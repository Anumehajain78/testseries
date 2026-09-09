"""Write services — the exam lifecycle.

Every transition here is guarded by ``app.domain.transitions`` rather than by an
``if`` invented at the call site, and every one writes an audit event, because a
transition nobody can account for afterwards is not much better than one that
did not happen.

Three properties this module is responsible for:

* **The server owns the clock.** ``starts_at`` and ``ends_at`` are stamped here,
  once, and never moved. The database refuses a LIVE exam without them.
* **Start is idempotent.** Invigilators press buttons twice and networks retry;
  neither may shift the window or disturb a candidate already answering.
* **Capacity is enforced.** The frontend checks it too, but only as UX — a
  candidate can edit the client, so scheduling is where it actually holds.
"""

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    Computer,
    Exam,
    ExamEnrolment,
    ExamQuestion,
    ExamSession,
    Question,
    QuestionOption,
)
from app.domain.seating import Workstation, allocate_seats, capacity_shortfall
from app.domain.transitions import IllegalTransition, assert_exam_move
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ExamStatus,
    SessionStatus,
    SubjectType,
)
from app.schemas.exam import ExamCreate, ExamWindow
from app.realtime.events import publish_soon
from app.schemas.enums import RealtimeEvent as RT
from app.services import queries
from app.utils.clock import exam_window, utcnow


def _conflict(exc: IllegalTransition) -> HTTPException:
    """Surface a refused transition with both states, so the client can say
    something useful instead of 'something went wrong'."""
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail={
            "code": "illegal_transition",
            "message": str(exc),
            "currentState": str(exc.current),
            "requestedState": str(exc.requested),
        },
    )


def _load(db: Session, exam_id: UUID) -> Exam:
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    return exam


def _audit(
    db: Session,
    *,
    event: AuditEventType,
    category: AuditCategory,
    severity: AuditSeverity,
    detail: str,
    actor_label: str,
    actor_id: UUID | None = None,
    exam_id: UUID | None = None,
) -> None:
    now = utcnow()
    db.add(
        AuditEvent(
            id=uuid4(),
            event=event,
            category=category,
            severity=severity,
            detail=detail,
            # Server-originated, so both timestamps are the server's own.
            occurred_at=now,
            recorded_at=now,
            actor_type=SubjectType.USER,
            actor_label=actor_label,
            actor_id=str(actor_id) if actor_id else None,
            exam_id=exam_id,
        )
    )


def _bump_seq(exam: Exam) -> int:
    """Advance the per-exam event sequence.

    Realtime frames carry this so a client that sees a gap refetches instead of
    drifting. Incrementing on every transition means the number is already
    meaningful when the websocket arrives.
    """
    exam.event_seq += 1
    return exam.event_seq


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_exam(db: Session, payload: ExamCreate, *, actor_id: UUID, actor_label: str):
    exam = Exam(
        id=uuid4(),
        code=payload.code,
        title=payload.title,
        course=payload.course,
        department=payload.department,
        description=payload.description,
        instructions=payload.instructions,
        duration_minutes=payload.duration_minutes,
        scheduled_at=payload.scheduled_at,
        status=ExamStatus.DRAFT,
        lab_id=payload.lab_id,
        created_by=actor_id,
        config=payload.config.model_dump(by_alias=True),
    )
    db.add(exam)
    db.flush()

    position = 0
    # Existing bank questions first, in the order given.
    for question_id in payload.question_ids:
        db.add(ExamQuestion(exam_id=exam.id, question_id=question_id, position=position))
        position += 1

    # Inline questions join the bank rather than being trapped in this exam.
    for authored in payload.questions:
        question = Question(
            id=uuid4(),
            owner_id=actor_id,
            course=authored.course or payload.course,
            type=authored.type,
            prompt=authored.prompt,
            marks=authored.marks,
        )
        question.options = [
            QuestionOption(id=uuid4(), position=index, body=option.body, is_correct=option.is_correct)
            for index, option in enumerate(authored.options)
        ]
        db.add(question)
        db.flush()
        db.add(ExamQuestion(exam_id=exam.id, question_id=question.id, position=position))
        position += 1

    for student_id in payload.student_ids:
        db.add(ExamEnrolment(exam_id=exam.id, student_id=student_id))

    _audit(
        db,
        event=AuditEventType.EXAM_CREATED,
        category=AuditCategory.SYSTEM,
        severity=AuditSeverity.INFO,
        detail=f"{exam.title} saved as a draft.",
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam.id,
    )
    db.commit()
    return queries.get_exam(db, exam.id)


