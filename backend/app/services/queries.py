"""Read services.

Everything the admin screens display, assembled from the database into the
contract's response models. Kept separate from the route handlers so the
mapping is testable without HTTP, and so step 05's write services have an
obvious neighbour rather than accreting inside route bodies.

Two rules run through the whole module:

* Liveness is derived here from ``last_heartbeat_at``, never read from a stored
  column, so a row is never stale in the one situation where staleness matters.
* Aggregates are computed in SQL rather than by loading rows and reducing them
  in Python — a monitor for a 200-seat exam must not depend on the client
  holding every session.
"""

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Answer,
    AuditEvent,
    Computer,
    Exam,
    ExamEnrolment,
    ExamQuestion,
    ExamSession,
    Lab,
    Question,
    Result,
    Student,
    User,
)
from app.domain.liveness import connection_state
from app.schemas.audit import AuditEventOut
from app.schemas.common import Page
from app.schemas.directory import ComputerOut, LabOut, StudentOut
from app.schemas.enums import (
    AuditCategory,
    AuditSeverity,
    ConnectionState,
    ExamStatus,
    SessionStatus,
)
from app.schemas.exam import ExamConfig, ExamDetail, ExamSummary
from app.schemas.question import OptionOut, QuestionOut
from app.schemas.result import ResultRow, ResultsPage, ResultStats
from app.schemas.session import (
    ActivityEntry,
    MonitorSnapshot,
    MonitorSummary,
    SessionDetail,
    SessionRow,
)
from app.utils.clock import utcnow

# Statuses that count as "the candidate has finished", for monitor aggregates.
_SUBMITTED = (SessionStatus.SUBMITTED, SessionStatus.AUTO_SUBMITTED)


def _paginate(stmt: Select, limit: int, offset: int) -> Select:
    return stmt.limit(limit).offset(offset)


def _count(db: Session, stmt: Select) -> int:
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------


def _exam_counts(db: Session, exam_ids: list[UUID]) -> dict[UUID, tuple[int, int, int]]:
    """Enrolment, question and total-mark counts for a page of exams.

    Gathered in two grouped queries rather than per row: an assessments table of
    200 exams should not issue 400 follow-up statements.
    """
    if not exam_ids:
        return {}

    enrolments = dict(
        db.execute(
            select(ExamEnrolment.exam_id, func.count())
            .where(ExamEnrolment.exam_id.in_(exam_ids))
            .group_by(ExamEnrolment.exam_id)
        ).all()
    )
    papers = {
        exam_id: (questions, marks or 0)
        for exam_id, questions, marks in db.execute(
            select(
                ExamQuestion.exam_id,
                func.count(),
                func.sum(func.coalesce(ExamQuestion.marks_override, Question.marks)),
            )
            .join(Question, Question.id == ExamQuestion.question_id)
            .where(ExamQuestion.exam_id.in_(exam_ids))
            .group_by(ExamQuestion.exam_id)
        ).all()
    }
    return {
        exam_id: (enrolments.get(exam_id, 0), *papers.get(exam_id, (0, 0)))
        for exam_id in exam_ids
    }


def _to_summary(exam: Exam, lab_name: str, counts: tuple[int, int, int]) -> ExamSummary:
    enrolled, questions, marks = counts
    return ExamSummary(
        id=exam.id,
        code=exam.code,
        title=exam.title,
        course=exam.course,
        department=exam.department,
        status=exam.status,
        duration_minutes=exam.duration_minutes,
        scheduled_at=exam.scheduled_at,
        starts_at=exam.starts_at,
        ends_at=exam.ends_at,
        lab_id=exam.lab_id,
        lab_name=lab_name,
        enrolled_count=enrolled,
        question_count=questions,
        total_marks=int(marks),
    )


