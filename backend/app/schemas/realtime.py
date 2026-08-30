"""WebSocket frame models.

These are declared as Pydantic models even though FastAPI will not generate
websocket routes into the OpenAPI document, because the frontend needs the
generated TypeScript for them just as much as for the REST payloads. They are
attached to the schema document explicitly in ``app.main``.

Every server frame carries ``seq`` and ``server_time``: a client that sees a
gap in the sequence refetches the monitor snapshot rather than silently
drifting, and one that has been asleep can recompute its clock offset.
"""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema
from app.schemas.enums import ConnectionState, RealtimeEvent, SessionStatus
from app.schemas.session import MonitorSummary


class ServerFrame(Schema):
    """Base envelope for everything the server pushes."""

    event: RealtimeEvent
    exam_id: UUID = Field(alias="examId")
    seq: int = Field(ge=0)
    server_time: datetime = Field(alias="serverTime")


class ExamStartedFrame(ServerFrame):
    starts_at: datetime = Field(alias="startsAt")
    ends_at: datetime = Field(alias="endsAt")


class ExamEndingFrame(ServerFrame):
    """Sent when the deadline is reached and the sweep begins.

    Candidate writes are already refused by this point; the frame exists so the
    UI can say so rather than failing a save silently.
    """

    ends_at: datetime = Field(alias="endsAt")


class SessionStateFrame(ServerFrame):
    """Sent to the monitor whenever a candidate's row changes."""

    session_id: UUID = Field(alias="sessionId")
    student_id: UUID = Field(alias="studentId")
    status: SessionStatus
    connection: ConnectionState
    warning_count: int = Field(alias="warningCount")
    answered_count: int = Field(alias="answeredCount")
    summary: MonitorSummary | None = Field(
        default=None,
        description="Recomputed aggregates, so the monitor never re-reduces the full roster.",
    )


class WarningFrame(ServerFrame):
    """An invigilation signal worth surfacing.

    Evidence for a human to judge, not an accusation the system makes.
    """

    session_id: UUID = Field(alias="sessionId")
    student_id: UUID = Field(alias="studentId")
    reason: str
    occurred_at: datetime = Field(alias="occurredAt")


class ForceSubmitFrame(ServerFrame):
    """Instructs a candidate client to close the paper immediately.

    Advisory only: the server has already stopped accepting that session's
    writes. A client that ignores this frame gains nothing.
    """

    session_id: UUID = Field(alias="sessionId")
    reason: str


class ClientFrame(Schema):
    """Base envelope for lab-client to server frames."""

    event: RealtimeEvent
    session_id: UUID | None = Field(default=None, alias="sessionId")
    machine_id: str = Field(alias="machineId")
    occurred_at: datetime = Field(alias="occurredAt")


class HeartbeatFrame(ClientFrame):
    """Liveness ping. High volume - held in Redis, never a row per beat."""


class FocusFrame(ClientFrame):
    """Focus lost or restored, reported by the lab client."""

    detail: str | None = None
