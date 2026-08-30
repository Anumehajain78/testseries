"""State machine tests.

The transition tables are the spine of the system, so they get tested before
anything is wired to a database. These assertions are about *policy*, not
implementation, and should survive every later refactor.
"""

import pytest

from app.domain.transitions import (
    EXAM_TRANSITIONS,
    SESSION_TRANSITIONS,
    SWEEPABLE_TO_AUTO_SUBMIT,
    SWEEPABLE_TO_TERMINATED,
    IllegalTransition,
    accepts_candidate_writes,
    assert_exam_move,
    assert_session_move,
    can_exam_move,
    can_session_move,
)
from app.schemas.enums import (
    TERMINAL_EXAM_STATUSES,
    TERMINAL_SESSION_STATUSES,
    ExamStatus,
    SessionStatus,
)


class TestExamLifecycle:
    def test_every_status_has_an_entry(self):
        assert set(EXAM_TRANSITIONS) == set(ExamStatus)

    def test_happy_path_is_reachable_end_to_end(self):
        path = [
            ExamStatus.DRAFT,
            ExamStatus.SCHEDULED,
            ExamStatus.READY,
            ExamStatus.LIVE,
            ExamStatus.ENDING,
            ExamStatus.COMPLETED,
        ]
        for current, nxt in zip(path, path[1:]):
            assert can_exam_move(current, nxt), f"{current} -> {nxt} should be legal"

    def test_terminal_states_go_nowhere(self):
        for status in TERMINAL_EXAM_STATUSES:
            assert EXAM_TRANSITIONS[status] == frozenset()

    def test_cannot_skip_straight_from_draft_to_live(self):
        # An exam must be scheduled and seated before it can be started;
        # otherwise there is no roster to release.
        assert not can_exam_move(ExamStatus.DRAFT, ExamStatus.LIVE)

    def test_cannot_reopen_a_completed_exam(self):
        assert not can_exam_move(ExamStatus.COMPLETED, ExamStatus.LIVE)

    def test_a_live_exam_cannot_return_to_scheduled(self):
        assert not can_exam_move(ExamStatus.LIVE, ExamStatus.SCHEDULED)

    def test_cancellation_is_available_before_completion(self):
        for status in (ExamStatus.DRAFT, ExamStatus.SCHEDULED, ExamStatus.READY, ExamStatus.LIVE):
            assert can_exam_move(status, ExamStatus.CANCELLED)

    def test_illegal_move_names_both_states(self):
        with pytest.raises(IllegalTransition) as excinfo:
            assert_exam_move(ExamStatus.COMPLETED, ExamStatus.LIVE)
        assert excinfo.value.current == ExamStatus.COMPLETED
        assert excinfo.value.requested == ExamStatus.LIVE


class TestSessionLifecycle:
    def test_every_status_has_an_entry(self):
        assert set(SESSION_TRANSITIONS) == set(SessionStatus)

    def test_happy_path_is_reachable_end_to_end(self):
        path = [
            SessionStatus.NOT_STARTED,
            SessionStatus.WAITING,
            SessionStatus.READY,
            SessionStatus.ACTIVE,
            SessionStatus.SUBMITTED,
        ]
        for current, nxt in zip(path, path[1:]):
            assert can_session_move(current, nxt), f"{current} -> {nxt} should be legal"

    def test_terminal_states_go_nowhere(self):
        for status in TERMINAL_SESSION_STATUSES:
            assert SESSION_TRANSITIONS[status] == frozenset()

    def test_readiness_can_regress_before_the_exam_starts(self):
        # A workstation dropping off must be able to un-ready a candidate,
        # or the roster would lie to the invigilator.
        assert can_session_move(SessionStatus.READY, SessionStatus.WAITING)

    def test_a_submitted_session_cannot_become_active_again(self):
        assert not can_session_move(SessionStatus.SUBMITTED, SessionStatus.ACTIVE)

    def test_a_candidate_cannot_jump_into_the_paper_unchecked(self):
        assert not can_session_move(SessionStatus.NOT_STARTED, SessionStatus.ACTIVE)

    def test_illegal_move_raises(self):
        with pytest.raises(IllegalTransition):
            assert_session_move(SessionStatus.SUBMITTED, SessionStatus.ACTIVE)


class TestDeadlineSweep:
    def test_only_active_sessions_are_auto_submitted(self):
        assert SWEEPABLE_TO_AUTO_SUBMIT == frozenset({SessionStatus.ACTIVE})

    def test_a_candidate_who_never_entered_is_terminated_not_auto_submitted(self):
        # An empty submission must never be confused with an absent candidate:
        # one sat the exam and answered nothing, the other never turned up.
        assert SessionStatus.NOT_STARTED in SWEEPABLE_TO_TERMINATED
        assert SessionStatus.NOT_STARTED not in SWEEPABLE_TO_AUTO_SUBMIT

    def test_sweep_sets_are_disjoint(self):
        assert not (SWEEPABLE_TO_AUTO_SUBMIT & SWEEPABLE_TO_TERMINATED)

    def test_sweep_covers_every_non_terminal_status(self):
        covered = SWEEPABLE_TO_AUTO_SUBMIT | SWEEPABLE_TO_TERMINATED | TERMINAL_SESSION_STATUSES
        assert covered == set(SessionStatus), "the sweep would leave a session stuck"


class TestCandidateWrites:
    def test_writes_need_both_axes_to_agree(self):
        assert accepts_candidate_writes(ExamStatus.LIVE, SessionStatus.ACTIVE)

    def test_writes_are_refused_once_the_deadline_passes(self):
        # ENDING is the sweep window: the clock has run out even though the
        # exam is not yet closed.
        assert not accepts_candidate_writes(ExamStatus.ENDING, SessionStatus.ACTIVE)

    def test_writes_are_refused_before_release(self):
        assert not accepts_candidate_writes(ExamStatus.READY, SessionStatus.READY)

    def test_a_submitted_candidate_cannot_keep_answering(self):
        assert not accepts_candidate_writes(ExamStatus.LIVE, SessionStatus.SUBMITTED)

    def test_a_terminated_candidate_cannot_keep_answering(self):
        assert not accepts_candidate_writes(ExamStatus.LIVE, SessionStatus.TERMINATED)