def list_exams(
    db: Session,
    *,
    status: ExamStatus | None = None,
    lab_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[ExamSummary]:
    stmt = select(Exam, Lab.name).join(Lab, Lab.id == Exam.lab_id)
    if status is not None:
        stmt = stmt.where(Exam.status == status)
    if lab_id is not None:
        stmt = stmt.where(Exam.lab_id == lab_id)

    total = _count(db, stmt)
    # Newest scheduled slot first, matching how the assessments table reads.
    rows = db.execute(
        _paginate(stmt.order_by(Exam.scheduled_at.desc()), limit, offset)
    ).all()

    counts = _exam_counts(db, [exam.id for exam, _ in rows])
    items = [_to_summary(exam, lab_name, counts.get(exam.id, (0, 0, 0))) for exam, lab_name in rows]
    return Page[ExamSummary](items=items, total=total, limit=limit, offset=offset)


def get_exam(db: Session, exam_id: UUID) -> ExamDetail | None:
    """Faculty-facing detail, including answer keys.

    Never reachable by a candidate — the route guards this, and the candidate
    path reads :func:`get_session_paper` instead, whose models have no
    answer-key field at all.
    """
    row = db.execute(
        select(Exam, Lab.name).join(Lab, Lab.id == Exam.lab_id).where(Exam.id == exam_id)
    ).first()
    if row is None:
        return None
    exam, lab_name = row

    paper = db.execute(
        select(ExamQuestion, Question)
        .join(Question, Question.id == ExamQuestion.question_id)
        .options(selectinload(ExamQuestion.question).selectinload(Question.options))
        .where(ExamQuestion.exam_id == exam_id)
        .order_by(ExamQuestion.position)
    ).all()

    questions = [
        QuestionOut(
            id=question.id,
            type=question.type,
            prompt=question.prompt,
            marks=link.marks_override or question.marks,
            course=question.course,
            options=[
                OptionOut(id=o.id, position=o.position, body=o.body, is_correct=o.is_correct)
                for o in question.options
            ],
        )
        for link, question in paper
    ]

    counts = _exam_counts(db, [exam_id]).get(exam_id, (0, 0, 0))
    summary = _to_summary(exam, lab_name, counts)
    return ExamDetail(
        **summary.model_dump(),
        description=exam.description,
        instructions=list(exam.instructions or []),
        config=ExamConfig(**(exam.config or {})),
        questions=questions,
        created_by=exam.created_by,
        created_at=exam.created_at,
    )


# ---------------------------------------------------------------------------
# Sessions and monitoring
# ---------------------------------------------------------------------------


def _session_rows(db: Session, exam_id: UUID) -> list[tuple[ExamSession, User, Student, str | None]]:
    return db.execute(
        select(ExamSession, User, Student, Computer.machine_id)
        .join(Student, Student.user_id == ExamSession.student_id)
        .join(User, User.id == Student.user_id)
        .outerjoin(Computer, Computer.id == ExamSession.computer_id)
        .where(ExamSession.exam_id == exam_id)
        # Ordering by workstation puts the roster in the physical order an
        # invigilator walks the room.
        .order_by(Computer.position.nulls_last(), User.full_name)
    ).all()


def _answered_counts(db: Session, exam_id: UUID) -> dict[UUID, int]:
    return dict(
        db.execute(
            select(Answer.session_id, func.count())
            .join(ExamSession, ExamSession.id == Answer.session_id)
            .where(ExamSession.exam_id == exam_id)
            .group_by(Answer.session_id)
        ).all()
    )


def _to_session_row(
    session: ExamSession,
    user: User,
    student: Student,
    machine_id: str | None,
    answered: int,
    now,
) -> SessionRow:
    return SessionRow(
        id=session.id,
        student_id=session.student_id,
        student_name=user.full_name,
        registration_no=student.registration_no,
        machine_id=machine_id,
        status=session.status,
        connection=connection_state(session.last_heartbeat_at, now=now),
        checked_in_at=session.checked_in_at,
        started_at=session.started_at,
        submitted_at=session.submitted_at,
        last_heartbeat_at=session.last_heartbeat_at,
        warning_count=session.warning_count,
        answered_count=answered,
    )


def list_exam_sessions(db: Session, exam_id: UUID) -> list[SessionRow]:
    now = utcnow()
    answered = _answered_counts(db, exam_id)
    return [
        _to_session_row(session, user, student, machine_id, answered.get(session.id, 0), now)
        for session, user, student, machine_id in _session_rows(db, exam_id)
    ]


def get_monitor(db: Session, exam_id: UUID) -> MonitorSnapshot | None:
    exam = db.get(Exam, exam_id)
    if exam is None:
        return None

    rows = list_exam_sessions(db, exam_id)
    enrolled = db.scalar(
        select(func.count()).select_from(ExamEnrolment).where(ExamEnrolment.exam_id == exam_id)
    ) or 0

    summary = MonitorSummary(
        enrolled=enrolled,
        online=sum(1 for r in rows if r.connection is not ConnectionState.OFFLINE),
        active=sum(1 for r in rows if r.status is SessionStatus.ACTIVE),
        submitted=sum(1 for r in rows if r.status in _SUBMITTED),
        warnings=sum(1 for r in rows if r.connection is ConnectionState.WARNING),
        disconnected=sum(1 for r in rows if r.connection is ConnectionState.OFFLINE),
    )
    return MonitorSnapshot(exam_id=exam_id, summary=summary, rows=rows, seq=exam.event_seq)


def get_session_detail(db: Session, session_id: UUID) -> SessionDetail | None:
    row = db.execute(
        select(ExamSession, User, Student, Computer.machine_id)
        .join(Student, Student.user_id == ExamSession.student_id)
        .join(User, User.id == Student.user_id)
        .outerjoin(Computer, Computer.id == ExamSession.computer_id)
        .where(ExamSession.id == session_id)
    ).first()
    if row is None:
        return None
    session, user, student, machine_id = row

    answered = db.scalar(
        select(func.count()).select_from(Answer).where(Answer.session_id == session_id)
    ) or 0

    base = _to_session_row(session, user, student, machine_id, answered, utcnow())

    # The timeline is the audit trail filtered to this candidate — one source of
    # truth rather than a second, drifting event log.
    events = db.execute(
        select(AuditEvent)
        .where(AuditEvent.session_id == session_id)
        .order_by(AuditEvent.occurred_at)
    ).scalars().all()

    return SessionDetail(
        **base.model_dump(),
        exam_id=session.exam_id,
        activity=[
            ActivityEntry(
                at=event.occurred_at,
                event=event.event.value,
                severity=event.severity.value,
                detail=event.detail,
            )
            for event in events
        ],
    )


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


def get_results(db: Session, exam_id: UUID) -> ResultsPage | None:
    exam = db.get(Exam, exam_id)
    if exam is None:
        return None

    published = exam.results_published_at is not None

    rows = db.execute(
        select(Result, ExamSession, User, Student)
        .join(ExamSession, ExamSession.id == Result.session_id)
        .join(Student, Student.user_id == ExamSession.student_id)
        .join(User, User.id == Student.user_id)
        .where(ExamSession.exam_id == exam_id)
        .order_by((Result.score / Result.max_score).desc(), User.full_name)
    ).all()

    results: list[ResultRow] = []
    percentages: list[float] = []
    for rank, (result, session, user, student) in enumerate(rows, start=1):
        percentage = round(float(result.score) / float(result.max_score) * 100, 1)
        percentages.append(percentage)
        taken = None
        if session.submitted_at and session.started_at:
            taken = int((session.submitted_at - session.started_at).total_seconds())
        results.append(
            ResultRow(
                rank=rank,
                session_id=session.id,
                student_id=session.student_id,
                student_name=user.full_name,
                registration_no=student.registration_no,
                # Scores are withheld until faculty publish them. Omitting the
                # value rather than hiding it in the UI means an unpublished
                # score never reaches the browser at all.
                score=float(result.score) if published else None,
                max_score=float(result.max_score),
                percentage=percentage if published else None,
                time_taken_seconds=taken,
                mode=session.submit_mode,
                submitted_at=session.submitted_at,
            )
        )

    stats = ResultStats(
        submitted=len(results),
        graded=len(results),
        average_percentage=round(sum(percentages) / len(percentages), 1) if percentages else None,
        highest_percentage=max(percentages) if percentages else None,
    )
    return ResultsPage(
        exam_id=exam_id,
        published=published,
        published_at=exam.results_published_at,
        stats=stats,
        rows=results,
    )


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------


def list_students(
    db: Session,
    *,
    search: str | None = None,
    section: str | None = None,
    semester: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[StudentOut]:
    stmt = select(Student, User).join(User, User.id == Student.user_id)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(User.full_name).like(pattern)
            | func.lower(Student.registration_no).like(pattern)
        )
    if section:
        stmt = stmt.where(Student.section == section)
    if semester is not None:
        stmt = stmt.where(Student.semester == semester)

    total = _count(db, stmt)
    rows = db.execute(_paginate(stmt.order_by(Student.registration_no), limit, offset)).all()
    items = [
        StudentOut(
            id=student.user_id,
            registration_no=student.registration_no,
            full_name=user.full_name,
            email=user.email,
            program=student.program,
            semester=student.semester,
            section=student.section,
            status=student.status,
        )
        for student, user in rows
    ]
    return Page[StudentOut](items=items, total=total, limit=limit, offset=offset)


def list_labs(db: Session) -> list[LabOut]:
    now = utcnow()
    labs = db.execute(select(Lab).order_by(Lab.name)).scalars().all()
    machines = db.execute(select(Computer)).scalars().all()

    by_lab: dict[UUID, list[Computer]] = {}
    for machine in machines:
        by_lab.setdefault(machine.lab_id, []).append(machine)

    invigilators = dict(
        db.execute(select(User.id, User.full_name)).all()
    )

    return [
        LabOut(
            id=lab.id,
            name=lab.name,
            building=lab.building,
            capacity=lab.capacity,
            status=lab.status,
            invigilator_id=lab.invigilator_id,
            invigilator_name=invigilators.get(lab.invigilator_id),
            computer_count=len(by_lab.get(lab.id, [])),
            online_count=sum(
                1
                for machine in by_lab.get(lab.id, [])
                if connection_state(machine.last_heartbeat_at, now=now) is not ConnectionState.OFFLINE
            ),
        )
        for lab in labs
    ]


def list_lab_computers(db: Session, lab_id: UUID) -> list[ComputerOut]:
    now = utcnow()
    machines = db.execute(
        select(Computer).where(Computer.lab_id == lab_id).order_by(Computer.position)
    ).scalars().all()
    return [
        ComputerOut(
            id=machine.id,
            machine_id=machine.machine_id,
            lab_id=machine.lab_id,
            position=machine.position,
            hostname=machine.hostname,
            enrolled_at=machine.enrolled_at,
            last_heartbeat_at=machine.last_heartbeat_at,
            connection=connection_state(machine.last_heartbeat_at, now=now),
        )
        for machine in machines
    ]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def list_audit_events(
    db: Session,
    *,
    exam_id: UUID | None = None,
    student_id: UUID | None = None,
    severity: AuditSeverity | None = None,
    category: AuditCategory | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Page[AuditEventOut]:
    stmt = select(AuditEvent)
    if exam_id is not None:
        stmt = stmt.where(AuditEvent.exam_id == exam_id)
    if student_id is not None:
        stmt = stmt.where(AuditEvent.student_id == student_id)
    if severity is not None:
        stmt = stmt.where(AuditEvent.severity == severity)
    if category is not None:
        stmt = stmt.where(AuditEvent.category == category)

    total = _count(db, stmt)
    # Newest first: the trail is read as "what just happened".
    events = db.execute(
        _paginate(stmt.order_by(AuditEvent.occurred_at.desc()), limit, offset)
    ).scalars().all()

    return Page[AuditEventOut](
        items=[AuditEventOut.model_validate(event) for event in events],
        total=total,
        limit=limit,
        offset=offset,
    )
