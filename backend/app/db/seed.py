"""Development seed.

Mirrors the frontend mock's world — the same roster, labs, papers and exam
states — so that flipping ``NEXT_PUBLIC_API_MODE`` between ``mock`` and ``live``
should produce recognisably the same screens. Any visible difference is a real
integration bug rather than a data artefact, which is the point.

Every timestamp is derived from the moment the seed runs, so "Today's
examinations" is populated whenever this is executed.

    ./.venv/bin/python -m app.db.seed          # idempotent: wipes and reseeds
"""

from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import hash_secret
from app.db.models import (
    Answer,
    AuditEvent,
    Computer,
    Exam,
    ExamEnrolment,
    ExamQuestion,
    ExamSession,
    Faculty,
    Lab,
    Question,
    QuestionOption,
    Result,
    Student,
    User,
)
from app.db.session import SessionLocal
from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ExamStatus,
    LabStatus,
    QuestionType,
    Role,
    SessionStatus,
    StudentStatus,
    SubjectType,
    SubmitMode,
)
from app.utils.clock import utcnow

DEV_PASSWORD = "examcontrol"

ROSTER: list[tuple[str, str, int, str, bool]] = [
    ("Aarav Mehta", "B.Tech CSE", 3, "A", False),
    ("Diya Nair", "B.Tech CSE", 3, "A", False),
    ("Kabir Singh", "B.Tech CSE", 3, "A", False),
    ("Meera Joshi", "B.Tech CSE", 3, "A", False),
    ("Rohan Das", "B.Tech CSE", 3, "A", True),
    ("Sara Khan", "B.Tech CSE", 3, "A", False),
    ("Vivaan Reddy", "B.Tech CSE", 3, "A", False),
    ("Ananya Iyer", "B.Tech CSE", 3, "A", False),
    ("Aditya Rao", "B.Tech CSE", 3, "A", False),
    ("Ishita Gupta", "B.Tech CSE", 3, "A", False),
    ("Arjun Kapoor", "B.Tech CSE", 3, "A", False),
    ("Nisha Verma", "B.Tech CSE", 3, "A", False),
    ("Karthik Menon", "B.Tech CSE", 3, "A", False),
    ("Priya Shetty", "B.Tech CSE", 3, "A", False),
    ("Rahul Chauhan", "B.Tech CSE", 3, "A", False),
    ("Sneha Pillai", "B.Tech CSE", 3, "A", False),
    ("Dhruv Malhotra", "B.Tech CSE", 3, "A", False),
    ("Tanvi Desai", "B.Tech CSE", 3, "A", False),
    ("Siddharth Bose", "B.Tech CSE", 3, "A", False),
    ("Aisha Sheikh", "B.Tech CSE", 3, "A", False),
    ("Yash Agarwal", "B.Tech CSE", 3, "B", False),
    ("Riya Sharma", "B.Tech CSE", 3, "B", False),
    ("Aryan Bhat", "B.Tech CSE", 3, "B", False),
    ("Kavya Nambiar", "B.Tech CSE", 3, "B", False),
    ("Nikhil Jain", "B.Tech CSE", 3, "B", False),
    ("Pooja Patel", "B.Tech CSE", 3, "B", False),
    ("Manav Saxena", "B.Tech CSE", 3, "B", False),
    ("Anjali Rane", "B.Tech CSE", 3, "B", False),
    ("Harsh Vardhan", "B.Tech CSE", 3, "B", False),
    ("Lakshmi Menon", "B.Tech CSE", 3, "B", False),
    ("Omkar Kulkarni", "B.Tech CSE", 3, "B", False),
    ("Sanya Kapadia", "B.Tech CSE", 3, "B", False),
    ("Rehan Ali", "B.Tech CSE", 3, "B", False),
    ("Divya Krishnan", "B.Tech CSE", 3, "B", False),
    ("Varun Nadar", "B.Tech CSE", 3, "B", False),
    ("Ira Chatterjee", "B.Tech CSE", 3, "B", False),
    ("Aman Gill", "B.Tech CSE", 3, "B", False),
    ("Neha Bansal", "B.Tech CSE", 3, "B", False),
    ("Rudra Pandey", "B.Tech CSE", 3, "B", False),
    ("Simran Kaur", "B.Tech CSE", 3, "B", False),
    ("Krishna Murthy", "B.Tech ECE", 5, "A", False),
    ("Tara Fernandes", "B.Tech ECE", 5, "A", False),
    ("Ayush Tiwari", "B.Tech ECE", 5, "A", False),
    ("Myra DSouza", "B.Tech ECE", 5, "A", False),
    ("Kunal Bhatt", "B.Tech ECE", 5, "A", False),
    ("Zara Qureshi", "B.Tech ECE", 5, "A", True),
    ("Parth Vyas", "B.Tech ECE", 5, "A", False),
    ("Ridhi Sen", "B.Tech ECE", 5, "A", False),
    ("Gaurav Naik", "B.Tech ECE", 5, "A", False),
    ("Aditi Deshpande", "B.Tech ECE", 5, "A", False),
    ("Shaurya Rathore", "B.Tech IT", 5, "A", False),
    ("Naina Kohli", "B.Tech IT", 5, "A", False),
    ("Vikram Sinha", "B.Tech IT", 5, "A", False),
    ("Palak Arora", "B.Tech IT", 5, "A", False),
    ("Devansh Mishra", "B.Tech IT", 5, "A", False),
    ("Mahira Ansari", "B.Tech IT", 5, "B", False),
    ("Tejas Wagh", "B.Tech IT", 5, "B", False),
    ("Anushka Roy", "B.Tech IT", 5, "B", False),
    ("Farhan Sheikh", "B.Tech IT", 5, "B", False),
    ("Isha Bhardwaj", "B.Tech IT", 5, "B", False),
]

