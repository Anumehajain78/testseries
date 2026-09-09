"""Paper ordering and grading.

Pure functions, so these run without a database. They cover the translation
that makes a shuffled paper gradable: a candidate answers in their own
coordinates, and the server has to map back before it can judge anything.
"""

from uuid import uuid4

from app.domain.paper import (
    AuthoredOption,
    AuthoredQuestion,
    draw_paper,
    presented_options,
    score_paper,
    score_question,
    to_authored_positions,
)
from app.schemas.enums import QuestionType


def question(*, correct: set[int], count: int = 4, marks: int = 2, qtype=QuestionType.MCQ):
    return AuthoredQuestion(
        id=uuid4(),
        type=qtype,
        prompt="?",
        marks=marks,
        options=tuple(
            AuthoredOption(uuid4(), i, f"option {i}", i in correct) for i in range(count)
        ),
    )


class TestDraw:
    def test_the_same_session_always_draws_the_same_paper(self):
        """Seeded by session id, so a reconnect is not a reshuffle."""
        questions = [question(correct={0}) for _ in range(6)]
        a = draw_paper(questions, seed="session-1", randomize_questions=True, randomize_options=True)
        b = draw_paper(questions, seed="session-1", randomize_questions=True, randomize_options=True)
        assert a == b

    def test_different_candidates_get_different_papers(self):
        questions = [question(correct={0}) for _ in range(8)]
        a, _ = draw_paper(questions, seed="session-1", randomize_questions=True, randomize_options=False)
        b, _ = draw_paper(questions, seed="session-2", randomize_questions=True, randomize_options=False)
        assert a != b

    def test_without_randomization_the_authored_order_is_kept(self):
        questions = [question(correct={0}) for _ in range(4)]
        order, options = draw_paper(
            questions, seed="s", randomize_questions=False, randomize_options=False
        )
        assert order == [str(q.id) for q in questions]
        assert all(positions == [0, 1, 2, 3] for positions in options.values())

    def test_a_subset_is_drawn_after_shuffling(self):
        """Otherwise every candidate sits the same first N questions."""
        questions = [question(correct={0}) for _ in range(10)]
        a, _ = draw_paper(
            questions, seed="s1", randomize_questions=True, randomize_options=False,
            questions_per_student=4,
        )
        b, _ = draw_paper(
            questions, seed="s2", randomize_questions=True, randomize_options=False,
            questions_per_student=4,
        )
        assert len(a) == len(b) == 4
        assert set(a) != set(b)

    def test_text_questions_are_never_option_shuffled(self):
        text = question(correct=set(), count=0, qtype=QuestionType.TEXT)
        _, options = draw_paper([text], seed="s", randomize_questions=False, randomize_options=True)
        assert options[str(text.id)] == []


class TestTranslation:
    def test_candidate_indices_map_back_to_authored_positions(self):
        # The candidate sees authored option 2 first, so their index 0 is
        # authored position 2.
        assert to_authored_positions([2, 0, 3, 1], [0]) == {2}
        assert to_authored_positions([2, 0, 3, 1], [1, 3]) == {0, 1}

    def test_an_out_of_range_index_is_dropped_rather_than_raising(self):
        """A malformed answer scores zero; it does not break the whole room."""
        assert to_authored_positions([2, 0, 3, 1], [9]) == set()

    def test_presented_options_follow_the_stored_order(self):
        q = question(correct={0})
        shown = presented_options(q, [3, 1, 0, 2])
        assert [option.position for option in shown] == [3, 1, 0, 2]

    def test_a_session_with_no_stored_order_falls_back_to_authored(self):
        q = question(correct={0})
        assert [o.position for o in presented_options(q, None)] == [0, 1, 2, 3]


class TestScoring:
    def test_a_correct_single_answer_scores_full_marks_through_the_shuffle(self):
        q = question(correct={1}, marks=3)
        # Candidate index 0 is authored position 1 — the correct one.
        assert score_question(q, [1, 0, 2, 3], {"kind": "single", "option": 0}) == 3.0

    def test_a_wrong_single_answer_scores_nothing(self):
        q = question(correct={1}, marks=3)
        assert score_question(q, [1, 0, 2, 3], {"kind": "single", "option": 1}) == 0.0

    def test_multiple_response_is_all_or_nothing(self):
        q = question(correct={0, 2}, marks=4)
        assert score_question(q, None, {"kind": "multiple", "options": [0, 2]}) == 4.0
        # A partially correct selection earns nothing: partial credit is a
        # policy decision, not a default.
        assert score_question(q, None, {"kind": "multiple", "options": [0]}) == 0.0
        assert score_question(q, None, {"kind": "multiple", "options": [0, 1, 2]}) == 0.0

    def test_an_unmarked_written_answer_scores_nothing_yet(self):
        q = question(correct=set(), count=0, marks=5, qtype=QuestionType.TEXT)
        assert score_question(q, None, {"kind": "text", "text": "anything"}) == 0.0

    def test_a_marked_written_answer_scores_what_it_was_given(self):
        q = question(correct=set(), count=0, marks=5, qtype=QuestionType.TEXT)
        assert score_question(q, None, {"kind": "text", "text": "a good answer"}, 4.0) == 4.0

    def test_an_unread_written_answer_is_counted_as_pending(self):
        """A total that treats unread work as nought reads as a finished
        result. The count is how the screens avoid saying that."""
        written = question(correct=set(), count=0, marks=5, qtype=QuestionType.TEXT)
        bank = {str(written.id): written}
        given, available, pending = score_paper(
            bank, [str(written.id)], None, {str(written.id): {"kind": "text", "text": "words"}}
        )
        assert (given, available, pending) == (0.0, 5.0, 1)

    def test_marking_it_clears_the_pending_count(self):
        written = question(correct=set(), count=0, marks=5, qtype=QuestionType.TEXT)
        bank = {str(written.id): written}
        given, available, pending = score_paper(
            bank, [str(written.id)], None,
            {str(written.id): {"kind": "text", "text": "words"}},
            {str(written.id): 3.5},
        )
        assert (given, available, pending) == (3.5, 5.0, 0)

    def test_an_unanswered_written_question_is_not_pending(self):
        """Nobody needs to read a blank."""
        written = question(correct=set(), count=0, marks=5, qtype=QuestionType.TEXT)
        bank = {str(written.id): written}
        _, _, pending = score_paper(bank, [str(written.id)], None, {})
        assert pending == 0

    def test_an_unanswered_question_scores_nothing(self):
        assert score_question(question(correct={0}), None, None) == 0.0

    def test_a_paper_is_scored_out_of_its_own_marks(self):
        """With questions_per_student two candidates sit different papers, so
        each is scored against their own total rather than the whole bank."""
        a, b, c = question(correct={0}, marks=2), question(correct={0}, marks=3), question(correct={0}, marks=5)
        bank = {str(q.id): q for q in (a, b, c)}
        awarded, available, pending = score_paper(
            bank, [str(a.id), str(b.id)], None, {str(a.id): {"kind": "single", "option": 0}}
        )
        assert (awarded, available, pending) == (2.0, 5.0, 0)

    def test_a_score_can_never_exceed_the_available_marks(self):
        a = question(correct={0}, marks=2)
        bank = {str(a.id): a}
        awarded, available, _ = score_paper(
            bank, [str(a.id)], None, {str(a.id): {"kind": "single", "option": 0}}
        )
        assert awarded <= available
