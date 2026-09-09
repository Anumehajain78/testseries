"""Candidate session endpoints.

Scope rules that step 03 must enforce, stated here so they are not invented
later:

* A STUDENT subject may only address their own session.
* Answers and flags require exam LIVE **and** session ACTIVE
  (``domain.transitions.accepts_candidate_writes``).
* Nothing in this module may return a model carrying an answer key.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import Candidate, CurrentPrincipal, DbSession, Machine, Staff
from app.services import machines, queries, sessions as session_service
from app.db.models import Exam
from app.realtime.events import publish_soon
from app.schemas.enums import RealtimeEvent as RT
from app.schemas.common import ErrorDetail
from app.schemas.exam import ExamSummary
from app.schemas.session import (
    CheckInRequest,
    HeartbeatRequest,
    SaveAnswerRequest,
    SaveAnswerResponse,
    SessionDetail,
    SessionEventRequest,
    SessionPaper,
    SessionRow,
    SessionState,
    SubmissionReceipt,
    SubmitRequest,
)

router = APIRouter(tags=["sessions"])

WRITE_REFUSED = {
    status.HTTP_409_CONFLICT: {
        "model": ErrorDetail,
        "description": "The exam is not LIVE or the session is not ACTIVE, so writes are refused.",
    }
}


@router.get("/me/exams", response_model=list[ExamSummary], operation_id="listMyExams")
async def list_my_exams(db: DbSession, principal: Candidate) -> list[ExamSummary]:
    """Assessments the authenticated candidate is enrolled in."""
    return queries.list_my_exams(db, UUID(principal.subject_id))


@router.get("/me/sessions", response_model=list[SessionRow], operation_id="listMySessions")
async def list_my_sessions(db: DbSession, principal: Candidate) -> list[SessionRow]:
    """This candidate's own sessions, so they can find the paper they sit."""
    return queries.list_my_sessions(db, UUID(principal.subject_id))


@router.post("/sessions/{session_id}/checkin", response_model=SessionPaper, operation_id="checkInSession")
async def check_in(
    session_id: UUID, payload: CheckInRequest, db: DbSession, principal: CurrentPrincipal
) -> SessionPaper:
    """Enters the waiting room and materializes this candidate's paper.

    The question and option ordering is drawn **once, here**, and persisted on
    the session. Recomputing it per request would reshuffle the paper on
    reconnect and leave every saved answer pointing at the wrong question.
    """
    return session_service.check_in(db, session_id, principal, payload.machine_id)


@router.get("/sessions/{session_id}", response_model=SessionPaper, operation_id="getSessionPaper")
async def get_session_paper(
    session_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> SessionPaper:
    """The paper as ordered for this candidate. Carries no answer keys."""
    return session_service.get_paper(db, session_id, principal)


@router.get("/sessions/{session_id}/state", response_model=SessionState, operation_id="getSessionState")
async def get_session_state(
    session_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> SessionState:
    """Reconnect recovery.

    Returns the server's view of every saved answer, so a client that missed
    acknowledgements during a network drop can tell what actually landed
    instead of guessing.
    """
    return session_service.get_state(db, session_id, principal)


@router.put(
    "/sessions/{session_id}/answers/{question_id}",
    response_model=SaveAnswerResponse,
    responses=WRITE_REFUSED,
    operation_id="saveAnswer",
)
async def save_answer(
    session_id: UUID,
    question_id: UUID,
    payload: SaveAnswerRequest,
    db: DbSession,
    principal: CurrentPrincipal,
) -> SaveAnswerResponse:
    """Idempotent upsert of one answer.

    ``client_seq`` lets a stale write that arrives late after a reconnect be
    discarded without relying on either clock.
    """
    return session_service.save_answer(
        db, session_id, question_id, principal, payload.value, payload.client_seq
    )


@router.put(
    "/sessions/{session_id}/flags/{question_id}",
    response_model=SaveAnswerResponse,
    responses=WRITE_REFUSED,
    operation_id="toggleFlag",
)
async def toggle_flag(
    session_id: UUID, question_id: UUID, db: DbSession, principal: CurrentPrincipal
) -> SaveAnswerResponse:
    """Toggles the review flag for one question."""
    return session_service.toggle_flag(db, session_id, question_id, principal)


@router.post(
    "/sessions/{session_id}/submit",
    response_model=SubmissionReceipt,
    responses=WRITE_REFUSED,
    operation_id="submitSession",
)
async def submit_session(
    session_id: UUID, payload: SubmitRequest, db: DbSession, principal: CurrentPrincipal
) -> SubmissionReceipt:
    """Final submission.

    Idempotent: a repeat call returns the original receipt rather than
    recording a second submission.
    """
    return session_service.submit(db, session_id, principal)


@router.get("/sessions/{session_id}/detail", response_model=SessionDetail, operation_id="getSessionDetail")
async def get_session_detail(session_id: UUID, db: DbSession, _: Staff) -> SessionDetail:
    """Invigilator drill-down: identity, machine, timings, and event timeline.

    Faculty scope - this is the monitor's detail drawer, not a candidate view.
    """
    detail = queries.get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return detail


@router.post(
    "/sessions/{session_id}/events",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="reportSessionEvent",
)
async def report_session_event(
    session_id: UUID, payload: SessionEventRequest, db: DbSession, principal: Machine
) -> dict[str, str]:
    """Invigilation signal from the lab client. Machine subjects only.

    Recorded as evidence; a focus loss raises a warning count but is never
    treated on its own as proof of misconduct — a person decides what a
    pattern means.
    """
    session, warned = machines.record_event(
        db, principal.subject_id, session_id, payload.event, payload.occurred_at, payload.detail
    )
    if warned:
        exam = db.get(Exam, session.exam_id)
        publish_soon(
            RT.WARNING, session.exam_id, exam.event_seq if exam else 0,
            sessionId=str(session.id), studentId=str(session.student_id),
            reason=payload.event, occurredAt=payload.occurred_at.isoformat(),
        )
    return {"status": "recorded"}


@router.post(
    "/computers/{machine_id}/heartbeat",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="postHeartbeat",
)
async def post_heartbeat(
    machine_id: str, payload: HeartbeatRequest, db: DbSession, principal: Machine
) -> dict[str, str]:
    """Liveness ping from a workstation. Machine subjects only.

    High volume by design — sixty machines in a lab, every few seconds. A frame
    is published only when the machine's liveness actually changes; pushing one
    per beat would have every open monitor refetching several times a second.
    """
    if principal.subject_id != machine_id:
        # A machine reports for itself and nothing else.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A machine may only report its own liveness")

    changed, exam_id = machines.record_heartbeat(db, machine_id, payload.session_id)
    if changed and exam_id:
        exam = db.get(Exam, exam_id)
        publish_soon(
            RT.MACHINE_STATUS_CHANGED, exam_id, exam.event_seq if exam else 0,
            machineId=machine_id,
        )
    return {"status": "recorded"}
