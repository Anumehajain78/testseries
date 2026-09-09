"""Students, labs, and workstations."""

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import Schema
from app.schemas.enums import ConnectionState, LabStatus, StudentStatus


class StudentOut(Schema):
    id: UUID
    registration_no: str = Field(alias="registrationNo")
    full_name: str = Field(alias="fullName")
    email: EmailStr
    program: str
    semester: int = Field(ge=1, le=12)
    section: str
    status: StudentStatus


class StudentCreate(Schema):
    registration_no: str = Field(min_length=1, max_length=40, alias="registrationNo")
    full_name: str = Field(min_length=1, max_length=200, alias="fullName")
    email: EmailStr
    program: str
    semester: int = Field(ge=1, le=12)
    section: str


class StudentUpdate(Schema):
    full_name: str | None = Field(default=None, alias="fullName")
    email: EmailStr | None = None
    program: str | None = None
    semester: int | None = Field(default=None, ge=1, le=12)
    section: str | None = None
    status: StudentStatus | None = None


class ComputerOut(Schema):
    """A workstation.

    Deliberately has no ``student_id``. Seating is a fact about a candidate
    sitting a particular exam, recorded on the session - a lab hosts a
    different cohort every hour, so a permanent binding cannot hold.
    """

    id: UUID
    machine_id: str = Field(alias="machineId")
    lab_id: UUID = Field(alias="labId")
    position: int
    hostname: str | None = None
    enrolled_at: datetime | None = Field(default=None, alias="enrolledAt")
    last_heartbeat_at: datetime | None = Field(default=None, alias="lastHeartbeatAt")
    connection: ConnectionState


class LabOut(Schema):
    id: UUID
    name: str
    building: str
    capacity: int = Field(ge=0)
    status: LabStatus
    invigilator_id: UUID | None = Field(default=None, alias="invigilatorId")
    invigilator_name: str | None = Field(default=None, alias="invigilatorName")
    computer_count: int = Field(alias="computerCount")
    online_count: int = Field(alias="onlineCount")


class EnrolmentToken(Schema):
    """A lab's enrolment token, returned the one time it is readable.

    Administrators type this into each machine in the room once; the machine
    then exchanges it for a permanent secret of its own, so this can expire
    without any workstation losing its identity.
    """

    lab_id: UUID = Field(alias="labId")
    lab_name: str = Field(alias="labName")
    token: str
    expires_at: datetime = Field(alias="expiresAt")


class NewStudent(Schema):
    """A candidate just created, with the one look at their password.

    Returned rather than stored in the clear, and never retrievable again: an
    administrator distributes it, and a candidate who loses it needs a reset
    rather than a lookup.
    """

    student: StudentOut
    temporary_password: str = Field(alias="temporaryPassword")


class ImportOutcome(Schema):
    """A row that could not be taken, and why."""

    line: int = Field(description="Line number in the uploaded file, counting the header as 1.")
    registration_no: str = Field(alias="registrationNo")
    reason: str


class ImportSummary(Schema):
    """What an import did.

    Partial by design: one duplicate in a roster of sixty should not cost the
    other fifty-nine.
    """

    created: list[NewStudent] = Field(default_factory=list)
    failed: list[ImportOutcome] = Field(default_factory=list)


class RosterImportRequest(Schema):
    csv: str = Field(min_length=1, description="The file's contents, header row included.")
