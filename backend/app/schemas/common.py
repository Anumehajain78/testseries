"""Shared building blocks."""

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Schema(BaseModel):
    """Base for every model in the contract.

    ``populate_by_name`` lets the API speak camelCase on the wire while the
    Python stays snake_case, so the generated TypeScript reads naturally in the
    frontend without a translation layer on either side.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ServerTime(Schema):
    """Every response carries the server clock.

    The client stores a single offset from this and derives all remaining-time
    maths from it, so a candidate changing their workstation clock has no
    effect on when their exam ends.
    """

    server_time: datetime = Field(
        alias="serverTime",
        description="Authoritative UTC time at the moment the response was produced.",
    )


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Answers
#
# Discriminated union mirroring the frontend's AnswerValue, so the wire format
# and the existing client type are the same shape.
# ---------------------------------------------------------------------------


class SingleAnswer(Schema):
    kind: Literal["single"] = "single"
    option: int = Field(ge=0, description="Index into the options as ordered for this candidate.")


class MultipleAnswer(Schema):
    kind: Literal["multiple"] = "multiple"
    options: list[int] = Field(default_factory=list)


class TextAnswer(Schema):
    kind: Literal["text"] = "text"
    text: str = Field(max_length=20_000)


AnswerValue = Annotated[
    SingleAnswer | MultipleAnswer | TextAnswer,
    Field(discriminator="kind"),
]


class ErrorDetail(Schema):
    """Uniform error body.

    ``code`` is stable and machine-readable; ``message`` is for humans and may
    change. Transition failures carry the states involved so the client can say
    something useful rather than 'something went wrong'.
    """

    code: str
    message: str
    current_state: str | None = Field(default=None, alias="currentState")
    requested_state: str | None = Field(default=None, alias="requestedState")
