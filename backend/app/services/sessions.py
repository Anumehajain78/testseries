"""Candidate session services.

Everything a candidate is allowed to do, and nothing else. Three rules run
through the module:

* **A candidate reaches only their own session.** Ownership is checked against
  the token subject, never against an id the client supplies.
* **Writes need the exam LIVE and the session ACTIVE.** Both axes, checked in
  one place (``accepts_candidate_writes``). The UI's disabled buttons and
  navigation lock are convenience; this is enforcement.
* **The answer key never leaves the server.** Candidate responses are built
  from ``StudentQuestionOut``, which has no field for it, and grading happens
  here where the key already lives.
"""

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Answer,
    AuditEvent,
    Exam,
    ExamQuestion,
    ExamSession,
    Question,
    Result,
)
from app.domain.paper import AuthoredOption, AuthoredQuestion, draw_paper, presented_options, score_paper
from app.domain.transitions import accepts_candidate_writes
from app.schemas.auth import Principal
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ExamStatus,
    SessionStatus,
    SubjectType,
    SubmitMode,
)
from app.schemas.common import AnswerValue
from app.schemas.exam import ExamConfig
from app.schemas.question import StudentOptionOut, StudentQuestionOut
from app.schemas.session import (
    SaveAnswerResponse,
    SessionPaper,
    SessionState,
    SubmissionReceipt,
)
from app.realtime.events import publish_soon
from app.schemas.enums import RealtimeEvent as RT
from app.utils.clock import utcnow


