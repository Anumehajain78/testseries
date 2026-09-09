"""Lab computer enrolment and reporting.

A workstation is not a person. It cannot own an exam, sit in a roster, or reset
a password — so it does not get a user account. Instead each machine holds its
own credential and presents it for the two things it is allowed to do: say it
is still there, and report what happened in front of it.

The enrolment path is deliberately two-staged:

* an administrator mints a short-lived **enrolment token** for one lab and
  types it into the machines in that room, once;
* each machine exchanges it for a **permanent secret of its own**, so the
  shared token can expire without any machine losing its identity.

That way the thing typed by hand in a lab is short-lived and lab-scoped, and
the long-lived thing never leaves the machine it belongs to.
"""

import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_secret, issue_machine_token, verify_secret
from app.db.models import AuditEvent, Computer, ExamSession, Lab
from app.domain.liveness import connection_state
from app.schemas.auth import MachineCredential, MachineToken
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ConnectionState,
    SubjectType,
)
from app.utils.clock import utcnow

#: How long an enrolment token is good for. Long enough to walk a lab and set
#: up every machine, short enough that a note left on a desk goes stale.
ENROLMENT_TOKEN_HOURS = 12

#: Signals a lab client reports. Anything else is refused rather than stored,
#: so the audit trail cannot be filled with arbitrary text from a workstation.
REPORTABLE = {
    AuditEventType.FOCUS_LOST,
    AuditEventType.FOCUS_RESTORED,
    AuditEventType.EXAM_CLIENT_CLOSED,
    AuditEventType.CONNECTION_RESTORED,
}

#: Signals that count towards a candidate's warning tally. Losing focus is
#: recorded as evidence for a person to weigh, never treated on its own as
#: proof of anything.
COUNTS_AS_WARNING = {AuditEventType.FOCUS_LOST, AuditEventType.EXAM_CLIENT_CLOSED}


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------


def mint_enrolment_token(db: Session, lab_id: UUID) -> tuple[str, Lab]:
    """Create a fresh enrolment token for one lab.

    Returned in the clear exactly once. Only the hash is kept, so this cannot
    be looked up later — losing it means minting another, which is cheap and
    does not disturb machines already enrolled.
    """
    lab = db.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Laboratory not found")

    token = f"{lab.name[:3].upper().replace(' ', '')}-{secrets.token_urlsafe(18)}"
    lab.enrolment_token_hash = hash_secret(token)
    lab.enrolment_token_expires_at = utcnow() + timedelta(hours=ENROLMENT_TOKEN_HOURS)
    db.commit()
    return token, lab


def enrol_machine(db: Session, token: str, machine_id: str, hostname: str | None) -> MachineCredential:
    """Bind a permanent secret to one workstation.

    The machine must already exist in the lab's floor plan. A workstation that
    can invent its own identity is one an attacker can add to the room, so
    enrolment claims a known machine rather than creating a new one.
    """
    computer = db.scalar(select(Computer).where(Computer.machine_id == machine_id))
    if computer is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"{machine_id} is not on any laboratory floor plan. Add it first.",
        )

    lab = db.get(Lab, computer.lab_id)
    now = utcnow()
    if (
        lab is None
        or not lab.enrolment_token_hash
        or not lab.enrolment_token_expires_at
        or lab.enrolment_token_expires_at < now
        or not verify_secret(token, lab.enrolment_token_hash)
    ):
        # One message for wrong, missing and expired: a machine being set up
        # should not be able to probe which labs have a live token.
        raise _unauthorized("That enrolment token is not valid for this machine")

    secret = secrets.token_urlsafe(32)
    computer.secret_hash = hash_secret(secret)
    computer.enrolled_at = now
    if hostname:
        computer.hostname = hostname

    db.add(
        AuditEvent(
            id=uuid4(),
            event=AuditEventType.LOGIN,
            category=AuditCategory.SYSTEM,
            severity=AuditSeverity.INFO,
            detail=f"{machine_id} enrolled in {lab.name}.",
            occurred_at=now,
            recorded_at=now,
            actor_type=SubjectType.MACHINE,
            actor_label=machine_id,
            machine_id=machine_id,
        )
    )
    db.commit()
    # The only time this secret is ever readable.
    return MachineCredential(machine_id=machine_id, secret=secret, lab_id=lab.id)


def issue_token(db: Session, machine_id: str, secret: str) -> MachineToken:
    computer = db.scalar(select(Computer).where(Computer.machine_id == machine_id))
    if computer is None or not computer.secret_hash or not verify_secret(secret, computer.secret_hash):
        raise _unauthorized("Unknown machine or secret")

    token, expires_at = issue_machine_token(machine_id, computer.lab_id)
    return MachineToken(
        access_token=token,
        expires_at=expires_at,
        server_time=utcnow(),
        machine_id=machine_id,
        lab_id=computer.lab_id,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def record_heartbeat(db: Session, machine_id: str, session_id: UUID | None) -> tuple[bool, UUID | None]:
    """Mark a workstation as alive.

    Returns whether the machine's liveness *changed*, and which exam it belongs
    to. Callers publish a realtime frame only on a change: sixty machines
    beating every ten seconds would otherwise push six frames a second at every
    open monitor, each of which triggers a refetch.
    """
    computer = db.scalar(select(Computer).where(Computer.machine_id == machine_id))
    if computer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown machine")

    now = utcnow()
    before = connection_state(computer.last_heartbeat_at, now=now)
    computer.last_heartbeat_at = now

    exam_id = None
    if session_id is not None:
        session = db.get(ExamSession, session_id)
        if session is not None:
            session.last_heartbeat_at = now
            exam_id = session.exam_id

    db.commit()
    return before is not ConnectionState.ONLINE, exam_id


def record_event(
    db: Session,
    machine_id: str,
    session_id: UUID,
    event: str,
    occurred_at,
    detail: str | None,
) -> tuple[ExamSession, bool]:
    """Store an invigilation signal reported by a lab client.

    Both timestamps are kept: what the machine said, and when the server heard
    it. A workstation with a wrong or tampered clock is then visible in the
    data rather than quietly reordering someone's timeline.
    """
    try:
        kind = AuditEventType(event)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown event {event!r}") from exc

    if kind not in REPORTABLE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{event} is not something a lab client may report",
        )

    session = db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    now = utcnow()
    warned = kind in COUNTS_AS_WARNING
    if warned:
        session.warning_count += 1

    db.add(
        AuditEvent(
            id=uuid4(),
            event=kind,
            category=AuditCategory.SESSION,
            severity=AuditSeverity.WARNING if warned else AuditSeverity.INFO,
            detail=detail or kind.value.replace("_", " ").capitalize(),
            occurred_at=occurred_at or now,
            recorded_at=now,
            actor_type=SubjectType.MACHINE,
            actor_label=machine_id,
            exam_id=session.exam_id,
            session_id=session.id,
            student_id=session.student_id,
            machine_id=machine_id,
        )
    )
    db.commit()
    return session, warned
