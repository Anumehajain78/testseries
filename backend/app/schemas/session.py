"""Exam session models - the central table of the whole system."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import AnswerValue, Schema
from app.schemas.enums import ConnectionState, SessionStatus, SubmitMode
from app.schemas.exam import ExamConfig
from app.schemas.question import StudentQuestionOut


class SessionRow(Schema):
    """One row of the live monitor and of the pre-start readiness roster.

    Note the two independent axes: ``status`` is lifecycle, ``connection`` is
    liveness derived from ``last_heartbeat_at``. A row reading
    ``ACTIVE`` + ``offline`` is meaningful and common - it is a candidate who
    was answering when their machine dropped.
    """

    id: UUID
    student_id: UUID = Field(alias="studentId")
    student_name: str = Field(alias="studentName")
    registration_no: str = Field(alias="registrationNo")
    machine_id: str | None = Field(default=None, alias="machineId")
    status: SessionStatus
    connection: ConnectionState
    checked_in_at: datetime | None = Field(default=None, alias="checkedInAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    submitted_at: datetime | None = Field(default=None, alias="submittedAt")
    last_heartbeat_at: datetime | None = Field(default=None, alias="lastHeartbeatAt")
    warning_count: int = Field(default=0, alias="warningCount")
    answered_count: int = Field(default=0, alias="answeredCount")


class MonitorSummary(Schema):
    """Server-computed aggregates.

    Computed server-side rather than reduced in the browser because the monitor
    must stay correct when a lab has 200 sessions and the client is only
    holding a page of them.
    """

    enrolled: int
    online: int
    active: int
    submitted: int
    warnings: int
    disconnected: int


class MonitorSnapshot(Schema):
    exam_id: UUID = Field(alias="examId")
    summary: MonitorSummary
    rows: list[SessionRow]
    #: Monotonic per-exam sequence. A websocket client that sees a gap refetches
    #: rather than silently drifting out of sync.
    seq: int


class ActivityEntry(Schema):
    at: datetime
    event: str
    severity: str
    detail: str | None = None


class SessionDetail(SessionRow):
    """Drill-down for one candidate, including their event timeline."""

    exam_id: UUID = Field(alias="examId")
    activity: list[ActivityEntry] = Field(default_factory=list)


class CheckInRequest(Schema):
    """Sent by the candidate's client on entering the waiting room.

    The machine identifier is reported by the lab client, not typed by the
    candidate - binding a student to a workstation is the client's job.
    """

    machine_id: str | None = Field(default=None, alias="machineId")


class SessionPaper(Schema):
    """Everything the candidate's exam screen needs, and nothing more.

    Questions are :class:`StudentQuestionOut`, which has no answer-key field at
    all. Ordering is this candidate's persisted shuffle.
    """

    session_id: UUID = Field(alias="sessionId")
    exam_id: UUID = Field(alias="examId")
    exam_title: str = Field(alias="examTitle")
    exam_code: str = Field(alias="examCode")
    instructions: list[str] = Field(default_factory=list)
    status: SessionStatus
    config: ExamConfig
    #: The authoritative deadline. The client derives remaining time from this
    #: plus its server-time offset, never from its own clock.
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    questions: list[StudentQuestionOut] = Field(default_factory=list)


class SessionState(Schema):
    """Reconnect recovery payload.

    After a network drop the client asks for this and reconciles: it holds the
    server's view of every saved answer, so a client that missed acknowledgements
    can tell what actually landed.
    """

    session_id: UUID = Field(alias="sessionId")
    status: SessionStatus
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    answers: dict[str, AnswerValue] = Field(default_factory=dict)
    flagged: list[UUID] = Field(default_factory=list)
    server_seq: int = Field(alias="serverSeq")


class SaveAnswerRequest(Schema):
    value: AnswerValue
    #: Client-side monotonic counter. Lets the server discard a stale write that
    #: arrives out of order after a reconnect, without needing a clock.
    client_seq: int = Field(default=0, ge=0, alias="clientSeq")


class SaveAnswerResponse(Schema):
    question_id: UUID = Field(alias="questionId")
    saved_at: datetime = Field(alias="savedAt")
    accepted: bool = Field(
        description="False when a newer write already won; the client should refetch state."
    )


class SubmitRequest(Schema):
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class SubmissionReceipt(Schema):
    """Returned by submit, and re-returned verbatim on a repeat submit."""

    session_id: UUID = Field(alias="sessionId")
    submission_id: UUID = Field(alias="submissionId")
    submitted_at: datetime = Field(alias="submittedAt")
    mode: SubmitMode
    answered_count: int = Field(alias="answeredCount")
    question_count: int = Field(alias="questionCount")
    flagged_count: int = Field(alias="flaggedCount")


class HeartbeatRequest(Schema):
    """Posted by the lab client on an interval.

    ``occurred_at`` is what the client believes; the server records its own
    arrival time separately, so a skewed or manipulated client clock is visible
    in the data rather than trusted.
    """

    machine_id: str = Field(alias="machineId")
    session_id: UUID | None = Field(default=None, alias="sessionId")
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")


class SessionEventRequest(Schema):
    """Invigilation signal reported by the lab client.

    A focus loss is recorded as evidence and raises a warning count. It is never
    treated, on its own, as proof of misconduct - faculty decide what a pattern
    means.
    """

    event: str
    occurred_at: datetime = Field(alias="occurredAt")
    detail: str | None = Field(default=None, max_length=1_000)
