"""Candidate records.

Adding a candidate creates two rows: the person who signs in, and the student
they are on the register. They are separate because the platform will one day
hold staff who are not candidates and candidates who have left, and collapsing
them now would make either awkward later.

Every new account gets a generated password, returned exactly once. A college
cannot invent sixty passwords by hand, and defaulting to something guessable —
the registration number is the obvious temptation — would mean any candidate
could sign in as any other on results day.
"""

import csv
import io
import secrets
import string
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import hash_secret, verify_secret
from app.db.models import RefreshToken, Student, User
from app.schemas.directory import (
    ImportOutcome,
    ImportSummary,
    NewStudent,
    PasswordReset,
    StudentCreate,
    StudentOut,
    StudentUpdate,
)
from app.schemas.enums import Role, StudentStatus
from app.utils.clock import utcnow

#: Readable but not guessable. Ambiguous characters are left out because these
#: get written on slips and read aloud across a lab.
_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "O0lI1")

#: Columns an imported file must carry. Anything else in the row is ignored,
#: so a spreadsheet exported from the college's own system usually just works.
REQUIRED_COLUMNS = {"registration_no", "full_name", "email", "program", "semester", "section"}


def _password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(10))


def _to_out(student: Student, user: User) -> StudentOut:
    return StudentOut(
        id=user.id,
        registration_no=student.registration_no,
        full_name=user.full_name,
        email=user.email,
        program=student.program,
        semester=student.semester,
        section=student.section,
        status=student.status,
    )


def create_student(db: Session, payload: StudentCreate) -> NewStudent:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{email} is already registered")
    if db.scalar(select(Student).where(Student.registration_no == payload.registration_no)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Registration number {payload.registration_no} already belongs to someone",
        )

    password = _password()
    user = User(
        id=uuid4(),
        email=email,
        password_hash=hash_secret(password),
        full_name=payload.full_name,
        role=Role.STUDENT,
    )
    db.add(user)
    db.flush()
    student = Student(
        user_id=user.id,
        registration_no=payload.registration_no,
        program=payload.program,
        semester=payload.semester,
        section=payload.section,
        status=StudentStatus.ACTIVE,
    )
    db.add(student)
    db.commit()
    # The only time the password is readable.
    return NewStudent(student=_to_out(student, user), temporary_password=password)


def update_student(db: Session, student_id: UUID, payload: StudentUpdate) -> StudentOut:
    student = db.get(Student, student_id)
    user = db.get(User, student_id)
    if student is None or user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")

    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "full_name" in fields:
        user.full_name = fields["full_name"]
    if "email" in fields:
        email = fields["email"].lower()
        clash = db.scalar(select(User).where(User.email == email, User.id != user.id))
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{email} is already registered")
        user.email = email
    for column in ("program", "semester", "section", "status"):
        if column in fields:
            setattr(student, column, fields[column])

    # Blocking a candidate must also stop them signing in, or "blocked" is
    # decoration on a screen rather than a fact about the system.
    if "status" in fields:
        user.is_active = fields["status"] is StudentStatus.ACTIVE

    db.commit()
    return _to_out(student, user)


def import_roster(db: Session, csv_text: str) -> ImportSummary:
    """Create candidates from a spreadsheet export.

    Row by row rather than all-or-nothing: a college roster usually has one
    duplicate or one malformed address in it, and refusing the whole file over
    a single bad line would mean fixing it blind. Every row that cannot be
    taken is reported with the reason and its line number.
    """
    try:
        reader = csv.DictReader(io.StringIO(csv_text.strip()))
        columns = {(name or "").strip().lower() for name in (reader.fieldnames or [])}
    except csv.Error as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unreadable file: {exc}") from exc

    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"The file is missing these columns: {', '.join(sorted(missing))}",
        )

    created: list[NewStudent] = []
    failed: list[ImportOutcome] = []

    for line, raw in enumerate(reader, start=2):  # line 1 is the header
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        try:
            payload = StudentCreate(
                registration_no=row["registration_no"],
                full_name=row["full_name"],
                email=row["email"],
                program=row["program"],
                semester=int(row["semester"]),
                section=row["section"],
            )
        except (ValueError, KeyError) as exc:
            failed.append(ImportOutcome(line=line, registration_no=row.get("registration_no", ""), reason=_readable(exc)))
            continue

        try:
            created.append(create_student(db, payload))
        except HTTPException as exc:
            # Roll back only this row; the ones before it stand.
            db.rollback()
            failed.append(
                ImportOutcome(line=line, registration_no=payload.registration_no, reason=str(exc.detail))
            )

    return ImportSummary(created=created, failed=failed)