def _load_owned(db: Session, session_id: UUID, principal: Principal) -> ExamSession:
    """Fetch a session the caller is entitled to see.

    A candidate may only reach their own. Staff may reach any, because
    invigilators legitimately inspect a session during an exam.
    """
    session = db.get(ExamSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    if principal.subject_type is SubjectType.USER and principal.role and principal.role.value == "STUDENT":
        if str(session.student_id) != principal.subject_id:
            # 404 rather than 403: a candidate should not be able to discover
            # that another candidate's session exists by probing ids.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return session


def _authored(db: Session, exam_id: UUID) -> dict[str, AuthoredQuestion]:
    rows = db.execute(
        select(ExamQuestion, Question)
        .join(Question, Question.id == ExamQuestion.question_id)
        .options(selectinload(ExamQuestion.question).selectinload(Question.options))
        .where(ExamQuestion.exam_id == exam_id)
        .order_by(ExamQuestion.position)
    ).all()
    return {
        str(question.id): AuthoredQuestion(
            id=question.id,
            type=question.type,
            prompt=question.prompt,
            marks=link.marks_override or question.marks,
            options=tuple(
                AuthoredOption(o.id, o.position, o.body, o.is_correct) for o in question.options
            ),
        )
        for link, question in rows
    }


def _paper(db: Session, session: ExamSession, exam: Exam) -> SessionPaper:
    authored = _authored(db, exam.id)
    order = session.question_order or list(authored)
    option_order = session.option_order or {}

    questions: list[StudentQuestionOut] = []
    for position, question_id in enumerate(order):
        question = authored.get(question_id)
        if question is None:
            continue
        questions.append(
            StudentQuestionOut(
                id=question.id,
                type=question.type,
                prompt=question.prompt,
                marks=question.marks,
                position=position,
                options=[
                    # Candidate coordinates: index in their list, not the
                    # authored position. No is_correct field exists here.
                    StudentOptionOut(id=option.id, position=index, body=option.body)
                    for index, option in enumerate(
                        presented_options(question, option_order.get(question_id))
                    )
                ],
            )
        )

    return SessionPaper(
        session_id=session.id,
        exam_id=exam.id,
        exam_title=exam.title,
        exam_code=exam.code,
        instructions=list(exam.instructions or []),
        status=session.status,
        config=ExamConfig(**(exam.config or {})),
        ends_at=exam.ends_at,
        questions=questions,
    )


def check_in(db: Session, session_id: UUID, principal: Principal, machine_id: str | None) -> SessionPaper:
    """Enter the waiting room and materialize this candidate's paper.

    The draw happens once. Re-checking in — after a refresh, or a reconnect —
    returns the same paper rather than reshuffling under saved answers.
    """
    session = _load_owned(db, session_id, principal)
    exam = db.get(Exam, session.exam_id)

    if session.question_order is None:
        config = ExamConfig(**(exam.config or {}))
        authored = _authored(db, exam.id)
        order, option_order = draw_paper(
            list(authored.values()),
            seed=str(session.id),
            randomize_questions=config.randomize_questions,
            randomize_options=config.randomize_options,
            questions_per_student=config.questions_per_student,
        )
        session.question_order = order
        session.option_order = option_order

    now = utcnow()
    session.checked_in_at = session.checked_in_at or now
    session.last_heartbeat_at = now

    # Waiting until the machine is confirmed; ready once it is. A candidate
    # released into a live exam is left alone — checking in again mid-paper
    # must not send them backwards.
    if session.status is SessionStatus.NOT_STARTED:
        session.status = SessionStatus.READY if machine_id else SessionStatus.WAITING

    db.add(
        AuditEvent(
            id=uuid4(),
            event=AuditEventType.SESSION_CHECKED_IN,
            category=AuditCategory.SESSION,
            severity=AuditSeverity.INFO,
            detail=f"Checked in{f' on {machine_id}' if machine_id else ''}.",
            occurred_at=now,
            recorded_at=now,
            actor_type=SubjectType.USER,
            actor_label="Candidate",
            exam_id=exam.id,
            session_id=session.id,
            student_id=session.student_id,
        )
    )
    db.commit()
    db.refresh(session)
    publish_soon(
        RT.STUDENT_CONNECTED, exam.id, exam.event_seq,
        sessionId=str(session.id), studentId=str(session.student_id),
        status=session.status.value,
    )
    return _paper(db, session, exam)


def get_paper(db: Session, session_id: UUID, principal: Principal) -> SessionPaper:
    session = _load_owned(db, session_id, principal)
    exam = db.get(Exam, session.exam_id)
    return _paper(db, session, exam)


def get_state(db: Session, session_id: UUID, principal: Principal) -> SessionState:
    """Reconnect recovery: the server's view of what was actually saved."""
    session = _load_owned(db, session_id, principal)
    exam = db.get(Exam, session.exam_id)
    answers = db.execute(select(Answer).where(Answer.session_id == session_id)).scalars().all()
    return SessionState(
        session_id=session.id,
        status=session.status,
        ends_at=exam.ends_at,
        # A row with an empty value is a question flagged but not answered.
        # It belongs in `flagged`, never in `answers` — reporting it as an
        # answer would both fail validation and overstate what was attempted.
        answers={str(a.question_id): a.value for a in answers if a.value},
        flagged=[a.question_id for a in answers if a.flagged],
        server_seq=exam.event_seq,
    )


def _assert_writable(db: Session, session: ExamSession) -> Exam:
    exam = db.get(Exam, session.exam_id)
    if not accepts_candidate_writes(exam.status, session.status):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "writes_closed",
                "message": "This examination is not accepting responses.",
                "currentState": f"{exam.status}/{session.status}",
                "requestedState": f"{ExamStatus.LIVE}/{SessionStatus.ACTIVE}",
            },
        )
    # Belt and braces: the sweep may not have run yet, and a candidate must not
    # slip an answer in between the deadline and the sweep noticing.
    if exam.ends_at and utcnow() > exam.ends_at:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "deadline_passed", "message": "The examination deadline has passed."},
        )
    return exam


def save_answer(
    db: Session,
    session_id: UUID,
    question_id: UUID,
    principal: Principal,
    value: AnswerValue,
    client_seq: int,
) -> SaveAnswerResponse:
    session = _load_owned(db, session_id, principal)
    _assert_writable(db, session)

    existing = db.get(Answer, {"session_id": session_id, "question_id": question_id})
    if existing is None:
        existing = Answer(session_id=session_id, question_id=question_id, value={}, client_seq=-1)
        db.add(existing)

    # A write that arrives out of order after a reconnect is discarded rather
    # than overwriting a newer one. The client refetches state when told so.
    if client_seq and client_seq <= existing.client_seq:
        return SaveAnswerResponse(question_id=question_id, saved_at=existing.saved_at, accepted=False)

    existing.value = value.model_dump(by_alias=True)
    existing.client_seq = client_seq
    existing.saved_at = utcnow()
    db.commit()
    return SaveAnswerResponse(question_id=question_id, saved_at=existing.saved_at, accepted=True)


