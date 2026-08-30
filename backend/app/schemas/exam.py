"""Exam models."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import Schema
from app.schemas.enums import ExamStatus
from app.schemas.question import QuestionOut


class ExamConfig(Schema):
    """Delivery rules applied per candidate session.

    ``questions_per_student`` is why the question bank exists: drawing a subset
    requires a pool larger than the paper. Zero means "use the whole paper".

    Randomization is materialized into the session at check-in and persisted -
    never recomputed per request, or a reconnect would reshuffle the paper and
    every saved answer would point at the wrong question.
    """

    questions_per_student: int = Field(
        default=0, ge=0, alias="questionsPerStudent"
    )
    randomize_questions: bool = Field(default=False, alias="randomizeQuestions")
    randomize_options: bool = Field(default=False, alias="randomizeOptions")
    allow_navigation: bool = Field(default=True, alias="allowNavigation")
    auto_submit_on_expiry: bool = Field(default=True, alias="autoSubmitOnExpiry")


class ExamCreate(Schema):
    title: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=40)
    course: str = Field(min_length=1, max_length=200)
    department: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2_000)
    instructions: list[str] = Field(default_factory=list)
    duration_minutes: int = Field(ge=5, le=480, alias="durationMinutes")
    scheduled_at: datetime = Field(alias="scheduledAt")
    lab_id: UUID = Field(alias="labId")
    student_ids: list[UUID] = Field(default_factory=list, alias="studentIds")
    question_ids: list[UUID] = Field(default_factory=list, alias="questionIds")
    config: ExamConfig = Field(default_factory=ExamConfig)


class ExamUpdate(Schema):
    """Accepted only while the exam is DRAFT. Every field optional."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    course: str | None = None
    department: str | None = None
    description: str | None = None
    instructions: list[str] | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480, alias="durationMinutes")
    scheduled_at: datetime | None = Field(default=None, alias="scheduledAt")
    lab_id: UUID | None = Field(default=None, alias="labId")
    student_ids: list[UUID] | None = Field(default=None, alias="studentIds")
    question_ids: list[UUID] | None = Field(default=None, alias="questionIds")
    config: ExamConfig | None = None


class ExamSummary(Schema):
    """List-row shape. Deliberately excludes questions - an assessments table
    of 200 exams must not carry every paper with it."""

    id: UUID
    code: str
    title: str
    course: str
    department: str
    status: ExamStatus
    duration_minutes: int = Field(alias="durationMinutes")
    #: The advertised slot. Mutable while DRAFT.
    scheduled_at: datetime = Field(alias="scheduledAt")
    #: Stamped once, when faculty press start. Null until then, immutable after.
    starts_at: datetime | None = Field(default=None, alias="startsAt")
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    lab_id: UUID = Field(alias="labId")
    lab_name: str = Field(alias="labName")
    enrolled_count: int = Field(alias="enrolledCount")
    question_count: int = Field(alias="questionCount")
    total_marks: int = Field(alias="totalMarks")

    @model_validator(mode="after")
    def _window_is_coherent(self) -> "ExamSummary":
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class ExamDetail(ExamSummary):
    """Faculty-facing detail. Carries the answer key - never returned to a
    STUDENT subject."""

    description: str | None = None
    instructions: list[str] = Field(default_factory=list)
    config: ExamConfig
    questions: list[QuestionOut] = Field(default_factory=list)
    created_by: UUID = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")


class ExamStartRequest(Schema):
    """Start is idempotent, so a retried request must not shift the window.

    ``idempotency_key`` lets the server recognise a retry of the *same* attempt
    rather than a deliberate restart.
    """

    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class ExamCancelRequest(Schema):
    reason: str = Field(min_length=3, max_length=500)


class ExamWindow(Schema):
    """Returned by start. This is the authoritative exam clock."""

    exam_id: UUID = Field(alias="examId")
    status: ExamStatus
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime = Field(alias="endsAt")
    released_session_count: int = Field(alias="releasedSessionCount")
