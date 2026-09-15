"""Authentication, directory, and audit endpoints."""

from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select, update

from app.api.deps import Admin, CurrentPrincipal, DbSession, Staff
from app.core.security import (
    REFRESH,
    TokenError,
    decode_token,
    issue_user_tokens,
    verify_secret,
)
from app.db.models import RefreshToken, Student, User
from app.services import directory, machines, queries
from app.utils.clock import utcnow
from app.schemas.audit import AuditEventOut
from app.schemas.auth import (
    LoginRequest,
    MachineCredential,
    MachineEnrolRequest,
    MachineToken,
    MachineTokenRequest,
    PasswordChangeRequest,
    PasswordChanged,
    Principal,
    RefreshRequest,
    TokenPair,
    UserOut,
)
from app.schemas.common import Page
from app.schemas.directory import (
    ComputerOut,
    EnrolmentToken,
    ImportSummary,
    LabOut,
    NewStudent,
    RosterImportRequest,
    StudentCreate,
    StudentOut,
    StudentUpdate,
)
from app.schemas.enums import AuditCategory, AuditSeverity, SubjectType

auth_router = APIRouter(prefix="/auth", tags=["auth"])
directory_router = APIRouter(tags=["directory"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@auth_router.post("/login", response_model=TokenPair, operation_id="login")
def login(payload: LoginRequest, db: DbSession) -> TokenPair:
    """Human sign-in. The response carries ``server_time`` so the client can
    establish its clock offset before anything is timed."""
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    # One message and one code path for "no such user" and "wrong password",
    # so the endpoint does not tell an attacker which accounts exist.
    if user is None or not verify_secret(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")

    now = utcnow()
    user.last_login_at = now
    # A brand new session id: this sign-in is a device of its own, and nothing
    # done to it afterwards touches any other machine the same person is on.
    pair = _tokens_for(db, user, session_id=uuid4(), now=now)
    _prune_dead_refresh_tokens(db, now)
    db.commit()

    return pair


@auth_router.post("/refresh", response_model=TokenPair, operation_id="refreshToken")
def refresh(payload: RefreshRequest, db: DbSession) -> TokenPair:
    """Exchange a refresh token for a fresh pair.

    This exists so nobody is signed out during an examination. Access tokens
    are deliberately short-lived; without renewal an invigilator would be
    ejected part-way through a ninety-minute paper, which is a worse failure
    than the one short lifetimes are guarding against.

    Renewal is single-use. The presented token is consumed as the replacement
    is minted, so a copy taken off the wire is worth one renewal at most, and
    nothing at all once the real client has renewed. The replacement stays
    inside the same session id, which is why this does not sign the same person
    out of their other machine — the failure that sank the previous attempt.
    """
    claims = _refresh_claims(payload.refresh_token)
    now = utcnow()

    # FOR UPDATE because two renewals arriving together must not both win. Read
    # without the lock, each sees an unconsumed row and both are honoured,
    # leaving one session with two live chains — exactly the state rotation is
    # supposed to make impossible.
    stored = db.get(RefreshToken, UUID(claims["jti"]), with_for_update=True)

    # Unknown, replayed, and expired are one answer on purpose. Distinguishing
    # them would tell whoever is holding a stolen token whether it was ever
    # real and whether the owner has already used it.
    if stored is None or stored.consumed_at is not None or stored.expires_at <= now:
        raise _sign_in_again()

    user = db.get(User, stored.user_id)
    # The database decides, not the token: an account deleted or disabled since
    # sign-in must not be able to renew its way back in.
    if user is None or not user.is_active:
        raise _sign_in_again()

    stored.consumed_at = now
    # Deliberately *not* killing the rest of the session here. Revoking the
    # whole chain on a replay is the usual advice, but the usual advice is not
    # written for a room of candidates on flaky lab wifi: a client that retries
    # a renewal it never saw the answer to would end its own examination. The
    # replayed token is refused; the session it came from survives.
    pair = _tokens_for(db, user, session_id=stored.session_id, now=now)
    db.commit()

    return pair


def _sign_in_again() -> HTTPException:
    """One message for expired, malformed, replayed and wrong-type alike."""
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in again")


def _refresh_claims(token: str) -> dict:
    """Claims of a structurally valid refresh token, or a 401.

    Signature and type are checked before the database is touched, so an
    attacker cannot make the server do lookups with made-up token ids.
    """
    try:
        claims = decode_token(token, expected_type=REFRESH)
    except TokenError as exc:
        raise _sign_in_again() from exc
    try:
        UUID(claims["jti"])
        UUID(claims["sid"])
    except (KeyError, ValueError) as exc:
        # No ``sid`` means a token minted before rotation existed. It cannot be
        # tied to a session, so it cannot be rotated: sign in again.
        raise _sign_in_again() from exc
    return claims


def _prune_dead_refresh_tokens(db: DbSession, now: datetime) -> None:
    """Drop rows no presented token could ever match again.

    An expired token fails on its signature long before its row is read, and a
    consumed row is kept only so that a replay is recognisable — which stops
    being worth anything once the token has expired anyway. Both go.

    Run at sign-in because sign-in is the only operation that adds rows, so the
    table cannot grow while nobody is signing in, and no scheduled job has to
    exist for the cleanup to happen.
    """
    db.execute(delete(RefreshToken).where(RefreshToken.expires_at <= now))


def _tokens_for(db: DbSession, user: User, *, session_id: UUID, now: datetime) -> TokenPair:
    """Build the pair returned by both sign-in and renewal, recording the
    refresh half so that presenting it later can end it.

    The row is added, not committed: the caller decides what else belongs in
    the same transaction, so a handed-out token and the record of it can never
    disagree.
    """
    tokens = issue_user_tokens(user.id, user.role, session_id=session_id)
    db.add(
        RefreshToken(
            id=tokens.refresh_id,
            user_id=user.id,
            session_id=tokens.session_id,
            expires_at=tokens.refresh_expires_at,
        )
    )
    registration_no = db.scalar(
        select(Student.registration_no).where(Student.user_id == user.id)
    )
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=tokens.expires_at,
        server_time=now,
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            registration_no=registration_no,
        ),
    )


@auth_router.post("/password", response_model=PasswordChanged, operation_id="changePassword")
def change_password(
    payload: PasswordChangeRequest, db: DbSession, principal: CurrentPrincipal
) -> PasswordChanged:
    """Change your own password.

    Every sign-in this account has is ended, on every device including the one
    making the request. A password changes because the old one is no longer
    trusted, and sessions it opened must not outlive it.

    Machines have secrets, not passwords, and re-enrol to get a new one — so
    this is for people only.
    """
    if principal.subject_type is not SubjectType.USER:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "A workstation changes its credential by enrolling again.",
        )

    ended = directory.change_own_password(
        db,
        UUID(principal.subject_id),
        payload.current_password,
        payload.new_password,
    )
    return PasswordChanged(sessions_ended=ended)


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="logout")
def logout(db: DbSession, payload: RefreshRequest | None = None) -> None:
    """End one sign-in.

    Takes the refresh token, because that is the thing that outlives the
    browser tab; the access token expires on its own within the half hour.
    Only the presented session is ended — signing out of a lab machine must not
    sign the same candidate out of their own laptop.

    The body is optional and a token that no longer verifies is not an error: a
    client that has already discarded its tokens still gets its 204, because
    refusing a sign-out leaves somebody stuck on a screen they are trying to
    leave, and answering differently for a genuine token would make this an
    oracle for whether one was real.
    """
    if payload is None:
        return None
    try:
        claims = decode_token(payload.refresh_token, expected_type=REFRESH)
        session_id = UUID(claims["sid"])
    except (TokenError, KeyError, ValueError):
        return None

    db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session_id, RefreshToken.consumed_at.is_(None))
        .values(consumed_at=utcnow())
    )
    db.commit()
    return None


