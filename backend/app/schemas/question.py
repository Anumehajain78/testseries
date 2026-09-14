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


class TestCaseIn(Schema):
    """One test case for a coding question. Faculty scope only."""

    stdin: str = Field(default="", max_length=20_000)
    #: Required, with no default. An empty expected output is occasionally
    #: what a question wants, but it must never be what a question gets by
    #: accident: a case defaulting to "" awards marks to any program that
    #: prints nothing at all, including one that crashes before its first line.
    expected_stdout: str = Field(max_length=20_000, alias="expectedStdout")
    #: Hidden cases are the answer key. A visible one is a worked example.
    hidden: bool = True
    weight: int = Field(default=1, ge=1, le=100)


class QuestionIn(Schema):
    """Authoring payload. Faculty scope only."""

    type: QuestionType
    prompt: str = Field(min_length=1, max_length=8_000)
    marks: int = Field(ge=1, le=100)
    course: str | None = None
    options: list[OptionIn] = Field(
        default_factory=list,
        description="Empty for text and coding questions; at least two entries otherwise.",
    )
    # Coding questions only.
    language: str | None = Field(default=None, max_length=40)
    starter_code: str | None = Field(default=None, max_length=20_000, alias="starterCode")
    time_limit_ms: int | None = Field(default=None, ge=100, le=30_000, alias="timeLimitMs")
    memory_limit_mb: int | None = Field(default=None, ge=16, le=1_024, alias="memoryLimitMb")
    tests: list[TestCaseIn] = Field(default_factory=list)


class OptionOut(Schema):
    """Faculty-facing option. Carries the answer key."""

    id: UUID
    position: int
    body: str
    is_correct: bool = Field(alias="isCorrect")


class TestCaseOut(Schema):
    """Faculty-facing test case. Carries the expected output."""

    id: UUID
    position: int
    stdin: str
    expected_stdout: str = Field(alias="expectedStdout")
    hidden: bool
    weight: int


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
    language: str | None = None
    starter_code: str | None = Field(default=None, alias="starterCode")
    time_limit_ms: int | None = Field(default=None, alias="timeLimitMs")
    memory_limit_mb: int | None = Field(default=None, alias="memoryLimitMb")
    tests: list[TestCaseOut] = Field(default_factory=list)


class StudentOptionOut(Schema):
    """Candidate-facing option.

    No ``is_correct``. The field does not exist on this model, so no serializer
    setting, response_model override, or future refactor can leak it.

    ``position`` is this candidate's shuffled position, not the authored one.
    """

    id: UUID
    position: int
    body: str


class StudentTestCaseOut(Schema):
    """Candidate-facing test case — a worked example, nothing more.

    No ``expected_stdout``, for the same structural reason ``StudentOptionOut``
    has no ``is_correct``: a coding question's expected outputs *are* its answer
    key, and a candidate who can read them can print them without solving
    anything. Hidden cases never reach this model at all; visible ones arrive
    stripped of their answer, so a candidate sees the shape of the input and
    has to work out what comes back.
    """

    position: int
    stdin: str


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
    #: Coding questions only, and null otherwise.
    language: str | None = None
    starter_code: str | None = Field(default=None, alias="starterCode")
    tests: list[StudentTestCaseOut] = Field(default_factory=list)
