"""Frames the server pushes.

Every frame carries ``seq`` and ``serverTime``. The sequence is what lets a
client notice it missed something — frames are dropped rather than queued when
a consumer is slow, so a gap is expected behaviour, not a bug — and refetch the
monitor snapshot instead of drifting quietly out of date.

Publishing is fire-and-forget by design. A realtime failure must never roll
back a transition that Postgres has already committed: the exam has started
whether or not anyone's browser heard about it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.realtime.broker import channel_for, get_broker
from app.schemas.enums import RealtimeEvent
from app.utils.clock import utcnow

log = logging.getLogger(__name__)


def _frame(event: RealtimeEvent, exam_id: UUID, seq: int, **payload: Any) -> dict[str, Any]:
    return {
        "event": event.value,
        "examId": str(exam_id),
        "seq": seq,
        "serverTime": utcnow().isoformat(),
        **payload,
    }


async def publish(event: RealtimeEvent, exam_id: UUID, seq: int, **payload: Any) -> None:
    await get_broker().publish(channel_for(str(exam_id)), _frame(event, exam_id, seq, **payload))


def publish_soon(event: RealtimeEvent, exam_id: UUID, seq: int, **payload: Any) -> None:
    """Publish from synchronous code without making it wait.

    The service layer is sync and already holds a committed transaction; the
    frame is a notification about work that is finished, so it is scheduled on
    the running loop and never awaited. If there is no loop — a script, a test
    — the frame is simply dropped, which is the correct outcome for a
    notification nobody is listening to.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_safe(event, exam_id, seq, payload))


async def _safe(event: RealtimeEvent, exam_id: UUID, seq: int, payload: dict[str, Any]) -> None:
    try:
        await publish(event, exam_id, seq, **payload)
    except Exception:  # pragma: no cover - defensive
        log.exception("realtime: failed to publish %s", event)
