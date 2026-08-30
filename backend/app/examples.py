"""Static example payloads.

Step 02 stands the contract up without a database, so every route answers from
here. The values are deliberately consistent with each other - one exam, one
lab, one candidate roster - so the generated client can be exercised end to end
before Postgres exists.

This module is deleted in step 03, when the routes start reading real rows.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.schemas.audit import AuditEventOut
from app.schemas.auth import TokenPair, UserOut
from app.schemas.directory import ComputerOut, LabOut, StudentOut
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ConnectionState,
    ExamStatus,
    LabStatus,
    QuestionType,
    Role,
    SessionStatus,
    StudentStatus,
    SubjectType,
    SubmitMode,
)
from app.schemas.exam import ExamConfig, ExamDetail, ExamSummary, ExamWindow
from app.schemas.question import OptionOut, QuestionOut, StudentOptionOut, StudentQuestionOut
from app.schemas.result import ResultRow, ResultsPage, ResultStats
from app.schemas.session import (
    ActivityEntry,
    MonitorSnapshot,
    MonitorSummary,
    SessionDetail,
    SessionPaper,
    SessionRow,
    SessionState,
    SubmissionReceipt,
)

NOW = datetime(2026, 8, 30, 11, 30, tzinfo=UTC)

EXAM_ID = UUID("11111111-1111-4111-8111-111111111111")
LAB_ID = UUID("22222222-2222-4222-8222-222222222222")
STUDENT_ID = UUID("33333333-3333-4333-8333-333333333333")
SESSION_ID = UUID("44444444-4444-4444-8444-444444444444")
FACULTY_ID = UUID("55555555-5555-4555-8555-555555555555")
QUESTION_ID = UUID("66666666-6666-4666-8666-666666666666")
OPTION_IDS = [
    UUID("77777777-7777-4777-8777-77777777770a"),
    UUID("77777777-7777-4777-8777-77777777770b"),
]


def server_time() -> datetime:
    return datetime.now(UTC)


CONFIG = ExamConfig(
    questions_per_student=6,
    randomize_questions=True,
    randomize_options=True,
    allow_navigation=True,
    auto_submit_on_expiry=True,
)

EXAM_SUMMARY = ExamSummary(
    id=EXAM_ID,
    code="CSE-203-M1",
    title="Data Structures Mid-Semester",
    course="Data Structures & Algorithms",
    department="Computer Science",
    status=ExamStatus.LIVE,
    duration_minutes=45,
    scheduled_at=NOW,
    starts_at=NOW,
    ends_at=NOW + timedelta(minutes=45),
    lab_id=LAB_ID,
    lab_name="Advanced Computing Lab",
    enrolled_count=40,
    question_count=6,
    total_marks=14,
)

# Faculty-facing: carries the answer key.
QUESTION = QuestionOut(
    id=QUESTION_ID,
    type=QuestionType.MCQ,
    prompt="Which data structure follows the Last-In, First-Out principle?",
    marks=2,
    course="Data Structures & Algorithms",
    options=[
        OptionOut(id=OPTION_IDS[0], position=0, body="Queue", is_correct=False),
        OptionOut(id=OPTION_IDS[1], position=1, body="Stack", is_correct=True),
    ],
)

EXAM_DETAIL = ExamDetail(
    **EXAM_SUMMARY.model_dump(),
    description="Mid-semester assessment covering linear structures, trees, and hashing.",
    instructions=["Answer all questions.", "Do not refresh the examination window."],
    config=CONFIG,
    questions=[QUESTION],
    created_by=FACULTY_ID,
    created_at=NOW - timedelta(days=3),
)

# Candidate-facing: structurally incapable of carrying the answer key.
STUDENT_QUESTION = StudentQuestionOut(
    id=QUESTION_ID,
    type=QuestionType.MCQ,
    prompt="Which data structure follows the Last-In, First-Out principle?",
    marks=2,
    position=0,
    options=[
        StudentOptionOut(id=OPTION_IDS[1], position=0, body="Stack"),
        StudentOptionOut(id=OPTION_IDS[0], position=1, body="Queue"),
    ],
)

SESSION_ROW = SessionRow(
    id=SESSION_ID,
    student_id=STUDENT_ID,
    student_name="Aarav Mehta",
    registration_no="23CSE1001",
    machine_id="LAB1-PC-01",
    status=SessionStatus.ACTIVE,
    connection=ConnectionState.ONLINE,
    checked_in_at=NOW - timedelta(minutes=8),
    started_at=NOW,
    last_heartbeat_at=NOW + timedelta(minutes=12),
    warning_count=0,
    answered_count=3,
)

MONITOR_SUMMARY = MonitorSummary(
    enrolled=40, online=37, active=33, submitted=4, warnings=8, disconnected=3
)

MONITOR_SNAPSHOT = MonitorSnapshot(
    exam_id=EXAM_ID, summary=MONITOR_SUMMARY, rows=[SESSION_ROW], seq=1042
)

SESSION_DETAIL = SessionDetail(
    **SESSION_ROW.model_dump(),
    exam_id=EXAM_ID,
    activity=[
        ActivityEntry(at=NOW - timedelta(minutes=8), event="SESSION_CHECKED_IN", severity="INFO", detail="Signed in to exam client"),
        ActivityEntry(at=NOW, event="EXAM_STARTED", severity="INFO", detail="Exam started"),
        ActivityEntry(at=NOW + timedelta(minutes=9), event="FOCUS_LOST", severity="WARNING", detail="Focus left the exam window"),
        ActivityEntry(at=NOW + timedelta(minutes=9, seconds=40), event="FOCUS_RESTORED", severity="INFO", detail="Returned to the exam window"),
    ],
)

SESSION_PAPER = SessionPaper(
    session_id=SESSION_ID,
    exam_id=EXAM_ID,
    exam_title="Data Structures Mid-Semester",
    exam_code="CSE-203-M1",
    instructions=["Answer all questions."],
    status=SessionStatus.ACTIVE,
    config=CONFIG,
    ends_at=NOW + timedelta(minutes=45),
    questions=[STUDENT_QUESTION],
)

SESSION_STATE = SessionState(
    session_id=SESSION_ID,
    status=SessionStatus.ACTIVE,
    ends_at=NOW + timedelta(minutes=45),
    answers={str(QUESTION_ID): {"kind": "single", "option": 0}},
    flagged=[],
    server_seq=17,
)

RECEIPT = SubmissionReceipt(
    session_id=SESSION_ID,
    submission_id=UUID("88888888-8888-4888-8888-888888888888"),
    submitted_at=NOW + timedelta(minutes=41),
    mode=SubmitMode.MANUAL,
    answered_count=5,
    question_count=6,
    flagged_count=1,
)

EXAM_WINDOW = ExamWindow(
    exam_id=EXAM_ID,
    status=ExamStatus.LIVE,
    starts_at=NOW,
    ends_at=NOW + timedelta(minutes=45),
    released_session_count=37,
)

STUDENT = StudentOut(
    id=STUDENT_ID,
    registration_no="23CSE1001",
    full_name="Aarav Mehta",
    email="aarav.mehta@northbridge.edu",
    program="B.Tech CSE",
    semester=3,
    section="A",
    status=StudentStatus.ACTIVE,
)

LAB = LabOut(
    id=LAB_ID,
    name="Advanced Computing Lab",
    building="Newton Block · Level 2",
    capacity=40,
    status=LabStatus.OCCUPIED,
    invigilator_id=FACULTY_ID,
    invigilator_name="Dr. Priya Raman",
    computer_count=40,
    online_count=37,
)

COMPUTER = ComputerOut(
    id=UUID("99999999-9999-4999-8999-999999999999"),
    machine_id="LAB1-PC-01",
    lab_id=LAB_ID,
    position=1,
    hostname="lab1-pc-01.northbridge.local",
    enrolled_at=NOW - timedelta(days=90),
    last_heartbeat_at=NOW + timedelta(minutes=12),
    connection=ConnectionState.ONLINE,
)

USER = UserOut(
    id=FACULTY_ID,
    email="anita.rao@northbridge.edu",
    full_name="Anita Rao",
    role=Role.FACULTY,
)


def token_pair() -> TokenPair:
    now = server_time()
    return TokenPair(
        access_token="example.access.token",
        refresh_token="example.refresh.token",
        expires_at=now + timedelta(minutes=30),
        server_time=now,
        user=USER,
    )


RESULTS = ResultsPage(
    exam_id=EXAM_ID,
    published=False,
    published_at=None,
    stats=ResultStats(submitted=28, graded=28, average_percentage=70.0, highest_percentage=100.0),
    rows=[
        ResultRow(
            rank=1,
            session_id=SESSION_ID,
            student_id=STUDENT_ID,
            student_name="Aarav Mehta",
            registration_no="23CSE1001",
            score=None,  # withheld until published
            max_score=14,
            percentage=None,
            time_taken_seconds=2_460,
            mode=SubmitMode.MANUAL,
            submitted_at=NOW + timedelta(minutes=41),
        )
    ],
)

AUDIT_EVENT = AuditEventOut(
    id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    event=AuditEventType.EXAM_STARTED,
    category=AuditCategory.EXAM,
    severity=AuditSeverity.INFO,
    detail="Data Structures Mid-Semester went live for 40 enrolled candidates.",
    occurred_at=NOW,
    recorded_at=NOW,
    actor_type=SubjectType.USER,
    actor_label="Exam Cell · Anita Rao",
    exam_id=EXAM_ID,
)