DS_QUESTIONS = [
    (QuestionType.MCQ, "Which data structure follows the Last-In, First-Out principle?",
     ["Queue", "Stack", "Heap", "Graph"], [1], 2),
    (QuestionType.MCQ, "What is the average time complexity of search in a balanced binary search tree?",
     ["O(1)", "O(log n)", "O(n)", "O(n²)"], [1], 2),
    (QuestionType.MCQ, "Which traversal visits the root between the left and right subtrees?",
     ["Preorder", "Inorder", "Postorder", "Level order"], [1], 2),
    (QuestionType.MULTIPLE, "Select every data structure that provides O(1) average-time insertion at one end.",
     ["Stack", "Hash table", "Sorted array", "Queue"], [0, 1, 3], 3),
    (QuestionType.MULTIPLE, "Which of the following are self-balancing binary search trees?",
     ["AVL tree", "Red-black tree", "Binary heap", "Splay tree"], [0, 1, 3], 3),
    (QuestionType.TEXT, "Explain in one sentence why hashing can degrade to O(n) lookup time.", [], [], 2),
]

CN_QUESTIONS = [
    (QuestionType.MCQ, "Which layer of the OSI model is responsible for routing?",
     ["Data link", "Network", "Transport", "Session"], [1], 2),
    (QuestionType.MCQ, "Which protocol guarantees ordered, reliable delivery?",
     ["UDP", "TCP", "ICMP", "ARP"], [1], 2),
    (QuestionType.MULTIPLE, "Which addresses belong to private IPv4 ranges?",
     ["10.0.0.5", "192.168.1.10", "8.8.8.8", "172.16.4.2"], [0, 1, 3], 3),
    (QuestionType.TEXT, "Explain the purpose of the TCP three-way handshake in one sentence.", [], [], 3),
]

DB_QUESTIONS = [
    (QuestionType.MCQ, "Which normal form removes transitive functional dependencies?",
     ["1NF", "2NF", "3NF", "BCNF"], [2], 10),
    (QuestionType.MCQ, "Which SQL clause filters groups produced by GROUP BY?",
     ["WHERE", "HAVING", "ON", "ORDER BY"], [1], 10),
    (QuestionType.MULTIPLE, "Select the ACID properties of a database transaction.",
     ["Atomicity", "Consistency", "Isolation", "Durability"], [0, 1, 2, 3], 20),
    (QuestionType.TEXT, "State one advantage of a clustered index over a non-clustered index.", [], [], 20),
]

OS_QUESTIONS = [
    (QuestionType.MCQ, "Which scheduling algorithm can cause starvation of long processes?",
     ["First-Come First-Served", "Shortest Job First", "Round Robin", "FIFO"], [1], 5),
    (QuestionType.MCQ, "A deadlock requires all of the following conditions except which?",
     ["Mutual exclusion", "Hold and wait", "Preemption", "Circular wait"], [2], 5),
    (QuestionType.MULTIPLE, "Which mechanisms are used for inter-process communication?",
     ["Pipes", "Shared memory", "Message queues", "Page tables"], [0, 1, 2], 5),
    (QuestionType.TEXT, "Describe the difference between a process and a thread in one sentence.", [], [], 5),
]