def update_exam(db: Session, exam_id: UUID, payload, *, actor_id: UUID, actor_label: str):
    """Edit a draft.

    Refused once the exam leaves DRAFT: changing a paper, a roster or a
    duration after candidates have been seated would silently invalidate the
    seating and the window they were promised.
    """
    exam = _load(db, exam_id)
    if exam.status is not ExamStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "not_editable",
                "message": "Only a draft assessment can be edited.",
                "currentState": str(exam.status),
                "requestedState": str(ExamStatus.DRAFT),
            },
        )

    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    for column in ("title", "course", "department", "description", "instructions",
                   "duration_minutes", "scheduled_at", "lab_id"):
        if column in fields:
            setattr(exam, column, fields[column])
    if "config" in fields and payload.config is not None:
        exam.config = payload.config.model_dump(by_alias=True)

    if payload.student_ids is not None:
        db.execute(ExamEnrolment.__table__.delete().where(ExamEnrolment.exam_id == exam_id))
        for student_id in payload.student_ids:
            db.add(ExamEnrolment(exam_id=exam_id, student_id=student_id))

    # Replacing the paper is safe here and only here: a draft has no sessions,
    # so nobody is mid-answer on a question about to be swapped out.
    if payload.question_ids is not None or payload.questions is not None:
        db.execute(ExamQuestion.__table__.delete().where(ExamQuestion.exam_id == exam_id))
        position = 0
        for question_id in payload.question_ids or []:
            db.add(ExamQuestion(exam_id=exam_id, question_id=question_id, position=position))
            position += 1
        for authored in payload.questions or []:
            question = Question(
                id=uuid4(),
                owner_id=actor_id,
                course=authored.course or exam.course,
                type=authored.type,
                prompt=authored.prompt,
                marks=authored.marks,
            )
            question.options = [
                QuestionOption(id=uuid4(), position=index, body=option.body, is_correct=option.is_correct)
                for index, option in enumerate(authored.options)
            ]
            db.add(question)
            db.flush()
            db.add(ExamQuestion(exam_id=exam_id, question_id=question.id, position=position))
            position += 1

    _audit(
        db,
        event=AuditEventType.EXAM_CREATED,
        category=AuditCategory.SYSTEM,
        severity=AuditSeverity.INFO,
        detail=f"{exam.title} draft updated.",
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam_id,
    )
    db.commit()
    return queries.get_exam(db, exam_id)


# ---------------------------------------------------------------------------
# Schedule — seats the roster
# ---------------------------------------------------------------------------


