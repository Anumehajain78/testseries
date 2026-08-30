"""Authentication, directory, and audit endpoints."""

from uuid import UUID

from fastapi import APIRouter, Query, status

from app import examples
from app.schemas.audit import AuditEventOut
from app.schemas.auth import (
    LoginRequest,
    MachineCredential,
    MachineEnrolRequest,
    MachineToken,
    MachineTokenRequest,
    Principal,
    RefreshRequest,
    TokenPair,
)
from app.schemas.common import Page
from app.schemas.directory import ComputerOut, LabOut, StudentCreate, StudentOut, StudentUpdate
from app.schemas.enums import AuditCategory, AuditSeverity, SubjectType

auth_router = APIRouter(prefix="/auth", tags=["auth"])
directory_router = APIRouter(tags=["directory"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@auth_router.post("/login", response_model=TokenPair, operation_id="login")
async def login(payload: LoginRequest) -> TokenPair:
    """Human sign-in. The response carries ``server_time`` so the client can
    establish its clock offset before anything is timed."""
    return examples.token_pair()


@auth_router.post("/refresh", response_model=TokenPair, operation_id="refreshToken")
async def refresh(payload: RefreshRequest) -> TokenPair:
    return examples.token_pair()


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout")
async def logout() -> None:
    return None


@auth_router.post("/machine/enrol", response_model=MachineCredential, operation_id="enrolMachine")
async def enrol_machine(payload: MachineEnrolRequest) -> MachineCredential:
    """One-time workstation enrolment, performed by an administrator.

    Returns the machine secret exactly once; it is stored hashed.
    """
    return MachineCredential(
        machine_id=payload.machine_id, secret="example-machine-secret", lab_id=examples.LAB_ID
    )


@auth_router.post("/machine/token", response_model=MachineToken, operation_id="machineToken")
async def machine_token(payload: MachineTokenRequest) -> MachineToken:
    """Exchanges a machine credential for a short-lived token carrying
    ``subject_type=machine``. Such a token may only reach heartbeat and event
    endpoints."""
    tokens = examples.token_pair()
    return MachineToken(
        access_token="example.machine.token",
        expires_at=tokens.expires_at,
        server_time=tokens.server_time,
        machine_id=payload.machine_id,
        lab_id=examples.LAB_ID,
    )


@auth_router.get("/me", response_model=Principal, operation_id="getCurrentPrincipal")
async def me() -> Principal:
    return Principal(
        subject_type=SubjectType.USER,
        subject_id=str(examples.FACULTY_ID),
        role=examples.USER.role,
        server_time=examples.server_time(),
    )


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------


@directory_router.get("/students", response_model=Page[StudentOut], operation_id="listStudents")
async def list_students(
    search: str | None = Query(default=None, description="Matches name or registration number."),
    section: str | None = None,
    semester: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[StudentOut]:
    return Page[StudentOut](items=[examples.STUDENT], total=1, limit=limit, offset=offset)


@directory_router.post(
    "/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED, operation_id="createStudent"
)
async def create_student(payload: StudentCreate) -> StudentOut:
    return examples.STUDENT


@directory_router.patch("/students/{student_id}", response_model=StudentOut, operation_id="updateStudent")
async def update_student(student_id: UUID, payload: StudentUpdate) -> StudentOut:
    return examples.STUDENT


@directory_router.get("/labs", response_model=list[LabOut], operation_id="listLabs")
async def list_labs() -> list[LabOut]:
    return [examples.LAB]


@directory_router.get("/labs/{lab_id}/computers", response_model=list[ComputerOut], operation_id="listLabComputers")
async def list_lab_computers(lab_id: UUID) -> list[ComputerOut]:
    """Workstations and their derived liveness.

    No candidate is attached here: seating belongs to the session, because a
    lab hosts a different cohort every hour.
    """
    return [examples.COMPUTER]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@audit_router.get("", response_model=Page[AuditEventOut], operation_id="listAuditEvents")
async def list_audit_events(
    exam_id: UUID | None = Query(default=None, alias="examId"),
    student_id: UUID | None = Query(default=None, alias="studentId"),
    severity: AuditSeverity | None = None,
    category: AuditCategory | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AuditEventOut]:
    """Append-only trail. There is deliberately no delete endpoint."""
    return Page[AuditEventOut](items=[examples.AUDIT_EVENT], total=1, limit=limit, offset=offset)
