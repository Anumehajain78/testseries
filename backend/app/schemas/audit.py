"""Audit trail."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema
from app.schemas.enums import AuditCategory, AuditEventType, AuditSeverity, SubjectType


class AuditEventOut(Schema):
    """One append-only trail entry.

    Two timestamps, deliberately. ``occurred_at`` is what the reporting client
    claimed; ``recorded_at`` is when the server accepted it. Keeping both means
    clock skew - or a deliberately altered client clock - is visible in the
    data instead of silently corrupting the ordering of the timeline.
    """

    id: UUID
    event: AuditEventType
    category: AuditCategory
    severity: AuditSeverity
    detail: str
    occurred_at: datetime = Field(alias="occurredAt")
    recorded_at: datetime = Field(alias="recordedAt")
    actor_type: SubjectType = Field(alias="actorType")
    actor_label: str = Field(alias="actorLabel")
    exam_id: UUID | None = Field(default=None, alias="examId")
    session_id: UUID | None = Field(default=None, alias="sessionId")
    student_id: UUID | None = Field(default=None, alias="studentId")
    machine_id: str | None = Field(default=None, alias="machineId")
