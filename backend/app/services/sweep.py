"""The deadline sweep.

When an exam's ``ends_at`` passes, the server closes it — not the candidate's
browser. A client-side auto-submit is a convenience that fires only if the tab
is still open, on time, and cooperating; none of those can be assumed of a
machine that has just lost its network.

The sweep distinguishes two outcomes that must never be confused:

* a candidate who was answering is ``AUTO_SUBMITTED`` and graded on whatever
  they had saved;
* a candidate who never entered the paper is ``TERMINATED``, because an empty
  submission and an absent candidate are different facts about a person.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Exam, ExamSession
from app.db.session import SessionLocal
from app.domain.transitions import SWEEPABLE_TO_AUTO_SUBMIT, SWEEPABLE_TO_TERMINATED
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ExamStatus,
    SessionStatus,
    SubjectType,
    SubmitMode,
)
from app.services.sessions import grade
from app.utils.clock import utcnow

log = logging.getLogger(__name__)

#: How often the loop looks for expired exams. Fine-grained enough that a
#: candidate never keeps answering long past the deadline, cheap enough to run
#: continuously — and irrelevant to correctness, because writes are refused
#: past ends_at whether or not the sweep has caught up.
SWEEP_INTERVAL_SECONDS = 10


def sweep_once(db: Session) -> dict[str, int]:
    """Close every exam whose deadline has passed. Safe to run repeatedly."""
    now = utcnow()
    expired = db.execute(
        select(Exam).where(
            Exam.status.in_([ExamStatus.LIVE, ExamStatus.ENDING]),
            Exam.ends_at.is_not(None),
            Exam.ends_at <= now,
        )
    ).scalars().all()

    submitted = terminated = 0
    for exam in expired:
        exam.status = ExamStatus.ENDING
        sessions = db.execute(
            select(ExamSession).where(ExamSession.exam_id == exam.id)
        ).scalars().all()

        for session in sessions:
            if session.status in SWEEPABLE_TO_AUTO_SUBMIT:
                session.status = SessionStatus.AUTO_SUBMITTED
                session.submitted_at = session.submitted_at or now
                session.submit_mode = SubmitMode.AUTO
                session.submission_id = session.submission_id or uuid4()
                grade(db, session)
                submitted += 1
            elif session.status in SWEEPABLE_TO_TERMINATED:
                session.status = SessionStatus.TERMINATED
                terminated += 1

        exam.status = ExamStatus.COMPLETED
        exam.ended_at = exam.ended_at or now
        exam.event_seq += 1
        db.add(
            AuditEvent(
                id=uuid4(),
                event=AuditEventType.EXAM_ENDED,
                category=AuditCategory.EXAM,
                severity=AuditSeverity.INFO,
                detail=(
                    f"{exam.title} reached its deadline; "
                    f"{submitted} auto-submitted, {terminated} never started."
                ),
                occurred_at=now,
                recorded_at=now,
                # The server closed this, not a person.
                actor_type=SubjectType.MACHINE,
                actor_label="Examination scheduler",
                exam_id=exam.id,
            )
        )

    if expired:
        db.commit()
    return {"exams": len(expired), "auto_submitted": submitted, "terminated": terminated}


async def sweep_loop() -> None:
    """Background task started with the application.

    Each pass gets its own session, and a failure is logged rather than
    allowed to kill the loop — a transient database blip must not leave every
    later exam running past its deadline.
    """
    while True:
        try:
            with SessionLocal() as db:
                outcome = sweep_once(db)
            if outcome["exams"]:
                log.info("deadline sweep closed %s", outcome)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - defensive
            log.exception("deadline sweep failed; continuing")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
