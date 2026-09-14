"""Per-candidate paper ordering and grading.

Two ideas hold this module together.

**Ordering is drawn once and stored.** A candidate's question and option order
is decided at check-in and written to their session. If it were recomputed per
request, a reconnect would reshuffle the paper and every answer already saved
would point at a different question. Persisting it is the only way a shuffled
exam can survive a dropped network.

**The candidate answers in their own coordinates.** An option index the client
sends is a position in *their* shuffled list, not the authored one. Grading has
to translate back before it can ask whether an answer is correct — which is
also why the answer key never needs to leave the server.

Pure functions, so the rules can be tested without a database or an HTTP call.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from uuid import UUID

from app.schemas.enums import QuestionType


@dataclass(frozen=True)
class AuthoredOption:
    id: UUID
    position: int
    body: str
    is_correct: bool


#: Types whose marks arrive after the paper is submitted rather than during it.
#: A written answer waits for a person; a program waits for the runner. Either
#: way the total is incomplete until then, and saying so is the whole point of
#: the pending count — a paper that reports 0/20 while nobody has marked it
#: reads as a candidate who failed.
AWAITING_MARKS = frozenset({QuestionType.TEXT, QuestionType.CODING})


@dataclass(frozen=True)
class AuthoredTest:
    """A coding question's test case, as authored.

    Carries ``expected_stdout`` in the same way :class:`AuthoredOption` carries
    ``is_correct``: this is the server's own view. Stripping it is the job of
    the candidate-facing schema, which has no field for it.
    """

    position: int
    stdin: str
    expected_stdout: str
    hidden: bool
    weight: int


@dataclass(frozen=True)
class AuthoredQuestion:
    id: UUID
    type: QuestionType
    prompt: str
    marks: int
    options: tuple[AuthoredOption, ...]
    # Coding questions only.
    language: str | None = None
    starter_code: str | None = None
    tests: tuple[AuthoredTest, ...] = ()


def draw_paper(
    questions: list[AuthoredQuestion],
    *,
    seed: str,
    randomize_questions: bool,
    randomize_options: bool,
    questions_per_student: int = 0,
) -> tuple[list[str], dict[str, list[int]]]:
    """Decide one candidate's paper.

    Returns the question order as ids, and for each question the authored
    option positions in the order that candidate will see them.

    Seeded by the session id, so the same candidate re-checking in gets the
    same paper — the draw is stable even though it looks random.
    """
    rng = random.Random(seed)

    ordered = list(questions)
    if randomize_questions:
        rng.shuffle(ordered)

    # A subset is drawn *after* shuffling, so every candidate can get a
    # different selection rather than the same first N in a different order.
    if questions_per_student and 0 < questions_per_student < len(ordered):
        ordered = ordered[:questions_per_student]

    option_order: dict[str, list[int]] = {}
    for question in ordered:
        positions = [option.position for option in question.options]
        # Only questions that *have* options can have them shuffled. Naming the
        # types would mean editing this every time one is added.
        if randomize_options and question.options:
            rng.shuffle(positions)
        option_order[str(question.id)] = positions

    return [str(question.id) for question in ordered], option_order


def presented_options(
    question: AuthoredQuestion, order: list[int] | None
) -> list[AuthoredOption]:
    """The options as this candidate sees them.

    Falls back to authored order when no shuffle was stored, so a session
    created before randomization was enabled still renders.
    """
    by_position = {option.position: option for option in question.options}
    if not order:
        return sorted(question.options, key=lambda option: option.position)
    return [by_position[position] for position in order if position in by_position]


def to_authored_positions(order: list[int] | None, chosen: list[int]) -> set[int]:
    """Translate the candidate's option indices into authored positions.

    ``chosen`` are indices into the candidate's shuffled list. Anything out of
    range is dropped rather than raising: a malformed answer should score zero,
    not break grading for the whole room.
    """
    if not order:
        return {index for index in chosen if index >= 0}
    return {order[index] for index in chosen if 0 <= index < len(order)}


def score_question(
    question: AuthoredQuestion,
    order: list[int] | None,
    value: dict | None,
    awarded: float | None = None,
) -> float:
    """Marks awarded for one answer.

    Multiple-response is all-or-nothing: the selection must match the key
    exactly. Partial credit is a policy decision with real consequences for a
    cohort, so it is not something to introduce by accident here.

    Text answers are never auto-scored — they carry zero until a human marks
    them, rather than being silently counted wrong.
    """
    if value is None:
        return 0.0

    kind = value.get("kind")
    correct = {option.position for option in question.options if option.is_correct}

    if kind == "single":
        option = value.get("option")
        if not isinstance(option, int):
            return 0.0
        chosen = to_authored_positions(order, [option])
        return float(question.marks) if chosen and chosen <= correct else 0.0

    if kind == "multiple":
        options = value.get("options") or []
        if not isinstance(options, list):
            return 0.0
        chosen = to_authored_positions(order, [o for o in options if isinstance(o, int)])
        return float(question.marks) if chosen == correct and correct else 0.0

    # Neither of these is scored while the paper is being sat. A written answer
    # waits for a person; a program waits for the runner, because executing it
    # takes seconds and a room submits at once. Until the award arrives it is
    # None, which is not the same as nought — see `score_paper`.
    if kind in ("text", "code"):
        return float(awarded) if awarded is not None else 0.0

    return 0.0


def score_paper(
    questions: dict[str, AuthoredQuestion],
    question_order: list[str] | None,
    option_order: dict[str, list[int]] | None,
    answers: dict[str, dict],
    awards: dict[str, float | None] | None = None,
) -> tuple[float, float, int]:
    """Total awarded, total available, and how many answers are still unmarked.

    The third number covers both written answers waiting for a person and
    programs waiting for the runner: what they have in common is that the total
    is not final yet, which is the only thing a results screen needs to know.

    The maximum is the marks on *their* paper, not the whole bank — with
    ``questions_per_student`` two candidates can legitimately sit different
    numbers of questions, and each must be scored out of their own total.

    A written answer nobody has read yet contributes nothing, and a total that
    quietly treats it as zero
    would read as a finished result. Callers use the count to say "marking
    pending" rather than publishing a score that is not yet true.
    """
    ids = question_order or list(questions)
    given = 0.0
    available = 0.0
    unmarked = 0
    for question_id in ids:
        question = questions.get(question_id)
        if question is None:
            continue
        available += float(question.marks)
        award = (awards or {}).get(question_id)
        if question.type in AWAITING_MARKS and answers.get(question_id) and award is None:
            unmarked += 1
        given += score_question(
            question, (option_order or {}).get(question_id), answers.get(question_id), award
        )
    return given, available, unmarked
