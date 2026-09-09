"""Exam management. Faculty and admin scope.

Reads query the database; writes run the exam lifecycle through the state
machine in ``app.domain.transitions``. A refused transition is a 409 carrying
both states, not a generic error.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, Staff
from app.services import commands, queries, sessions as session_service
from app.schemas.common import ErrorDetail, Page
from app.schemas.enums import ExamStatus
from app.schemas.exam import (
    ExamCancelRequest,
    ExamCreate,
    ExamDetail,
    ExamStartRequest,
    ExamSummary,
    ExamUpdate,
    ExamWindow,
)
from app.schemas.result import PublishResultsRequest, ResultsPage
from app.schemas.session import AwardMarksRequest, MarkingItem, MonitorSnapshot, SessionRow

router = APIRouter(prefix="/exams", tags=["exams"])

ILLEGAL_TRANSITION = {
    status.HTTP_409_CONFLICT: {
        "model": ErrorDetail,
        "description": "The exam is not in a state that permits this transition.",
    }
}


@router.get("", response_model=Page[ExamSummary], operation_id="listExams")
async def list_exams(
    db: DbSession,
    _: Staff,
    status_filter: ExamStatus | None = Query(default=None, alias="status"),
    lab_id: UUID | None = Query(default=None, alias="labId"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[ExamSummary]:
    """Backs the assessments table and the dashboard."""
    return queries.list_exams(db, status=status_filter, lab_id=lab_id, limit=limit, offset=offset)


@router.post("", response_model=ExamDetail, status_code=status.HTTP_201_CREATED, operation_id="createExam")
async def create_exam(payload: ExamCreate, db: DbSession, principal: Staff) -> ExamDetail:
    """Creates the exam as a DRAFT.

    Questions may be referenced from the bank or authored inline; either way
    they end up in the bank, so a paper written here is reusable afterwards.
    """
    return commands.create_exam(
        db, payload, actor_id=UUID(principal.subject_id), actor_label="Exam Cell"
    )


@router.get("/{exam_id}", response_model=ExamDetail, operation_id="getExam")
async def get_exam(exam_id: UUID, db: DbSession, _: Staff) -> ExamDetail:
    """Faculty-facing detail, including answer keys.

    Never reachable by a STUDENT subject; candidates read their paper through
    ``GET /sessions/{id}`` instead.
    """
    exam = queries.get_exam(db, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    return exam


@router.patch("/{exam_id}", response_model=ExamDetail, responses=ILLEGAL_TRANSITION, operation_id="updateExam")
async def update_exam(
    exam_id: UUID, payload: ExamUpdate, db: DbSession, principal: Staff
) -> ExamDetail:
    """Rejected with 409 unless the exam is still DRAFT."""
    return commands.update_exam(
        db, exam_id, payload, actor_id=UUID(principal.subject_id), actor_label="Exam Cell"
    )


@router.post("/{exam_id}/schedule", response_model=ExamDetail, responses=ILLEGAL_TRANSITION, operation_id="scheduleExam")
async def schedule_exam(exam_id: UUID, db: DbSession, principal: Staff) -> ExamDetail:
    """DRAFT to SCHEDULED, then seats the roster to reach READY.

    Validates the roster against lab capacity inside the same transaction. The
    frontend performs this check too, but only as UX - a candidate can edit the
    client, so this is where it actually holds.
    """
    return commands.schedule_exam(
        db, exam_id, actor_id=UUID(principal.subject_id), actor_label="Exam Cell"
    )


@router.post("/{exam_id}/start", response_model=ExamWindow, responses=ILLEGAL_TRANSITION, operation_id="startExam")
async def start_exam(
    exam_id: UUID, payload: ExamStartRequest, db: DbSession, principal: Staff
) -> ExamWindow:
    """Stamps the authoritative window and releases waiting candidates.

    Idempotent: a retry with the same idempotency key returns the existing
    window rather than shifting it, and candidates already answering are left
    untouched.
    """
    return commands.start_exam(
        db,
        exam_id,
        idempotency_key=payload.idempotency_key,
        actor_id=UUID(principal.subject_id),
        actor_label="Exam Cell",
    )


@router.post("/{exam_id}/end", response_model=ExamWindow, responses=ILLEGAL_TRANSITION, operation_id="endExam")
async def end_exam(exam_id: UUID, db: DbSession, principal: Staff) -> ExamWindow:
    """Closes the exam early. Enters ENDING and begins the sweep."""
    return commands.end_exam(
        db, exam_id, actor_id=UUID(principal.subject_id), actor_label="Exam Cell"
    )


@router.post("/{exam_id}/cancel", response_model=ExamSummary, responses=ILLEGAL_TRANSITION, operation_id="cancelExam")
async def cancel_exam(
    exam_id: UUID, payload: ExamCancelRequest, db: DbSession, principal: Staff
) -> ExamSummary:
    """Requires a reason, which is written to the audit trail as CRITICAL."""
    return commands.cancel_exam(
        db, exam_id, payload.reason, actor_id=UUID(principal.subject_id), actor_label="Exam Cell"
    )


@router.get("/{exam_id}/sessions", response_model=list[SessionRow], operation_id="listExamSessions")
async def list_exam_sessions(exam_id: UUID, db: DbSession, _: Staff) -> list[SessionRow]:
    """The readiness roster before start, and the monitor table during."""
    return queries.list_exam_sessions(db, exam_id)


@router.get("/{exam_id}/monitor", response_model=MonitorSnapshot, operation_id="getExamMonitor")
async def get_exam_monitor(exam_id: UUID, db: DbSession, _: Staff) -> MonitorSnapshot:
    """Server-computed aggregates plus rows.

    Also the documented fallback when the websocket is unavailable: the same
    reducer consumes this and a live frame, so losing the socket degrades the
    refresh rate rather than correctness.
    """
    snapshot = queries.get_monitor(db, exam_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    return snapshot


@router.get("/{exam_id}/results", response_model=ResultsPage, operation_id="getExamResults")
async def get_exam_results(exam_id: UUID, db: DbSession, _: Staff) -> ResultsPage:
    """Ranked results. Scores are omitted while unpublished."""
    results = queries.get_results(db, exam_id)
    if results is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    return results


@router.get("/{exam_id}/marking", response_model=list[MarkingItem], operation_id="listForMarking")
async def list_for_marking(exam_id: UUID, db: DbSession, _: Staff) -> list[MarkingItem]:
    """Written answers on this exam, for a person to read and mark.

    Staff only — it shows candidates' work alongside their names.
    """
    return session_service.list_for_marking(db, exam_id)


@router.put(
    "/{exam_id}/marking/{session_id}/{question_id}",
    response_model=MarkingItem,
    operation_id="awardMarks",
)
async def award_marks(
    exam_id: UUID,
    session_id: UUID,
    question_id: UUID,
    payload: AwardMarksRequest,
    db: DbSession,
    principal: Staff,
) -> MarkingItem:
    """Award marks to one written answer and re-grade that paper."""
    return session_service.award_marks(
        db, session_id, question_id, payload.marks, marked_by=UUID(principal.subject_id)
    )


@router.post("/{exam_id}/results/publish", response_model=ResultsPage, operation_id="publishExamResults")
async def publish_exam_results(
    exam_id: UUID, payload: PublishResultsRequest, db: DbSession, principal: Staff
) -> ResultsPage:
    """Releases scores to candidates by setting ``published_at``."""
    return commands.publish_results(
        db, exam_id, payload.published, actor_id=UUID(principal.subject_id), actor_label="Exam Cell"
    )
