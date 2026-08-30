"""Candidate session endpoints.

Scope rules that step 03 must enforce, stated here so they are not invented
later:

* A STUDENT subject may only address their own session.
* Answers and flags require exam LIVE **and** session ACTIVE
  (``domain.transitions.accepts_candidate_writes``).
* Nothing in this module may return a model carrying an answer key.
"""

from uuid import UUID

from fastapi import APIRouter, status

from app import examples
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
async def list_my_exams() -> list[ExamSummary]:
    """Assessments the authenticated candidate is enrolled in."""
    return [examples.EXAM_SUMMARY]


@router.post("/sessions/{session_id}/checkin", response_model=SessionPaper, operation_id="checkInSession")
async def check_in(session_id: UUID, payload: CheckInRequest) -> SessionPaper:
    """Enters the waiting room and materializes this candidate's paper.

    The question and option ordering is drawn **once, here**, and persisted on
    the session. Recomputing it per request would reshuffle the paper on
    reconnect and leave every saved answer pointing at the wrong question.
    """
    return examples.SESSION_PAPER


@router.get("/sessions/{session_id}", response_model=SessionPaper, operation_id="getSessionPaper")
async def get_session_paper(session_id: UUID) -> SessionPaper:
    """The paper as ordered for this candidate. Carries no answer keys."""
    return examples.SESSION_PAPER


@router.get("/sessions/{session_id}/state", response_model=SessionState, operation_id="getSessionState")
async def get_session_state(session_id: UUID) -> SessionState:
    """Reconnect recovery.

    Returns the server's view of every saved answer, so a client that missed
    acknowledgements during a network drop can tell what actually landed
    instead of guessing.
    """
    return examples.SESSION_STATE


@router.put(
    "/sessions/{session_id}/answers/{question_id}",
    response_model=SaveAnswerResponse,
    responses=WRITE_REFUSED,
    operation_id="saveAnswer",
)
async def save_answer(session_id: UUID, question_id: UUID, payload: SaveAnswerRequest) -> SaveAnswerResponse:
    """Idempotent upsert of one answer.

    ``client_seq`` lets a stale write that arrives late after a reconnect be
    discarded without relying on either clock.
    """
    return SaveAnswerResponse(
        question_id=question_id, saved_at=examples.server_time(), accepted=True
    )


@router.put(
    "/sessions/{session_id}/flags/{question_id}",
    response_model=SaveAnswerResponse,
    responses=WRITE_REFUSED,
    operation_id="toggleFlag",
)
async def toggle_flag(session_id: UUID, question_id: UUID) -> SaveAnswerResponse:
    """Toggles the review flag for one question."""
    return SaveAnswerResponse(
        question_id=question_id, saved_at=examples.server_time(), accepted=True
    )


@router.post(
    "/sessions/{session_id}/submit",
    response_model=SubmissionReceipt,
    responses=WRITE_REFUSED,
    operation_id="submitSession",
)
async def submit_session(session_id: UUID, payload: SubmitRequest) -> SubmissionReceipt:
    """Final submission.

    Idempotent: a repeat call returns the original receipt rather than
    recording a second submission.
    """
    return examples.RECEIPT


@router.get("/sessions/{session_id}/detail", response_model=SessionDetail, operation_id="getSessionDetail")
async def get_session_detail(session_id: UUID) -> SessionDetail:
    """Invigilator drill-down: identity, machine, timings, and event timeline.

    Faculty scope - this is the monitor's detail drawer, not a candidate view.
    """
    return examples.SESSION_DETAIL


@router.post(
    "/sessions/{session_id}/events",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="reportSessionEvent",
)
async def report_session_event(session_id: UUID, payload: SessionEventRequest) -> dict[str, str]:
    """Invigilation signal from the lab client. Machine subjects only.

    Accepted and recorded as evidence; a focus loss raises a warning count but
    is never treated on its own as proof of misconduct.
    """
    return {"status": "accepted"}


@router.post(
    "/computers/{machine_id}/heartbeat",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="postHeartbeat",
)
async def post_heartbeat(machine_id: str, payload: HeartbeatRequest) -> dict[str, str]:
    """Liveness ping from a workstation. Machine subjects only.

    High volume by design - 60 machines in a lab. Held in Redis rather than
    written as a row per beat.
    """
    return {"status": "accepted"}
