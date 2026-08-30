"""Authentication models."""

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import Schema
from app.schemas.enums import Role, SubjectType


class LoginRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(Schema):
    id: UUID
    email: EmailStr
    full_name: str = Field(alias="fullName")
    role: Role
    #: Present only for STUDENT principals.
    registration_no: str | None = Field(default=None, alias="registrationNo")


class TokenPair(Schema):
    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    expires_at: datetime = Field(alias="expiresAt")
    #: The client stores one offset from this and never trusts its own clock.
    server_time: datetime = Field(alias="serverTime")
    user: UserOut


class RefreshRequest(Schema):
    refresh_token: str = Field(alias="refreshToken")


class MachineEnrolRequest(Schema):
    """One-time enrolment, performed once per workstation by an administrator.

    A workstation is not a user: it cannot own an exam, sit in a roster, or
    reset a password. Modelling it as a user row would mean every query
    touching users has to remember to exclude machines.
    """

    enrolment_token: str = Field(alias="enrolmentToken")
    machine_id: str = Field(alias="machineId")
    hostname: str | None = None


class MachineCredential(Schema):
    machine_id: str = Field(alias="machineId")
    #: Shown exactly once, at enrolment.
    secret: str
    lab_id: UUID = Field(alias="labId")


class MachineTokenRequest(Schema):
    machine_id: str = Field(alias="machineId")
    secret: str


class MachineToken(Schema):
    access_token: str = Field(alias="accessToken")
    expires_at: datetime = Field(alias="expiresAt")
    server_time: datetime = Field(alias="serverTime")
    machine_id: str = Field(alias="machineId")
    lab_id: UUID = Field(alias="labId")


class Principal(Schema):
    """Whoever is making the current request.

    ``subject_type`` is what lets one dependency guard both humans and
    machines: heartbeat and event endpoints accept a machine subject, and
    nothing else does.
    """

    subject_type: SubjectType = Field(alias="subjectType")
    subject_id: str = Field(alias="subjectId")
    role: Role | None = None
    server_time: datetime = Field(alias="serverTime")
