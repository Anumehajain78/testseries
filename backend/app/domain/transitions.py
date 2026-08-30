"""Legal state transitions.

The frontend may *request* a transition; it may never assert one. Keeping the
adjacency here means an illegal move is a lookup failure rather than a missing
``if`` somewhere in a route handler, and the same table can be asserted against
in tests and rendered into documentation.
"""

from app.schemas.enums import ExamStatus, SessionStatus

# --------------------------------------------------------------------------
# Exam lifecycle
# --------------------------------------------------------------------------

EXAM_TRANSITIONS: dict[ExamStatus, frozenset[ExamStatus]] = {
    ExamStatus.DRAFT: frozenset({ExamStatus.SCHEDULED, ExamStatus.CANCELLED}),
    # Scheduling seats the roster; READY is reached once every enrolled
    # candidate has a session, which is what faculty review before starting.
    ExamStatus.SCHEDULED: frozenset({ExamStatus.READY, ExamStatus.DRAFT, ExamStatus.CANCELLED}),
    ExamStatus.READY: frozenset({ExamStatus.LIVE, ExamStatus.SCHEDULED, ExamStatus.CANCELLED}),
    # ENDING is entered by the scheduler at ends_at, or by faculty closing early.
    ExamStatus.LIVE: frozenset({ExamStatus.ENDING, ExamStatus.CANCELLED}),
    ExamStatus.ENDING: frozenset({ExamStatus.COMPLETED}),
    ExamStatus.COMPLETED: frozenset(),
    ExamStatus.CANCELLED: frozenset(),
}

# --------------------------------------------------------------------------
# Candidate session lifecycle
# --------------------------------------------------------------------------

SESSION_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    # The row is created when the exam is scheduled, before the candidate
    # has done anything.
    SessionStatus.NOT_STARTED: frozenset({SessionStatus.WAITING, SessionStatus.TERMINATED}),
    SessionStatus.WAITING: frozenset({SessionStatus.READY, SessionStatus.TERMINATED}),
    # READY -> WAITING is legal: a readiness check can start failing again
    # (machine drops off) before the exam is released.
    SessionStatus.READY: frozenset(
        {SessionStatus.ACTIVE, SessionStatus.WAITING, SessionStatus.TERMINATED}
    ),
    SessionStatus.ACTIVE: frozenset(
        {
            SessionStatus.SUBMITTED,
            SessionStatus.AUTO_SUBMITTED,
            SessionStatus.TERMINATED,
        }
    ),
    SessionStatus.SUBMITTED: frozenset(),
    SessionStatus.AUTO_SUBMITTED: frozenset(),
    SessionStatus.TERMINATED: frozenset(),
}

# Statuses from which the deadline sweep may auto-submit. A candidate who never
# entered the paper is swept to TERMINATED rather than AUTO_SUBMITTED, so an
# empty submission is never confused with an absent one.
SWEEPABLE_TO_AUTO_SUBMIT = frozenset({SessionStatus.ACTIVE})
SWEEPABLE_TO_TERMINATED = frozenset(
    {SessionStatus.NOT_STARTED, SessionStatus.WAITING, SessionStatus.READY}
)


class IllegalTransition(Exception):
    """Raised when a caller requests a move the state machine forbids."""

    def __init__(self, entity: str, current: str, requested: str) -> None:
        super().__init__(f"{entity}: {current} -> {requested} is not a legal transition")
        self.entity = entity
        self.current = current
        self.requested = requested


def can_exam_move(current: ExamStatus, requested: ExamStatus) -> bool:
    return requested in EXAM_TRANSITIONS[current]


def assert_exam_move(current: ExamStatus, requested: ExamStatus) -> None:
    if not can_exam_move(current, requested):
        raise IllegalTransition("exam", current, requested)


def can_session_move(current: SessionStatus, requested: SessionStatus) -> bool:
    return requested in SESSION_TRANSITIONS[current]


def assert_session_move(current: SessionStatus, requested: SessionStatus) -> None:
    if not can_session_move(current, requested):
        raise IllegalTransition("session", current, requested)


def accepts_candidate_writes(exam: ExamStatus, session: SessionStatus) -> bool:
    """Whether an answer may be saved right now.

    Both axes must agree. This is the single rule behind every answer and flag
    endpoint - the UI's navigation lock and disabled buttons are convenience,
    not enforcement.
    """
    return exam is ExamStatus.LIVE and session is SessionStatus.ACTIVE