def toggle_flag(
    db: Session, session_id: UUID, question_id: UUID, principal: Principal
) -> SaveAnswerResponse:
    session = _load_owned(db, session_id, principal)
    _assert_writable(db, session)

    existing = db.get(Answer, {"session_id": session_id, "question_id": question_id})
    if existing is None:
        # Flagging a question you have not answered is normal, so the row is
        # created to carry the flag.
        existing = Answer(session_id=session_id, question_id=question_id, value={}, flagged=True)
        db.add(existing)
    else:
        existing.flagged = not existing.flagged
    existing.saved_at = utcnow()
    db.commit()
    return SaveAnswerResponse(question_id=question_id, saved_at=existing.saved_at, accepted=True)


def grade(db: Session, session: ExamSession) -> Result:
    """Score a submitted paper.

    Runs server-side because that is where the answer key is, and because a
    score computed on the client is a score a candidate can choose.
    """
    authored = _authored(db, session.exam_id)
    answers = {
        str(a.question_id): a.value
        for a in db.execute(select(Answer).where(Answer.session_id == session.id)).scalars()
    }
    awarded, available = score_paper(authored, session.question_order, session.option_order, answers)

    result = db.get(Result, session.id)
    if result is None:
        result = Result(session_id=session.id, score=awarded, max_score=available)
        db.add(result)
    else:
        result.score, result.max_score = awarded, available
    return result


def submit(
    db: Session,
    session_id: UUID,
    principal: Principal,
    *,
    mode: SubmitMode = SubmitMode.MANUAL,
) -> SubmissionReceipt:
    """Final submission. Idempotent — a repeat returns the original receipt."""
    session = _load_owned(db, session_id, principal)

    if session.submitted_at and session.submission_id:
        return _receipt(db, session)

    _assert_writable(db, session)

    now = utcnow()
    session.status = (
        SessionStatus.AUTO_SUBMITTED if mode is SubmitMode.AUTO else SessionStatus.SUBMITTED
    )
    session.submitted_at = now
    session.submit_mode = mode
    session.submission_id = uuid4()
    grade(db, session)

    db.add(
        AuditEvent(
            id=uuid4(),
            event=AuditEventType.AUTO_SUBMISSION if mode is SubmitMode.AUTO else AuditEventType.SUBMISSION,
            category=AuditCategory.EXAM,
            severity=AuditSeverity.WARNING if mode is SubmitMode.AUTO else AuditSeverity.INFO,
            detail="Examination submitted.",
            occurred_at=now,
            recorded_at=now,
            actor_type=SubjectType.USER,
            actor_label="Candidate",
            exam_id=session.exam_id,
            session_id=session.id,
            student_id=session.student_id,
        )
    )
    db.commit()
    db.refresh(session)
    exam = db.get(Exam, session.exam_id)
    publish_soon(
        RT.SUBMISSION, session.exam_id, exam.event_seq,
        sessionId=str(session.id), studentId=str(session.student_id),
        status=session.status.value,
    )
    return _receipt(db, session)


def _receipt(db: Session, session: ExamSession) -> SubmissionReceipt:
    answers = db.execute(select(Answer).where(Answer.session_id == session.id)).scalars().all()
    answered = sum(1 for a in answers if a.value)
    total = len(session.question_order or _authored(db, session.exam_id))
    return SubmissionReceipt(
        session_id=session.id,
        submission_id=session.submission_id,
        submitted_at=session.submitted_at,
        mode=session.submit_mode or SubmitMode.MANUAL,
        answered_count=answered,
        question_count=total,
        flagged_count=sum(1 for a in answers if a.flagged),
    )
