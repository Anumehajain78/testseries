"""Question models.

The central rule of this module: **there are two question models, and only one
of them can reach a candidate.**

The frontend currently ships answer keys to the browser - during a live exam
``correctOption`` is readable from DevTools. Making the candidate payload a
structurally different type, rather than the same model with a flag or an
excluded field, means there is no field to forget to exclude. A reviewer can
verify the guarantee by reading the class definition.
"""

from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema
from app.schemas.enums import QuestionType


class OptionIn(Schema):
    body: str = Field(min_length=1, max_length=2_000)
    is_correct: bool = Field(default=False, alias="isCorrect")


class QuestionIn(Schema):
    """Authoring payload. Faculty scope only."""

    type: QuestionType
    prompt: str = Field(min_length=1, max_length=8_000)
    marks: int = Field(ge=1, le=100)
    course: str | None = None
    options: list[OptionIn] = Field(
        default_factory=list,
        description="Empty for text questions; at least two entries otherwise.",
    )


class OptionOut(Schema):
    """Faculty-facing option. Carries the answer key."""

    id: UUID
    position: int
    body: str
    is_correct: bool = Field(alias="isCorrect")


class QuestionOut(Schema):
    """Faculty-facing question. Carries the answer key.

    Returned by ``GET /exams/{id}`` and the question-bank endpoints, all of
    which require an ADMIN or FACULTY subject.
    """

    id: UUID
    type: QuestionType
    prompt: str
    marks: int
    course: str | None = None
    options: list[OptionOut] = Field(default_factory=list)


class StudentOptionOut(Schema):
    """Candidate-facing option.

    No ``is_correct``. The field does not exist on this model, so no serializer
    setting, response_model override, or future refactor can leak it.

    ``position`` is this candidate's shuffled position, not the authored one.
    """

    id: UUID
    position: int
    body: str


class StudentQuestionOut(Schema):
    """Candidate-facing question.

    Ordering reflects the per-session shuffle materialized at check-in, so the
    paper is stable across reconnects. Marks are shown because candidates are
    told what each question is worth; nothing here reveals the answer.
    """

    id: UUID
    type: QuestionType
    prompt: str
    marks: int
    position: int = Field(description="Position in this candidate's paper, not the authored order.")
    options: list[StudentOptionOut] = Field(default_factory=list)
