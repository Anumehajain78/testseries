"""Grading and results."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import Schema
from app.schemas.enums import SubmitMode


class ResultRow(Schema):
    """One ranked result.

    ``score`` is null while results are unpublished. The frontend's
    ``mockResultMode`` switch was standing in for exactly this: grading and
    publication are separate events, and a score exists before a candidate is
    allowed to see it.
    """

    rank: int = Field(ge=1)
    session_id: UUID = Field(alias="sessionId")
    student_id: UUID = Field(alias="studentId")
    student_name: str = Field(alias="studentName")
    registration_no: str = Field(alias="registrationNo")
    score: float | None = None
    max_score: float = Field(alias="maxScore")
    percentage: float | None = None
    time_taken_seconds: int | None = Field(default=None, alias="timeTakenSeconds")
    mode: SubmitMode
    submitted_at: datetime = Field(alias="submittedAt")

    @model_validator(mode="after")
    def _score_within_bounds(self) -> "ResultRow":
        # Defence in depth. The grader clamps too, but a schema that can express
        # 63/60 is a schema that will eventually emit it.
        if self.score is not None and self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        if self.score is not None and self.score < 0:
            raise ValueError("score cannot be negative")
        return self


class ResultStats(Schema):
    submitted: int
    graded: int
    average_percentage: float | None = Field(default=None, alias="averagePercentage")
    highest_percentage: float | None = Field(default=None, alias="highestPercentage")


class ResultsPage(Schema):
    exam_id: UUID = Field(alias="examId")
    published: bool = Field(
        description="False means scores are withheld; rows omit score and percentage."
    )
    published_at: datetime | None = Field(default=None, alias="publishedAt")
    stats: ResultStats
    rows: list[ResultRow] = Field(default_factory=list)


class PublishResultsRequest(Schema):
    published: bool