def schedule_exam(db: Session, exam_id: UUID, *, actor_id: UUID, actor_label: str):
    exam = _load(db, exam_id)
    try:
        assert_exam_move(exam.status, ExamStatus.SCHEDULED)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc

    enrolled = list(
        db.execute(
            select(ExamEnrolment.student_id)
            .where(ExamEnrolment.exam_id == exam_id)
            .order_by(ExamEnrolment.enrolled_at)
        ).scalars()
    )
    if not enrolled:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Assign at least one candidate before scheduling"
        )

    machines = db.execute(
        select(Computer).where(Computer.lab_id == exam.lab_id).order_by(Computer.position)
    ).scalars().all()

    # The capacity rule the frontend only suggests.
    shortfall = capacity_shortfall(len(enrolled), len(machines))
    if shortfall:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{exam.lab.name} seats {len(machines)} candidates; {len(enrolled)} are enrolled.",
        )

    existing = db.execute(
        select(ExamSession.student_id, ExamSession.computer_id).where(ExamSession.exam_id == exam_id)
    ).all()
    already_seated = {student_id for student_id, _ in existing}
    occupied = {computer_id for _, computer_id in existing if computer_id}

    assignments = allocate_seats(
        enrolled,
        [Workstation(id=m.id, machine_id=m.machine_id, position=m.position) for m in machines],
        occupied_computer_ids=occupied,
        already_seated=already_seated,
    )
    for assignment in assignments:
        db.add(
            ExamSession(
                id=uuid4(),
                exam_id=exam_id,
                student_id=assignment.student_id,
                computer_id=assignment.computer_id,
                status=SessionStatus.NOT_STARTED,
            )
        )

    exam.status = ExamStatus.SCHEDULED
    # Seating is what READY means, so the two transitions happen together.
    assert_exam_move(exam.status, ExamStatus.READY)
    exam.status = ExamStatus.READY
    _bump_seq(exam)

    _audit(
        db,
        event=AuditEventType.EXAM_SCHEDULED,
        category=AuditCategory.EXAM,
        severity=AuditSeverity.INFO,
        detail=f"{exam.title} scheduled; {len(assignments)} candidates seated.",
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam_id,
    )
    db.commit()
    publish_soon(RT.SESSION_STATE_CHANGED, exam.id, exam.event_seq, seatedCount=len(assignments))
    return queries.get_exam(db, exam_id)


# ---------------------------------------------------------------------------
# Start — stamps the authoritative window
# ---------------------------------------------------------------------------


def start_exam(
    db: Session, exam_id: UUID, *, idempotency_key: str | None, actor_id: UUID, actor_label: str
) -> ExamWindow:
    exam = _load(db, exam_id)

    # A retry of the same attempt returns the existing window untouched. Without
    # this a double-click would move the deadline for a room full of people.
    if exam.status in (ExamStatus.LIVE, ExamStatus.ENDING) and exam.starts_at and exam.ends_at:
        same_attempt = idempotency_key is not None and idempotency_key == exam.start_idempotency_key
        if same_attempt or idempotency_key is None:
            return _window(db, exam)

    try:
        assert_exam_move(exam.status, ExamStatus.LIVE)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc

    starts_at, ends_at = exam_window(exam.duration_minutes)
    exam.starts_at = starts_at
    exam.ends_at = ends_at
    exam.status = ExamStatus.LIVE
    exam.started_by = actor_id
    exam.start_idempotency_key = idempotency_key
    _bump_seq(exam)

    # Release only candidates who are actually waiting. A session already ACTIVE
    # keeps its own started_at, so a repeat start cannot reset anyone's clock.
    released = 0
    sessions = db.execute(select(ExamSession).where(ExamSession.exam_id == exam_id)).scalars().all()
    for session in sessions:
        if session.status in (SessionStatus.NOT_STARTED, SessionStatus.WAITING, SessionStatus.READY):
            session.status = SessionStatus.ACTIVE
            session.started_at = session.started_at or starts_at
            released += 1

    _audit(
        db,
        event=AuditEventType.EXAM_STARTED,
        category=AuditCategory.EXAM,
        severity=AuditSeverity.INFO,
        detail=f"{exam.title} went live; {released} candidates released.",
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam_id,
    )
    db.commit()
    # Fire-and-forget: the exam has started whether or not a browser hears it.
    publish_soon(
        RT.EXAM_STARTED, exam.id, exam.event_seq,
        startsAt=starts_at.isoformat(), endsAt=ends_at.isoformat(),
        releasedSessionCount=released,
    )
    return _window(db, exam, released)


def _window(db: Session, exam: Exam, released: int | None = None) -> ExamWindow:
    if released is None:
        released = db.scalar(
            select(func.count())
            .select_from(ExamSession)
            .where(ExamSession.exam_id == exam.id, ExamSession.status == SessionStatus.ACTIVE)
        ) or 0
    return ExamWindow(
        exam_id=exam.id,
        status=exam.status,
        starts_at=exam.starts_at,
        ends_at=exam.ends_at,
        released_session_count=released,
    )


