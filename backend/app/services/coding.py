"""Marking a program by running it.

Coding answers are not scored while a paper is being sat. Running a program
takes seconds, a lab submits within the same minute, and a candidate pressing
submit must not wait on sixty other people's code. So a coding answer behaves
exactly like a written one: it is stored, it counts as unmarked, and the marks
arrive afterwards — from the runner instead of from a person.

That reuses the whole marking path rather than inventing a parallel one.
``answers.awarded_marks`` is the same column a human fills in, and
``score_paper`` already knows that an answer with no award is pending rather
than wrong.
"""

from __future__ import annotations

from uuid import UUID

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.db.models import Answer, Exam, ExamQuestion, ExamSession, Question, QuestionTest
from app.domain.sandbox import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIME_LIMIT_MS,
    Outcome,
    SandboxUnavailable,
    run_python,
    sandbox_available,
)
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ExamStatus,
    QuestionType,
)
from app.services.commands import _audit


def normalise(output: str) -> str:
    """Compare what the candidate meant, not how their terminal spaced it.

    Trailing whitespace on a line and a missing final newline are the two ways
    a correct program is marked wrong by a careless comparison. Neither is
    something an examination is trying to test, and a candidate cannot see the
    expected bytes to match them exactly.

    Everything else is significant: internal spacing, blank lines between
    values, and case are all part of the answer.
    """
    lines = [line.rstrip() for line in output.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def run_answer(question: Question, tests: list[QuestionTest], source: str) -> dict:
    """Run one candidate's program against every case, and score it.

    Marks are proportional to the weight of the cases passed. This differs from
    multiple-response, which is all or nothing, and the difference is
    deliberate: a program that handles the ordinary input but not the empty one
    has demonstrably done most of the work, where a half-ticked multiple-choice
    answer has demonstrated nothing.
    """
    time_limit = question.time_limit_ms or DEFAULT_TIME_LIMIT_MS
    memory_limit = question.memory_limit_mb or DEFAULT_MEMORY_LIMIT_MB

    cases: list[dict] = []
    earned = 0
    total_weight = sum(test.weight for test in tests)
    # A case the sandbox could not run says nothing about the program. Scoring
    # it as a failure would take marks off a candidate for a fault on the
    # server, silently — one flaky case in five is twenty per cent of a mark
    # nobody would ever think to question.
    unavailable = False

    for test in tests:
        execution = run_python(
            source,
            test.stdin,
            time_limit_ms=time_limit,
            memory_limit_mb=memory_limit,
        )
        if execution.outcome is Outcome.UNAVAILABLE:
            unavailable = True
        passed = (
            execution.outcome is Outcome.OK
            and normalise(execution.stdout) == normalise(test.expected_stdout)
        )
        if passed:
            earned += test.weight

        cases.append({
            "position": test.position,
            "hidden": test.hidden,
            "passed": passed,
            "outcome": str(execution.outcome),
            "durationMs": execution.duration_ms,
            # The candidate's own output, kept so a disputed mark can be looked
            # at rather than argued about. Only for cases they were allowed to
            # see — echoing a hidden case's output back would hand over the
            # answer key one submission at a time.
            "stdout": execution.stdout if not test.hidden else "",
            "stderr": execution.stderr if not test.hidden else "",
        })

    marks = round(question.marks * earned / total_weight, 2) if total_weight else 0.0
    return {
        "marks": marks,
        "passed": sum(1 for case in cases if case["passed"]),
        "total": len(cases),
        "cases": cases,
        #: True when at least one case never ran. The caller must not record
        #: these marks: the paper stays unmarked and is picked up again, which
        #: is the right outcome for a transient fault on the server.
        "incomplete": unavailable,
    }


def grade_exam(db: Session, exam_id: UUID, *, force: bool = False) -> dict:
    """Mark every candidate's coding answers for one exam.

    What the faculty endpoint calls after fixing a broken test case: re-running
    with ``force`` re-marks the whole cohort against the corrected question, so
    nobody keeps a mark earned under the wrong one.
    """
    if sandbox_available() is None:
        raise SandboxUnavailable(
            "Candidate code cannot be run on this machine: bubblewrap is "
            "missing or unprivileged user namespaces are disabled. No marks "
            "have been changed."
        )

    sessions = db.scalars(
        select(ExamSession.id).where(
            ExamSession.exam_id == exam_id, ExamSession.submitted_at.is_not(None)
        )
    ).all()

    graded = skipped = 0
    for session_id in sessions:
        outcome = grade_session(db, session_id, force=force)
        graded += outcome["graded"]
        skipped += outcome["skipped"]
    return {"graded": graded, "skipped": skipped}


def grade_session(db: Session, session_id: UUID, *, force: bool = False) -> dict:
    """Run every coding answer on one paper and record the marks.

    Skips answers already marked unless ``force``, so a re-run after a server
    restart costs nothing and cannot quietly change a mark somebody has already
    seen. Re-running deliberately is how a faculty member fixes a question
    whose test cases were wrong.
    """
    if sandbox_available() is None:
        raise SandboxUnavailable(
            "Candidate code cannot be run on this machine: bubblewrap is "
            "missing or unprivileged user namespaces are disabled. No marks "
            "have been changed."
        )

    session = db.get(ExamSession, session_id)
    if session is None:
        return {"graded": 0, "skipped": 0}

    coding = db.scalars(
        select(Question)
        .join(ExamQuestion, ExamQuestion.question_id == Question.id)
        .where(ExamQuestion.exam_id == session.exam_id, Question.type == QuestionType.CODING)
        .options(selectinload(Question.tests))
    ).all()

    graded = skipped = 0
    for question in coding:
        answer = db.get(Answer, {"session_id": session_id, "question_id": question.id})
        if answer is None:
            continue
        if answer.awarded_marks is not None and not force:
            skipped += 1
            continue

        source = (answer.value or {}).get("source")
        if not isinstance(source, str) or not source.strip():
            # An empty editor is a blank answer, not a failing program. Marked
            # zero rather than left pending, so the paper can be finished.
            answer.awarded_marks = 0
            answer.run_report = {"marks": 0, "passed": 0, "total": len(question.tests), "cases": []}
            graded += 1
            continue

        report = run_answer(question, list(question.tests), source)
        if report["incomplete"]:
            # Left unmarked on purpose, so the next pass tries again. Recording
            # a mark here would turn a server fault into a candidate's result.
            skipped += 1
            continue
        answer.awarded_marks = report["marks"]
        answer.run_report = report
        graded += 1

    db.commit()
    return {"graded": graded, "skipped": skipped}


def claim_and_grade(db: Session, *, limit: int = 4) -> dict:
    """Grade a few submitted papers' coding answers, safely across workers.

    The API runs several worker processes and each runs its own sweep, so this
    is a shared queue rather than a private one. ``FOR UPDATE SKIP LOCKED`` is
    what makes that safe: a worker claims rows nobody else holds and the others
    move past them, so the same program is never run twice and one slow answer
    does not block the rest.

    Only submitted papers. Running a candidate's code while they are still
    editing it would burn the server's time on a program they are about to
    change, and the marks would be stale by the time anyone read them.

    The batch is small on purpose. Each answer costs seconds of wall clock, and
    this shares a process with the deadline sweep — which must stay responsive,
    because it is what ends examinations on time.
    """
    if sandbox_available() is None:
        # Not an error here, unlike the explicit endpoint: a machine without a
        # sandbox should still run examinations, it simply cannot mark the
        # coding answers, and saying so once a minute would drown the log.
        return {"graded": 0, "unavailable": True}

    claimed = db.scalars(
        select(Answer)
        .join(ExamSession, ExamSession.id == Answer.session_id)
        .join(Question, Question.id == Answer.question_id)
        .where(
            Question.type == QuestionType.CODING,
            Answer.awarded_marks.is_(None),
            ExamSession.submitted_at.is_not(None),
        )
        .order_by(ExamSession.submitted_at)
        .limit(limit)
        .with_for_update(skip_locked=True, of=Answer)
    ).all()

    graded = 0
    for answer in claimed:
        question = db.get(Question, answer.question_id)
        if question is None:
            continue
        source = (answer.value or {}).get("source")
        if isinstance(source, str) and source.strip():
            report = run_answer(question, list(question.tests), source)
            if report["incomplete"]:
                # Try again next pass rather than record a mark a server fault
                # produced.
                continue
        else:
            report = {"marks": 0, "passed": 0, "total": len(question.tests), "cases": []}
        answer.awarded_marks = report["marks"]
        answer.run_report = report
        graded += 1

    db.commit()
    return {"graded": graded, "unavailable": False}


def list_reports(db: Session, exam_id: UUID) -> list["CodingReport"]:
    """Every coding answer on an exam, with how it was marked.

    The counterpart of the written-answer marking queue. Staff-guarded at the
    route, and it carries candidate names for the same reason that one does:
    somebody reviewing a mark needs to know whose work they are looking at.
    """
    from app.db.models import Student, User
    from app.schemas.session import CodingCaseReport, CodingReport

    questions = {
        q.id: q
        for q in db.scalars(
            select(Question)
            .join(ExamQuestion, ExamQuestion.question_id == Question.id)
            .where(ExamQuestion.exam_id == exam_id, Question.type == QuestionType.CODING)
        ).all()
    }
    if not questions:
        return []

    rows = db.execute(
        select(Answer, ExamSession, User, Student)
        .join(ExamSession, ExamSession.id == Answer.session_id)
        .join(Student, Student.user_id == ExamSession.student_id)
        .join(User, User.id == Student.user_id)
        .where(ExamSession.exam_id == exam_id, Answer.question_id.in_(questions))
        .order_by(User.full_name)
    ).all()

    reports: list[CodingReport] = []
    for answer, session, user, student in rows:
        question = questions[answer.question_id]
        report = answer.run_report or {}
        reports.append(
            CodingReport(
                session_id=session.id,
                question_id=answer.question_id,
                student_name=user.full_name,
                registration_no=student.registration_no,
                prompt=question.prompt,
                marks=question.marks,
                source=(answer.value or {}).get("source", ""),
                awarded_marks=float(answer.awarded_marks) if answer.awarded_marks is not None else None,
                passed=report.get("passed", 0),
                total=report.get("total", 0),
                cases=[CodingCaseReport(**case) for case in report.get("cases", [])],
            )
        )
    return reports


def correct_test_cases(
    db: Session,
    exam_id: UUID,
    question_id: UUID,
    cases: list,
    *,
    reason: str,
    actor_id: UUID,
    actor_label: str,
) -> dict:
    """Fix a coding question's test cases after the examination has finished.

    The only edit a paper accepts once it stops being a draft, and it exists
    because the alternative is worse. A test case with the wrong expected
    output marks an entire cohort against an answer that was never right; if
    that cannot be corrected, the wrong marks stand for ever. Refusing every
    edit is a defensible rule right up to the moment it protects a mistake.

    So the opening is deliberately narrow:

    * Only a coding question's cases. Not the prompt, not the marks, not the
      roster, not the window — changing any of those after candidates have sat
      the paper would rewrite what they were asked, rather than correct how it
      was judged.
    * Only once the exam is over. Changing the key while candidates are still
      answering is a worse version of the same problem, and there is no hurry:
      marks are awarded afterwards anyway.
    * Only with a reason, written to the audit trail. This changes marks people
      may already have been shown, which is exactly the kind of act that has to
      leave a record naming whoever did it.

    Every existing mark for the question is cleared, not recomputed here. That
    is the honest state: those marks were produced by a key that no longer
    exists, so the papers go back to unmarked and the runner re-marks them
    within the minute. A results screen showing "awaiting marking" for a moment
    is true; one showing marks from a question that has since been corrected is
    not.
    """
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam not found")
    if exam.status is not ExamStatus.COMPLETED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Test cases can only be corrected once the examination has finished. "
            f"This one is {exam.status.value}.",
        )

    link = db.scalar(
        select(ExamQuestion).where(
            ExamQuestion.exam_id == exam_id, ExamQuestion.question_id == question_id
        )
    )
    question = db.get(Question, question_id)
    if link is None or question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That question is not on this exam")
    if question.type is not QuestionType.CODING:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Only a coding question has test cases.",
        )
    if not cases:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A coding question needs at least one test case, or it can never be scored.",
        )

    # Cleared and flushed before the replacements are added. Assigning the list
    # in one go lets SQLAlchemy order the inserts before the deletes, and the
    # new case at position 0 then collides with the old one.
    question.tests.clear()
    db.flush()

    question.tests = [
        QuestionTest(
            id=uuid4(),
            position=index,
            stdin=case.stdin,
            expected_stdout=case.expected_stdout,
            hidden=case.hidden,
            weight=case.weight,
        )
        for index, case in enumerate(cases)
    ]

    # Back to unmarked. The runner picks them up on its next pass.
    cleared = db.execute(
        update(Answer)
        .where(
            Answer.question_id == question_id,
            Answer.session_id.in_(
                select(ExamSession.id).where(ExamSession.exam_id == exam_id)
            ),
        )
        .values(awarded_marks=None, run_report=None, marked_by=None, marked_at=None)
    ).rowcount

    _audit(
        db,
        event=AuditEventType.TEST_CASES_CORRECTED,
        category=AuditCategory.SYSTEM,
        severity=AuditSeverity.WARNING,
        detail=(
            f"Test cases corrected on a coding question in {exam.title}; "
            f"{cleared} mark(s) cleared for re-marking. Reason: {reason}"
        ),
        actor_label=actor_label,
        actor_id=actor_id,
        exam_id=exam_id,
    )
    db.commit()
    return {"cases": len(question.tests), "cleared": cleared}