def _branch(program: str) -> str:
    return "CSE" if "CSE" in program else "ECE" if "ECE" in program else "IT"


def wipe(db: Session) -> None:
    """Delete in dependency order. Faster and clearer than dropping the schema,
    and it keeps the migration history intact."""
    for model in (
        Answer, Result, AuditEvent, ExamSession, ExamEnrolment, ExamQuestion,
        Exam, QuestionOption, Question, Computer, Lab, Student, Faculty, User,
    ):
        db.execute(delete(model))
    db.commit()


def _make_questions(db: Session, owner_id: UUID, course: str, spec: list) -> list[Question]:
    questions: list[Question] = []
    for qtype, prompt, options, correct, marks in spec:
        question = Question(
            id=uuid4(), owner_id=owner_id, course=course, type=qtype, prompt=prompt, marks=marks
        )
        question.options = [
            QuestionOption(id=uuid4(), position=i, body=body, is_correct=i in correct)
            for i, body in enumerate(options)
        ]
        db.add(question)
        questions.append(question)
    return questions


def seed(db: Session) -> dict[str, int]:
    now = utcnow()
    wipe(db)

    # -- staff ---------------------------------------------------------------
    admin = User(
        id=uuid4(), email="admin@northbridge.edu", password_hash=hash_secret(DEV_PASSWORD),
        full_name="Exam Cell Administrator", role=Role.ADMIN,
    )
    anita_user = User(
        id=uuid4(), email="anita.rao@northbridge.edu", password_hash=hash_secret(DEV_PASSWORD),
        full_name="Anita Rao", role=Role.FACULTY,
    )
    priya_user = User(
        id=uuid4(), email="priya.raman@northbridge.edu", password_hash=hash_secret(DEV_PASSWORD),
        full_name="Dr. Priya Raman", role=Role.FACULTY,
    )
    db.add_all([admin, anita_user, priya_user])
    db.flush()

    anita = Faculty(user_id=anita_user.id, employee_no="NIT-F-001", department="Computer Science")
    priya = Faculty(user_id=priya_user.id, employee_no="NIT-F-002", department="Computer Science")
    db.add_all([anita, priya])
    db.flush()

    # -- candidates ----------------------------------------------------------
    students: list[Student] = []
    for index, (name, program, semester, section, blocked) in enumerate(ROSTER, start=1):
        user = User(
            id=uuid4(),
            email=f"{name.lower().replace(' ', '.')}@northbridge.edu",
            password_hash=hash_secret(DEV_PASSWORD),
            full_name=name,
            role=Role.STUDENT,
        )
        db.add(user)
        db.flush()
        student = Student(
            user_id=user.id,
            registration_no=f"23{_branch(program)}{1000 + index}",
            program=program,
            semester=semester,
            section=section,
            status=StudentStatus.BLOCKED if blocked else StudentStatus.ACTIVE,
        )
        db.add(student)
        students.append(student)
    db.flush()

    # -- venues --------------------------------------------------------------
    lab_a = Lab(id=uuid4(), name="Advanced Computing Lab", building="Newton Block · Level 2",
                capacity=40, status=LabStatus.OCCUPIED, invigilator_id=priya.user_id)
    lab_b = Lab(id=uuid4(), name="Systems Laboratory", building="Turing Block · Level 1",
                capacity=30, status=LabStatus.READY, invigilator_id=anita.user_id)
    lab_c = Lab(id=uuid4(), name="Networks Laboratory", building="Turing Block · Level 3",
                capacity=24, status=LabStatus.MAINTENANCE)
    db.add_all([lab_a, lab_b, lab_c])
    db.flush()

    computers: dict[str, list[Computer]] = {}
    for lab, lab_no, count in ((lab_a, 1, 40), (lab_b, 2, 30), (lab_c, 3, 24)):
        machines = []
        for position in range(1, count + 1):
            # Deterministic liveness so the monitor and lab views look stable:
            # a few offline machines, a few in warning, the rest healthy.
            if lab is lab_c:
                heartbeat = None
            elif position % 13 == 0:
                heartbeat = now - timedelta(minutes=6)      # offline
            elif position % 5 == 0:
                heartbeat = now - timedelta(seconds=45)     # warning
            else:
                heartbeat = now - timedelta(seconds=4)      # online
            machine = Computer(
                id=uuid4(), lab_id=lab.id, machine_id=f"LAB{lab_no}-PC-{position:02d}",
                position=position, hostname=f"lab{lab_no}-pc-{position:02d}.northbridge.local",
                enrolled_at=now - timedelta(days=90), last_heartbeat_at=heartbeat,
            )
            db.add(machine)
            machines.append(machine)
        computers[lab.name] = machines
    db.flush()

    # -- question bank -------------------------------------------------------
    ds_q = _make_questions(db, anita.user_id, "Data Structures & Algorithms", DS_QUESTIONS)
    cn_q = _make_questions(db, anita.user_id, "Computer Networks", CN_QUESTIONS)
    db_q = _make_questions(db, anita.user_id, "Database Management Systems", DB_QUESTIONS)
    os_q = _make_questions(db, anita.user_id, "Operating Systems", OS_QUESTIONS)
    db.flush()

    def build_exam(*, code, title, course, status, lab, questions, roster, scheduled_offset,
                   duration, config=None, starts=None, ends=None) -> Exam:
        exam = Exam(
            id=uuid4(), code=code, title=title, course=course, department="Computer Science",
            instructions=["Answer all questions.", "Do not refresh the examination window."],
            duration_minutes=duration, scheduled_at=now + scheduled_offset,
            starts_at=starts, ends_at=ends, status=status, lab_id=lab.id,
            created_by=anita.user_id,
            config=config or {
                "questionsPerStudent": 0, "randomizeQuestions": False, "randomizeOptions": False,
                "allowNavigation": True, "autoSubmitOnExpiry": True,
            },
        )
        db.add(exam)
        db.flush()
        for position, question in enumerate(questions):
            db.add(ExamQuestion(exam_id=exam.id, question_id=question.id, position=position))
        for student in roster:
            db.add(ExamEnrolment(exam_id=exam.id, student_id=student.user_id))
        db.flush()
        return exam

    ds_roster = students[:40]
    cn_roster = students[40:60]

    # Live: started half an hour ago, still running.
    ds_exam = build_exam(
        code="CSE-203-M1", title="Data Structures Mid-Semester",
        course="Data Structures & Algorithms", status=ExamStatus.LIVE, lab=lab_a,
        questions=ds_q, roster=ds_roster, scheduled_offset=timedelta(minutes=-30),
        duration=45, starts=now - timedelta(minutes=30), ends=now + timedelta(minutes=15),
    )
    # Scheduled later today, so the dashboard's "today" panel has two rows.
    cn_exam = build_exam(
        code="CSE-307-P1", title="Computer Networks Practice Test",
        course="Computer Networks", status=ExamStatus.SCHEDULED, lab=lab_b,
        questions=cn_q, roster=cn_roster, scheduled_offset=timedelta(minutes=90), duration=40,
        config={"questionsPerStudent": 4, "randomizeQuestions": True, "randomizeOptions": False,
                "allowNavigation": True, "autoSubmitOnExpiry": True},
    )
    build_exam(
        code="CSE-305-Q2", title="Operating Systems Quiz II", course="Operating Systems",
        status=ExamStatus.DRAFT, lab=lab_b, questions=os_q, roster=[],
        scheduled_offset=timedelta(days=2), duration=30,
    )
    completed = build_exam(
        code="CSE-302-E1", title="Database Systems End-Semester",
        course="Database Management Systems", status=ExamStatus.COMPLETED, lab=lab_a,
        questions=db_q, roster=ds_roster, scheduled_offset=timedelta(days=-45), duration=90,
        starts=now - timedelta(days=45), ends=now - timedelta(days=45) + timedelta(minutes=90),
    )
    # An exam that finished six weeks ago has had its results released; leaving
    # it unpublished would misrepresent the normal end state.
    completed.results_published_at = now - timedelta(days=40)

    # -- sessions ------------------------------------------------------------
    lab_a_machines = computers["Advanced Computing Lab"]
    lab_b_machines = computers["Systems Laboratory"]

    for index, (student, machine) in enumerate(zip(ds_roster, lab_a_machines), start=1):
        offline = machine.last_heartbeat_at is None or (
            (now - machine.last_heartbeat_at).total_seconds() > 90
        )
        if offline:
            status, submitted_at, mode = SessionStatus.NOT_STARTED, None, None
        elif index % 9 == 0:
            status, submitted_at, mode = SessionStatus.SUBMITTED, now - timedelta(minutes=3), SubmitMode.MANUAL
        elif index % 4 == 0:
            status, submitted_at, mode = SessionStatus.READY, None, None
        else:
            status, submitted_at, mode = SessionStatus.ACTIVE, None, None
        db.add(ExamSession(
            id=uuid4(), exam_id=ds_exam.id, student_id=student.user_id, computer_id=machine.id,
            status=status,
            checked_in_at=None if offline else now - timedelta(minutes=38),
            started_at=None if status in (SessionStatus.NOT_STARTED, SessionStatus.READY) else now - timedelta(minutes=30),
            submitted_at=submitted_at, submit_mode=mode,
            submission_id=uuid4() if submitted_at else None,
            last_heartbeat_at=machine.last_heartbeat_at,
            warning_count=2 if (machine.last_heartbeat_at and (now - machine.last_heartbeat_at).total_seconds() > 30 and not offline) else 0,
        ))

    # The scheduled exam is seated but not released — this is the readiness view.
    for student, machine in zip(cn_roster, lab_b_machines):
        db.add(ExamSession(
            id=uuid4(), exam_id=cn_exam.id, student_id=student.user_id, computer_id=machine.id,
            status=SessionStatus.READY, checked_in_at=now - timedelta(minutes=4),
            last_heartbeat_at=machine.last_heartbeat_at,
        ))

    # -- completed exam: sessions and graded results -------------------------
    db_total = sum(marks for *_, marks in DB_QUESTIONS)
    scores = [48, 60, 35, 42, 39, 45, 28, 51, 47, 32, 40, 53, 37, 44, 49, 30, 34, 52, 41, 38,
              46, 29, 43, 36, 50, 33, 58, 31]
    finished = now - timedelta(days=45) + timedelta(minutes=70)
    for offset, (student, score) in enumerate(zip(ds_roster, scores)):
        mode = SubmitMode.AUTO if offset % 7 == 0 else SubmitMode.MANUAL
        session = ExamSession(
            id=uuid4(), exam_id=completed.id, student_id=student.user_id,
            status=SessionStatus.AUTO_SUBMITTED if mode is SubmitMode.AUTO else SessionStatus.SUBMITTED,
            checked_in_at=now - timedelta(days=45) - timedelta(minutes=10),
            started_at=now - timedelta(days=45),
            submitted_at=finished + timedelta(minutes=offset % 20),
            submit_mode=mode, submission_id=uuid4(),
        )
        db.add(session)
        db.flush()
        db.add(Result(session_id=session.id, score=min(score, db_total), max_score=db_total))

    # -- audit ---------------------------------------------------------------
    trail = [
        (AuditEventType.EXAM_STARTED, AuditCategory.EXAM, AuditSeverity.INFO, 30,
         "Data Structures Mid-Semester went live for 40 enrolled candidates.", "Exam Cell · Anita Rao"),
        (AuditEventType.SESSION_CHECKED_IN, AuditCategory.SESSION, AuditSeverity.INFO, 35,
         "34 of 40 assigned workstations in Advanced Computing Lab reported ready.", "System"),
        (AuditEventType.FOCUS_LOST, AuditCategory.SESSION, AuditSeverity.WARNING, 11,
         "Ishita Gupta switched away from the exam window on LAB1-PC-10.", "System"),
        (AuditEventType.CONNECTION_LOST, AuditCategory.CONNECTION, AuditSeverity.CRITICAL, 6,
         "LAB1-PC-13 dropped its heartbeat during the live examination.", "System"),
        (AuditEventType.SUBMISSION, AuditCategory.EXAM, AuditSeverity.INFO, 3,
         "Aditya Rao submitted Data Structures Mid-Semester from LAB1-PC-09.", "System"),
    ]
    for event, category, severity, minutes_ago, detail, actor in trail:
        at = now - timedelta(minutes=minutes_ago)
        db.add(AuditEvent(
            id=uuid4(), event=event, category=category, severity=severity, detail=detail,
            occurred_at=at, recorded_at=at, actor_type=SubjectType.USER, actor_label=actor,
            exam_id=ds_exam.id,
        ))

    db.commit()

    counts = {
        "users": len(ROSTER) + 3,
        "students": len(students),
        "labs": 3,
        "computers": 94,
        "exams": 4,
        "sessions": len(ds_roster) + len(cn_roster) + len(scores),
    }
    return counts


def main() -> None:
    with SessionLocal() as db:
        counts = seed(db)
    print("seeded: " + ", ".join(f"{value} {key}" for key, value in counts.items()))
    print(f"sign in with any seeded email and the password: {DEV_PASSWORD}")


if __name__ == "__main__":
    main()