# ---------------------------------------------------------------------------
# End and cancel
# ---------------------------------------------------------------------------


def end_exam(db: Session, exam_id: UUID, *, actor_id: UUID, actor_label: str) -> ExamWindow:
    """Close early. Enters ENDING, sweeps, then COMPLETED.

    The sweep distinguishes a candidate who sat the paper from one who never
    arrived: the first is AUTO_SUBMITTED, the second TERMINATED. Collapsing them
    would report an absent candidate as having submitted nothing.
    """
    exam = _load(db, exam_id)
    try:
        assert_exam_move(exam.status, ExamStatus.ENDING)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc

    now = utcnow()
    exam.status = ExamStatus.ENDING
    exam.ends_at = min(exam.ends_at, now) if exam.ends_at else now
    exam.ended_at = now

    swept = 0
    sessions = db.execute(select(ExamSession).where(ExamSession.exam_id == exam_id)).scalars().all()
    for session in sessions:
        if session.status is SessionStatus.ACTIVE:
            session.status = SessionStatus.AUTO_SUBMITTED
            session.submitted_at = now
            session.submit_mode = "AUTO"
            session.submission_id = uuid4()
            swept += 1
        elif session.status in (
            SessionStatus.NOT_STARTED,
            SessionStatus.WAITING,
            SessionStatus.READY,
        ):
            session.status = SessionStatus.TERMINATED

    assert_exam_move(exam.status, ExamStatus.COMPLETED)
    exam.status = ExamStatus.COMPLETED
    _bump_seq(exam)

    _audit(
        db,
        event=AuditEventType.EXAM_ENDED,
        category=AuditCategory.EXAM,
        severity=AuditSeverity.INFO if swept == 0 else AuditSeverity.WARNING,
        detail=f"{exam.title} closed; {swept} candidates auto-submitted by the sweep.",
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam_id,
    )
    db.commit()
    publish_soon(RT.EXAM_ENDED, exam.id, exam.event_seq, sweptCount=swept)
    return _window(db, exam, 0)


def cancel_exam(db: Session, exam_id: UUID, reason: str, *, actor_id: UUID, actor_label: str):
    exam = _load(db, exam_id)
    try:
        assert_exam_move(exam.status, ExamStatus.CANCELLED)
    except IllegalTransition as exc:
        raise _conflict(exc) from exc

    exam.status = ExamStatus.CANCELLED
    exam.cancelled_reason = reason
    _bump_seq(exam)

    for session in db.execute(
        select(ExamSession).where(ExamSession.exam_id == exam_id)
    ).scalars().all():
        if session.status not in (
            SessionStatus.SUBMITTED,
            SessionStatus.AUTO_SUBMITTED,
            SessionStatus.TERMINATED,
        ):
            session.status = SessionStatus.TERMINATED

    _audit(
        db,
        event=AuditEventType.EXAM_CANCELLED,
        category=AuditCategory.EXAM,
        # Cancelling a scheduled examination is always worth an explanation.
        severity=AuditSeverity.CRITICAL,
        detail=f"{exam.title} cancelled: {reason}",
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam_id,
    )
    db.commit()
    page = queries.list_exams(db, limit=200)
    return next(item for item in page.items if item.id == exam_id)


# ---------------------------------------------------------------------------
# Results publication
# ---------------------------------------------------------------------------


def publish_results(db: Session, exam_id: UUID, published: bool, *, actor_id: UUID, actor_label: str):
    exam = _load(db, exam_id)
    exam.results_published_at = utcnow() if published else None
    _audit(
        db,
        event=AuditEventType.RESULTS_PUBLISHED,
        category=AuditCategory.EXAM,
        severity=AuditSeverity.INFO,
        detail=f"Results for {exam.title} {'published' if published else 'withheld'}.",
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam_id,
    )
    db.commit()
    return queries.get_results(db, exam_id)