@auth_router.post("/machine/enrol", response_model=MachineCredential, operation_id="enrolMachine")
def enrol_machine(payload: MachineEnrolRequest, db: DbSession) -> MachineCredential:
    """Claim a workstation using its lab's enrolment token.

    Unauthenticated on purpose: a machine being set up has no credential yet,
    which is the whole point of the enrolment token. Returns the machine secret
    exactly once; only its hash is stored.
    """
    return machines.enrol_machine(db, payload.enrolment_token, payload.machine_id, payload.hostname)


@auth_router.post("/machine/token", response_model=MachineToken, operation_id="machineToken")
def machine_token(payload: MachineTokenRequest, db: DbSession) -> MachineToken:
    """Exchange a machine credential for a short-lived token.

    The token carries ``subject_type=machine``, which authorization uses to
    refuse it everywhere except heartbeat and event reporting.
    """
    return machines.issue_token(db, payload.machine_id, payload.secret)


@auth_router.get("/me", response_model=Principal, operation_id="getCurrentPrincipal")
def me(principal: CurrentPrincipal) -> Principal:
    return principal


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------


@directory_router.get("/students", response_model=Page[StudentOut], operation_id="listStudents")
def list_students(
    db: DbSession,
    _: Staff,
    search: str | None = Query(default=None, description="Matches name or registration number."),
    section: str | None = None,
    semester: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[StudentOut]:
    return queries.list_students(
        db, search=search, section=section, semester=semester, limit=limit, offset=offset
    )


@directory_router.post(
    "/students", response_model=NewStudent, status_code=status.HTTP_201_CREATED, operation_id="createStudent"
)
def create_student(payload: StudentCreate, db: DbSession, _: Admin) -> NewStudent:
    """Add one candidate. The password is shown here and nowhere else.

    Administrative, like the bulk import below. Allowing faculty to add
    candidates one at a time while refusing them the paste would not protect
    the register — it would only make rewriting it tedious.
    """
    return directory.create_student(db, payload)


@directory_router.patch("/students/{student_id}", response_model=StudentOut, operation_id="updateStudent")
def update_student(
    student_id: UUID, payload: StudentUpdate, db: DbSession, _: Admin
) -> StudentOut:
    """Edit a candidate, including blocking them from signing in."""
    return directory.update_student(db, student_id, payload)


@directory_router.post(
    "/students/{student_id}/password",
    response_model=NewStudent,
    operation_id="resetStudentPassword",
)
def reset_student_password(student_id: UUID, db: DbSession, _: Admin) -> NewStudent:
    """Give a candidate a new password, shown exactly once.

    The exam-morning fix: somebody arrives without their slip and cannot sit
    the paper. There is no self-service reset — the platform sends no email,
    and a candidate showing their college card to the exam cell is a stronger
    check than a link in a mailbox that anyone in a lab could read over their
    shoulder.

    Ends every session the candidate had. If the reset is happening because
    somebody else knew the password, leaving their session open would make it
    pointless.
    """
    return directory.reset_student_password(db, student_id)


@directory_router.post(
    "/students/import", response_model=ImportSummary, operation_id="importRoster"
)
def import_roster(payload: RosterImportRequest, db: DbSession, _: Admin) -> ImportSummary:
    """Create candidates from a spreadsheet export.

    Administrators only, and partial by design: rows that cannot be taken are
    reported with a reason and a line number rather than sinking the file.
    """
    return directory.import_roster(db, payload.csv)


@directory_router.get("/labs", response_model=list[LabOut], operation_id="listLabs")
def list_labs(db: DbSession, _: Staff) -> list[LabOut]:
    return queries.list_labs(db)


@directory_router.post(
    "/labs/{lab_id}/enrolment-token",
    response_model=EnrolmentToken,
    operation_id="mintLabEnrolmentToken",
)
def mint_enrolment_token(lab_id: UUID, db: DbSession, principal: Admin) -> EnrolmentToken:
    """Mint an enrolment token for one laboratory.

    Administrators only, and shown in the clear exactly once — it is stored
    hashed, so it cannot be read back. Minting a new one does not disturb
    machines already enrolled, because each holds its own secret by then.
    """
    token, lab = machines.mint_enrolment_token(db, lab_id)
    return EnrolmentToken(
        lab_id=lab.id,
        lab_name=lab.name,
        token=token,
        expires_at=lab.enrolment_token_expires_at,
    )


@directory_router.get("/labs/{lab_id}/computers", response_model=list[ComputerOut], operation_id="listLabComputers")
def list_lab_computers(lab_id: UUID, db: DbSession, _: Staff) -> list[ComputerOut]:
    """Workstations and their derived liveness.

    No candidate is attached here: seating belongs to the session, because a
    lab hosts a different cohort every hour.
    """
    return queries.list_lab_computers(db, lab_id)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@audit_router.get("", response_model=Page[AuditEventOut], operation_id="listAuditEvents")
def list_audit_events(
    db: DbSession,
    _: Staff,
    exam_id: UUID | None = Query(default=None, alias="examId"),
    student_id: UUID | None = Query(default=None, alias="studentId"),
    severity: AuditSeverity | None = None,
    category: AuditCategory | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AuditEventOut]:
    """Append-only trail. There is deliberately no delete endpoint."""
    return queries.list_audit_events(
        db, exam_id=exam_id, student_id=student_id, severity=severity,
        category=category, limit=limit, offset=offset,
    )
