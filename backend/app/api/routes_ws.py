"""WebSocket channels.

Authentication is the awkward part of browser WebSockets: the API cannot set an
Authorization header on the handshake. The token therefore arrives as a query
parameter, which is acceptable only because these are short-lived access tokens
over the college LAN — and it is still checked exactly as a REST request would
be, including the database lookup that makes a deleted account stop working.

The socket is an accelerator, never the source of truth. A client that misses
frames, sees a sequence gap, or cannot connect at all falls back to
``GET /exams/{id}/monitor`` and stays correct.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_token
from app.db.models import Exam, ExamSession, User
from app.db.session import SessionLocal
from app.realtime.broker import channel_for, get_broker
from app.schemas.enums import RealtimeEvent, Role, SubjectType
from app.utils.clock import utcnow

log = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])

#: Sent when nothing has happened, so an idle socket is distinguishable from a
#: dead one without waiting for a TCP timeout.
KEEPALIVE_SECONDS = 20


def _principal(token: str) -> tuple[SubjectType, str, Role | None]:
    claims = decode_token(token, expected_type="access")
    subject_type = SubjectType(claims.get("sty", "user"))
    role = Role(claims["role"]) if claims.get("role") else None
    return subject_type, claims["sub"], role


def _staff_may_watch(db: Session, subject_id: str, role: Role | None) -> bool:
    if role not in (Role.ADMIN, Role.FACULTY):
        return False
    # The database is authoritative: a revoked account must lose its socket,
    # not keep it until the token expires.
    try:
        user = db.get(User, UUID(subject_id))
    except ValueError:
        return False
    return user is not None and user.is_active and user.role in (Role.ADMIN, Role.FACULTY)


@router.websocket("/ws/exams/{exam_id}/monitor")
async def monitor_socket(
    websocket: WebSocket,
    exam_id: UUID,
    token: str = Query(..., description="Access token; headers are unavailable on a handshake."),
) -> None:
    """Live monitor feed for invigilators."""
    try:
        subject_type, subject_id, role = _principal(token)
    except TokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    if subject_type is not SubjectType.USER:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not permitted")
        return

    with SessionLocal() as db:
        if not _staff_may_watch(db, subject_id, role):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not permitted")
            return
        exam = db.get(Exam, exam_id)
        if exam is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown exam")
            return
        current_seq = exam.event_seq

    await websocket.accept()
    # The first frame carries the current sequence, so a client that reconnects
    # can tell immediately whether it missed anything while away.
    await websocket.send_json(
        {
            "event": "HELLO",
            "examId": str(exam_id),
            "seq": current_seq,
            "serverTime": utcnow().isoformat(),
        }
    )

    await _pump(websocket, channel_for(str(exam_id)))


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(
    websocket: WebSocket,
    session_id: UUID,
    token: str = Query(...),
) -> None:
    """A candidate's own channel: start, ending, and forced submission."""
    try:
        subject_type, subject_id, role = _principal(token)
    except TokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    with SessionLocal() as db:
        session = db.get(ExamSession, session_id)
        if session is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unknown session")
            return
        # A candidate reaches only their own session; staff may observe any.
        owns = subject_type is SubjectType.USER and str(session.student_id) == subject_id
        if not owns and not _staff_may_watch(db, subject_id, role):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not permitted")
            return
        exam_id = session.exam_id

    await websocket.accept()
    await _pump(websocket, channel_for(str(exam_id)))


async def _pump(websocket: WebSocket, channel: str) -> None:
    """Forward broker frames to one socket until it goes away."""
    broker = get_broker()
    subscription = broker.subscribe(channel)

    async def forward() -> None:
        async for frame in subscription:
            await websocket.send_json(frame)

    async def keepalive() -> None:
        while True:
            await asyncio.sleep(KEEPALIVE_SECONDS)
            await websocket.send_json(
                {"event": RealtimeEvent.HEARTBEAT.value, "serverTime": utcnow().isoformat()}
            )

    async def drain() -> None:
        # Nothing is expected from the browser on this channel, but reading is
        # how a disconnect is noticed promptly.
        while True:
            await websocket.receive_text()

    tasks = [asyncio.create_task(coro()) for coro in (forward, keepalive, drain)]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                task.result()
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        with contextlib.suppress(Exception):
            await subscription.aclose()
