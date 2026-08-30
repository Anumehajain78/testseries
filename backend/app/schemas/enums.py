"""Domain enumerations.

These are the vocabulary the whole contract is written in, so they live in one
module rather than beside the models that happen to use them first.

The two lifecycle enums are deliberately narrow: every value is a state the
server can be asked to justify, and every transition between them is guarded in
one place (``app.domain.transitions``) rather than inferred from booleans
scattered across the codebase.
"""

from enum import StrEnum


class Role(StrEnum):
    """Who a human principal is. Machines are not users - a lab workstation
    authenticates with its own credential and carries ``subject_type=machine``,
    so it never appears in a roster or owns an exam."""

    ADMIN = "ADMIN"
    FACULTY = "FACULTY"
    STUDENT = "STUDENT"


class SubjectType(StrEnum):
    """What kind of principal a token represents."""

    USER = "user"
    MACHINE = "machine"


class ExamStatus(StrEnum):
    """Exam lifecycle.

    ``READY`` exists because seating the roster is a real transition with
    observable consequences - faculty review candidate readiness in that state,
    before anyone is released into the paper.

    ``ENDING`` is the deadline sweep window: the clock has run out and the
    server is auto-submitting stragglers, but the exam is not yet closed.
    Candidate writes are refused from the moment this state is entered.
    """

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    READY = "READY"
    LIVE = "LIVE"
    ENDING = "ENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SessionStatus(StrEnum):
    """Per-candidate lifecycle.

    Note what is absent: there is no ``DISCONNECTED`` member. Liveness is a
    separate axis (:class:`ConnectionState`) derived from the heartbeat, so a
    candidate can be correctly described as "ACTIVE but offline for 40s".
    Folding the two together would lose what the candidate was doing when the
    network dropped, which is exactly what an invigilator needs to know.
    """

    NOT_STARTED = "NOT_STARTED"
    WAITING = "WAITING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    SUBMITTED = "SUBMITTED"
    AUTO_SUBMITTED = "AUTO_SUBMITTED"
    TERMINATED = "TERMINATED"


TERMINAL_SESSION_STATUSES = frozenset(
    {SessionStatus.SUBMITTED, SessionStatus.AUTO_SUBMITTED, SessionStatus.TERMINATED}
)

TERMINAL_EXAM_STATUSES = frozenset({ExamStatus.COMPLETED, ExamStatus.CANCELLED})


class ConnectionState(StrEnum):
    """Derived liveness, never stored.

    Computed from ``now - last_heartbeat_at`` against two thresholds, so it is
    always current rather than as-of the last write.
    """

    ONLINE = "online"
    WARNING = "warning"
    OFFLINE = "offline"


class QuestionType(StrEnum):
    MCQ = "mcq"
    MULTIPLE = "multiple"
    TEXT = "text"


class SubmitMode(StrEnum):
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    TERMINATED = "TERMINATED"


class AuditSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AuditCategory(StrEnum):
    AUTH = "AUTH"
    EXAM = "EXAM"
    SESSION = "SESSION"
    CONNECTION = "CONNECTION"
    SYSTEM = "SYSTEM"


class AuditEventType(StrEnum):
    """Append-only event vocabulary.

    Deliberately includes the invigilation signals the lab client will report
    once it exists. ``FOCUS_LOST`` is recorded as evidence and contributes to a
    warning count; it is never treated as proof of anything on its own.
    """

    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXAM_CREATED = "EXAM_CREATED"
    EXAM_SCHEDULED = "EXAM_SCHEDULED"
    EXAM_STARTED = "EXAM_STARTED"
    EXAM_ENDED = "EXAM_ENDED"
    EXAM_CANCELLED = "EXAM_CANCELLED"
    SESSION_CHECKED_IN = "SESSION_CHECKED_IN"
    CONNECTION_LOST = "CONNECTION_LOST"
    CONNECTION_RESTORED = "CONNECTION_RESTORED"
    FOCUS_LOST = "FOCUS_LOST"
    FOCUS_RESTORED = "FOCUS_RESTORED"
    EXAM_CLIENT_CLOSED = "EXAM_CLIENT_CLOSED"
    ANSWER_SAVED = "ANSWER_SAVED"
    SUBMISSION = "SUBMISSION"
    AUTO_SUBMISSION = "AUTO_SUBMISSION"
    SESSION_TERMINATED = "SESSION_TERMINATED"
    RESULTS_PUBLISHED = "RESULTS_PUBLISHED"


class LabStatus(StrEnum):
    READY = "READY"
    OCCUPIED = "OCCUPIED"
    MAINTENANCE = "MAINTENANCE"


class StudentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class RealtimeEvent(StrEnum):
    """WebSocket frame types. Server-sent unless noted."""

    EXAM_STARTED = "EXAM_STARTED"
    EXAM_ENDING = "EXAM_ENDING"
    EXAM_ENDED = "EXAM_ENDED"
    SESSION_STATE_CHANGED = "SESSION_STATE_CHANGED"
    STUDENT_CONNECTED = "STUDENT_CONNECTED"
    STUDENT_DISCONNECTED = "STUDENT_DISCONNECTED"
    MACHINE_STATUS_CHANGED = "MACHINE_STATUS_CHANGED"
    WARNING = "WARNING"
    SUBMISSION = "SUBMISSION"
    FORCE_SUBMIT = "FORCE_SUBMIT"
    TERMINATED = "TERMINATED"
    ANSWER_ACK = "ANSWER_ACK"
    # client -> server
    HEARTBEAT = "HEARTBEAT"
    FOCUS_LOST = "FOCUS_LOST"
    FOCUS_RESTORED = "FOCUS_RESTORED"
    CLIENT_CLOSED = "CLIENT_CLOSED"
