"""Database models.

Constraints are expressed in the schema wherever the rule is absolute. A check
constraint the application also enforces is not redundancy — it is the version
that still holds when a migration, a fixture, or a future endpoint forgets.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, uuid_pk
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ExamStatus,
    LabStatus,
    QuestionType,
    Role,
    SessionStatus,
    StudentStatus,
    SubjectType,
    SubmitMode,
)


def pg_enum(enum_cls: type, name: str) -> Enum:
    """Native Postgres enums, storing the member *value* rather than the Python
    attribute name.

    Type creation belongs to the migration that first uses the type; every enum
    here is referenced by exactly one table, so SQLAlchemy emits each CREATE
    TYPE once. Adding a member later still needs a hand-written ALTER TYPE —
    Alembic cannot autogenerate enum changes — which is why the members are
    listed explicitly in the migration.
    """
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[Role] = mapped_column(pg_enum(Role, "role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped["Student | None"] = relationship(back_populates="user", uselist=False)
    faculty: Mapped["Faculty | None"] = relationship(back_populates="user", uselist=False)


class Student(Base, TimestampMixin):
    """Candidate profile, one-to-one with a user."""

    __tablename__ = "students"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    registration_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    program: Mapped[str] = mapped_column(String(120), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[StudentStatus] = mapped_column(
        pg_enum(StudentStatus, "student_status"), default=StudentStatus.ACTIVE, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="student")

    __table_args__ = (
        CheckConstraint("semester BETWEEN 1 AND 12", name="semester_range"),
    )


class Faculty(Base, TimestampMixin):
    __tablename__ = "faculty"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    employee_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)

    user: Mapped[User] = relationship(back_populates="faculty")


# ---------------------------------------------------------------------------
# Venues
# ---------------------------------------------------------------------------


class Lab(Base, TimestampMixin):
    __tablename__ = "labs"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    building: Mapped[str] = mapped_column(String(120), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[LabStatus] = mapped_column(
        pg_enum(LabStatus, "lab_status"), default=LabStatus.READY, nullable=False
    )
    invigilator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("faculty.user_id", ondelete="SET NULL")
    )

    computers: Mapped[list["Computer"]] = relationship(back_populates="lab")

    __table_args__ = (CheckConstraint("capacity >= 0", name="capacity_non_negative"),)


class Computer(Base, TimestampMixin):
    """A workstation.

    Deliberately has no student column. A lab hosts a different cohort every
    hour, so seating is a fact about a candidate sitting a particular exam and
    lives on ``exam_sessions.computer_id``.
    """

    __tablename__ = "computers"

    id: Mapped[uuid.UUID] = uuid_pk()
    lab_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("labs.id", ondelete="CASCADE"), nullable=False)
    machine_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    #: Hashed. The plaintext secret is shown once, at enrolment.
    secret_hash: Mapped[str | None] = mapped_column(String(255))
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    lab: Mapped[Lab] = relationship(back_populates="computers")

    __table_args__ = (
        UniqueConstraint("lab_id", "position", name="uq_computers_lab_position"),
    )


# ---------------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------------


class Question(Base, TimestampMixin):
    """Reusable bank entry.

    Questions are not owned by an exam: drawing ``questions_per_student`` needs
    a pool larger than any one paper.
    """

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("faculty.user_id", ondelete="SET NULL")
    )
    course: Mapped[str | None] = mapped_column(String(200), index=True)
    type: Mapped[QuestionType] = mapped_column(pg_enum(QuestionType, "question_type"), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    marks: Mapped[int] = mapped_column(Integer, nullable=False)

    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="QuestionOption.position"
    )

    __table_args__ = (CheckConstraint("marks > 0", name="marks_positive"),)


class QuestionOption(Base):
    __tablename__ = "question_options"

    id: Mapped[uuid.UUID] = uuid_pk()
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Never serialized to a candidate. The API enforces this structurally by
    #: having no field for it on the candidate-facing model.
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    question: Mapped[Question] = relationship(back_populates="options")

    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_question_options_question_id_position"),
    )


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------


class Exam(Base, TimestampMixin):
    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    #: The advertised slot. Mutable while DRAFT.
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    #: Stamped once at start, immutable after. Null means the exam never ran.
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[ExamStatus] = mapped_column(
        pg_enum(ExamStatus, "exam_status"), default=ExamStatus.DRAFT, nullable=False, index=True
    )
    lab_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("labs.id", ondelete="RESTRICT"), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("faculty.user_id", ondelete="SET NULL")
    )
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("faculty.user_id", ondelete="SET NULL")
    )
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    #: Set when a retried start is recognised as the same attempt rather than a
    #: deliberate restart.
    start_idempotency_key: Mapped[str | None] = mapped_column(String(80))
    #: Monotonic per-exam counter stamped on every realtime frame, so a client
    #: that sees a gap refetches instead of drifting.
    event_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    results_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lab: Mapped[Lab] = relationship()
    exam_questions: Mapped[list["ExamQuestion"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", order_by="ExamQuestion.position"
    )
    enrolments: Mapped[list["ExamEnrolment"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["ExamSession"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("duration_minutes >= 5", name="duration_minimum"),
        # The authoritative window can only move forwards. A schema that can
        # express an exam ending before it began will eventually contain one.
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name="window_moves_forward",
        ),
        # A live exam must have a window. This is what makes 'the server owns
        # the clock' a database guarantee rather than a convention.
        CheckConstraint(
            "status NOT IN ('LIVE', 'ENDING') OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="live_exam_has_window",
        ),
    )


class ExamQuestion(Base):
    """The paper: which bank questions this exam draws from, in which order."""

    __tablename__ = "exam_questions"

    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    marks_override: Mapped[int | None] = mapped_column(Integer)

    exam: Mapped[Exam] = relationship(back_populates="exam_questions")
    question: Mapped[Question] = relationship()


class ExamEnrolment(Base):
    """Which candidates are expected to sit this exam."""

    __tablename__ = "exam_enrolments"

    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), primary_key=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.user_id", ondelete="CASCADE"), primary_key=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    exam: Mapped[Exam] = relationship(back_populates="enrolments")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class ExamSession(Base, TimestampMixin):
    """One candidate sitting one exam. The central table of the system."""

    __tablename__ = "exam_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    exam_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("students.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    computer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("computers.id", ondelete="SET NULL")
    )
    status: Mapped[SessionStatus] = mapped_column(
        pg_enum(SessionStatus, "session_status"), default=SessionStatus.NOT_STARTED, nullable=False
    )

    #: Drawn once at check-in and persisted. Recomputing per request would
    #: reshuffle the paper on reconnect and leave saved answers pointing at the
    #: wrong questions.
    question_order: Mapped[list | None] = mapped_column(JSONB)
    option_order: Mapped[dict | None] = mapped_column(JSONB)

    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submit_mode: Mapped[SubmitMode | None] = mapped_column(pg_enum(SubmitMode, "submit_mode"))
    submission_id: Mapped[uuid.UUID | None] = mapped_column()
    #: Liveness source. ConnectionState is derived from this, never stored.
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    exam: Mapped[Exam] = relationship(back_populates="sessions")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # One session per candidate per exam. This is what makes seating and
        # submission idempotent at the storage layer rather than by convention.
        UniqueConstraint("exam_id", "student_id", name="uq_exam_sessions_exam_id_student_id"),
        # Two candidates cannot occupy one workstation in the same exam.
        Index(
            "uq_exam_sessions_exam_computer",
            "exam_id",
            "computer_id",
            unique=True,
            postgresql_where=text("computer_id IS NOT NULL"),
        ),
        CheckConstraint("warning_count >= 0", name="warning_count_non_negative"),
        # A terminal session must record when and how it ended.
        CheckConstraint(
            "status NOT IN ('SUBMITTED', 'AUTO_SUBMITTED') "
            "OR (submitted_at IS NOT NULL AND submit_mode IS NOT NULL)",
            name="submitted_session_has_receipt",
        ),
    )


class Answer(Base):
    __tablename__ = "answers"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    #: Mirrors the AnswerValue discriminated union on the wire.
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Client-side monotonic counter. Lets a stale write arriving late after a
    #: reconnect be discarded without trusting either clock.
    client_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[ExamSession] = relationship(back_populates="answers")


class Result(Base):
    """Grading outcome.

    Separate from the session because grading is asynchronous and publication
    is a distinct event: a score exists before candidates may see it.
    """

    __tablename__ = "results"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exam_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    max_score: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    graded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # The frontend once rendered 63/60 as 105%. A score outside its own
        # bounds is not merely a display bug, so the database refuses it.
        CheckConstraint("score >= 0", name="score_non_negative"),
        CheckConstraint("score <= max_score", name="score_within_max"),
        CheckConstraint("max_score > 0", name="max_score_positive"),
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditEvent(Base):
    """Append-only trail. There is deliberately no update or delete path."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    event: Mapped[AuditEventType] = mapped_column(
        pg_enum(AuditEventType, "audit_event_type"), nullable=False, index=True
    )
    category: Mapped[AuditCategory] = mapped_column(pg_enum(AuditCategory, "audit_category"), nullable=False)
    severity: Mapped[AuditSeverity] = mapped_column(
        pg_enum(AuditSeverity, "audit_severity"), nullable=False, index=True
    )
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)

    #: What the reporting client claimed.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When the server accepted it. Keeping both makes a skewed or manipulated
    #: client clock visible in the data instead of silently trusted.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    actor_type: Mapped[SubjectType] = mapped_column(pg_enum(SubjectType, "subject_type"), nullable=False)
    actor_label: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(80))

    exam_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exams.id", ondelete="SET NULL"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exam_sessions.id", ondelete="SET NULL"))
    student_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("students.user_id", ondelete="SET NULL"))
    machine_id: Mapped[str | None] = mapped_column(String(60))