def _readable(exc: Exception) -> str:
    """Turn a validation failure into something an administrator can act on."""
    text = str(exc)
    if "email" in text.lower():
        return "That email address is not valid"
    if "semester" in text.lower():
        return "Semester must be a number between 1 and 12"
    if isinstance(exc, KeyError):
        return f"Missing value for {exc.args[0]}"
    return "Some values in this row are missing or invalid"


def _revoke_every_session(db: Session, user_id: UUID) -> int:
    """End every sign-in this person has, on every device.

    Deliberately not the per-session revocation that signing out uses. A
    password changes because the old one is no longer trusted — lost, shared,
    or taken — and leaving the sessions it opened alive would defeat the whole
    act. Somebody holding the old password keeps their seat until the token
    happens to expire.

    Access tokens are stateless and live for half an hour, so there is a window
    where an already-issued one still works. Closing it would mean a database
    lookup on every request for the life of the system, which is a real cost
    paid every second against a risk measured in minutes. The refresh tokens
    are what turn thirty minutes into twelve hours, and those are gone.
    """
    return db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.consumed_at.is_(None))
        .values(consumed_at=utcnow())
    ).rowcount


def change_own_password(db: Session, user_id: UUID, current: str, replacement: str) -> int:
    """Change a password, knowing the one being replaced.

    The current password is required and checked even though the caller is
    already authenticated. A signed-in session is not proof that the person at
    the keyboard is the account holder — on a lab machine it is frequently
    proof of the opposite, because the previous candidate walked away without
    signing out.

    Returns how many sign-ins were ended, so the screen can say so.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")

    if not verify_secret(current, user.password_hash):
        # Deliberately the same wording the sign-in screen uses. Confirming
        # that the *new* password was fine but the old one was wrong tells an
        # attacker at an unattended machine which half they got right.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password")

    if current == replacement:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That is the password you are already using.",
        )

    user.password_hash = hash_secret(replacement)
    ended = _revoke_every_session(db, user_id)
    db.commit()
    return ended


def reset_student_password(db: Session, student_id: UUID) -> PasswordReset:
    """Give a candidate a new password, because they have lost the old one.

    This is the exam-morning fix: somebody arrives without their slip and
    cannot sit the paper. There is no self-service reset by design — the
    platform sends no email, a lab has no private inbox to send one to, and a
    candidate proving who they are to the exam cell with their college card is
    a stronger check than a link in a mailbox anyone in the room could be
    reading over their shoulder.

    Every session the candidate had is ended. If the reset is happening because
    somebody else knew the password, leaving their session open would make the
    reset pointless.
    """
    student = db.get(Student, student_id)
    user = db.get(User, student_id)
    if student is None or user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")

    password = _password()
    user.password_hash = hash_secret(password)
    ended = _revoke_every_session(db, student_id)
    db.commit()

    # Same moment as adding a candidate — a password readable once and gone as
    # soon as the screen closes — plus the count, because whoever is doing this
    # at a counter wants to know if they have just ejected four live sign-ins.
    return PasswordReset(
        student=_to_out(student, user),
        temporary_password=password,
        sessions_ended=ended,
    )
