"""Coding questions, end to end.

Two things are being protected here.

The first is the answer key. A coding question's expected outputs are exactly
what an option's ``is_correct`` flag is, and a candidate who can read them can
print them without solving anything. These assert that hidden cases never reach
a candidate and that visible ones arrive without their answers.

The second is that marks arrive at all — a program is marked after submission
rather than during it, so the failure mode to guard against is a paper that
sits at "awaiting marking" for ever.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import Answer, Question, QuestionTest
from app.db.session import SessionLocal
from app.domain.sandbox import sandbox_available
from app.main import app
from app.services import coding

client = TestClient(app)
API = "/api/v1"

needs_sandbox = pytest.mark.skipif(
    sandbox_available() is None,
    reason="needs bubblewrap and unprivileged user namespaces",
)


def _login(email: str) -> dict[str, str] | None:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "examcontrol"})
    if response.status_code != 200:
        return None
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


@pytest.fixture(scope="module")
def staff(database) -> dict[str, str]:
    headers = _login("anita.rao@northbridge.edu")
    if headers is None:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return headers


@pytest.fixture(scope="module")
def world(staff) -> dict:
    labs = client.get(f"{API}/labs", headers=staff).json()
    students = client.get(f"{API}/students?limit=5", headers=staff).json()["items"]
    if not labs or not students:
        pytest.skip("no seeded database")
    return {"lab": labs[0], "students": students}


CODING_QUESTION = {
    "type": "coding",
    "prompt": "Read two integers and print their sum.",
    "marks": 10,
    "language": "python",
    "starterCode": "a, b = map(int, input().split())\n",
    "timeLimitMs": 3000,
    "memoryLimitMb": 128,
    "tests": [
        {"stdin": "2 3\n", "expectedStdout": "5", "hidden": False, "weight": 1},
        {"stdin": "-5 1\n", "expectedStdout": "-4", "hidden": True, "weight": 1},
        {"stdin": "-9 2\n", "expectedStdout": "-7", "hidden": True, "weight": 2},
    ],
}


def make_exam(staff, world, *, students: int = 1) -> str:
    payload = {
        "title": f"Coding Probe {uuid.uuid4().hex[:6]}",
        "code": f"CODE-{uuid.uuid4().hex[:5].upper()}",
        "course": "Programming",
        "department": "Computer Science",
        "durationMinutes": 30,
        "scheduledAt": "2026-09-01T10:00:00Z",
        "labId": world["lab"]["id"],
        "studentIds": [s["id"] for s in world["students"][:students]],
        "questions": [CODING_QUESTION],
    }
    response = client.post(f"{API}/exams", json=payload, headers=staff)
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestAuthoring:
    def test_a_coding_question_keeps_its_tests(self, staff, world):
        exam_id = make_exam(staff, world)
        detail = client.get(f"{API}/exams/{exam_id}", headers=staff).json()
        question = detail["questions"][0]
        assert question["type"] == "coding"
        assert question["language"] == "python"
        assert len(question["tests"]) == 3
        assert question["tests"][0]["expectedStdout"] == "5"

    def test_editing_a_draft_does_not_discard_the_tests(self, staff, world):
        """Create and update build questions through the same helper. When
        they did not, editing a draft silently dropped every test case and
        left the question unmarkable."""
        exam_id = make_exam(staff, world)
        response = client.patch(
            f"{API}/exams/{exam_id}",
            headers=staff,
            json={"title": "Edited", "questions": [CODING_QUESTION]},
        )
        assert response.status_code == 200, response.text
        question = client.get(f"{API}/exams/{exam_id}", headers=staff).json()["questions"][0]
        assert len(question["tests"]) == 3
        assert any(t["hidden"] for t in question["tests"])


class TestTheAnswerKeyStaysOnTheServer:
    def test_a_candidate_never_receives_a_hidden_test(self, staff, world, database):
        exam_id = make_exam(staff, world)
        client.post(f"{API}/exams/{exam_id}/schedule", headers=staff, json={})
        client.post(
            f"{API}/exams/{exam_id}/start",
            headers=staff,
            json={"idempotencyKey": f"coding-{exam_id}"},
        )

        student = world["students"][0]
        candidate = _login(student["email"])
        assert candidate is not None
        sessions = client.get(f"{API}/me/sessions", headers=candidate).json()
        mine = next(s for s in sessions if s["examId"] == exam_id)
        paper = client.post(
            f"{API}/sessions/{mine['id']}/checkin", headers=candidate, json={}
        ).json()

        question = paper["questions"][0]
        # One visible case of the three.
        assert len(question["tests"]) == 1
        # Each surviving case carries the input and nothing else. Checking the
        # keys rather than searching the payload for the expected values: the
        # values are short strings that occur inside UUIDs by chance, and a
        # test that passes by luck is worse than none here.
        assert [set(t) for t in question["tests"]] == [{"position", "stdin"}]
        assert "expectedStdout" not in str(paper)
        # The hidden cases are gone entirely, inputs included — their inputs
        # are a large part of what makes them hidden.
        assert "-5 1" not in str(paper) and "-9 2" not in str(paper)

    def test_the_candidate_gets_the_starter_code(self, staff, world, database):
        """It is not an answer, and without it a candidate spends their time
        guessing the input format instead of solving the problem."""
        exam_id = make_exam(staff, world)
        client.post(f"{API}/exams/{exam_id}/schedule", headers=staff, json={})
        client.post(
            f"{API}/exams/{exam_id}/start", headers=staff,
            json={"idempotencyKey": f"coding-start-{exam_id}"},
        )
        candidate = _login(world["students"][0]["email"])
        sessions = client.get(f"{API}/me/sessions", headers=candidate).json()
        mine = next(s for s in sessions if s["examId"] == exam_id)
        paper = client.post(
            f"{API}/sessions/{mine['id']}/checkin", headers=candidate, json={}
        ).json()
        assert paper["questions"][0]["starterCode"].startswith("a, b = map(int")


class TestMarking:
    """These use the service directly rather than the sweep: the sweep's timing
    is not what is being asserted, the marking is."""

    @needs_sandbox
    def test_a_correct_program_earns_full_marks(self, staff, world, database):
        question, answer_id = self._answer(
            staff, world, "a, b = map(int, input().split())\nprint(a + b)"
        )
        with SessionLocal() as db:
            coding.grade_session(db, answer_id)
            answer = db.get(Answer, {"session_id": answer_id, "question_id": question})
            assert float(answer.awarded_marks) == 10.0
            assert answer.run_report["passed"] == 3

    @needs_sandbox
    def test_a_program_that_fails_some_cases_earns_part_of_the_marks(self, staff, world, database):
        """Unlike multiple-response, which is all or nothing. A program that
        handles ordinary input but not negatives has done most of the work."""
        question, session_id = self._answer(
            staff, world, "a, b = map(int, input().split())\nprint(abs(a + b))"
        )
        with SessionLocal() as db:
            coding.grade_session(db, session_id)
            answer = db.get(Answer, {"session_id": session_id, "question_id": question})
            # One of four weight units: the visible case only.
            assert float(answer.awarded_marks) == 2.5

    @needs_sandbox
    def test_an_endless_program_is_marked_rather_than_hanging_the_run(self, staff, world, database):
        question, session_id = self._answer(staff, world, "while True: pass")
        with SessionLocal() as db:
            coding.grade_session(db, session_id)
            answer = db.get(Answer, {"session_id": session_id, "question_id": question})
            assert float(answer.awarded_marks) == 0.0
            assert all(c["outcome"] == "timed_out" for c in answer.run_report["cases"])

    @needs_sandbox
    def test_a_blank_answer_is_marked_zero_rather_than_left_pending(self, staff, world, database):
        """Otherwise the paper never finishes: nobody is coming to mark it."""
        question, session_id = self._answer(staff, world, "   ")
        with SessionLocal() as db:
            coding.grade_session(db, session_id)
            answer = db.get(Answer, {"session_id": session_id, "question_id": question})
            assert float(answer.awarded_marks) == 0.0

    @needs_sandbox
    def test_a_hidden_case_does_not_echo_its_output_back(self, staff, world, database):
        """The report is shown to faculty, but it is stored on the answer and
        one careless endpoint away from a candidate. Returning what a hidden
        case printed would hand over the key one submission at a time."""
        question, session_id = self._answer(
            staff, world, "a, b = map(int, input().split())\nprint(a + b)"
        )
        with SessionLocal() as db:
            coding.grade_session(db, session_id)
            answer = db.get(Answer, {"session_id": session_id, "question_id": question})
            hidden = [c for c in answer.run_report["cases"] if c["hidden"]]
            assert hidden and all(c["stdout"] == "" for c in hidden)

    @needs_sandbox
    def test_marking_twice_does_not_change_a_mark_already_given(self, staff, world, database):
        question, session_id = self._answer(
            staff, world, "a, b = map(int, input().split())\nprint(a + b)"
        )
        with SessionLocal() as db:
            first = coding.grade_session(db, session_id)
            second = coding.grade_session(db, session_id)
        assert first["graded"] == 1
        assert second == {"graded": 0, "skipped": 1}

    @needs_sandbox
    def test_forcing_a_re_run_re_marks_it(self, staff, world, database):
        """How a faculty member fixes a question whose test cases were wrong."""
        question, session_id = self._answer(
            staff, world, "a, b = map(int, input().split())\nprint(a + b)"
        )
        with SessionLocal() as db:
            coding.grade_session(db, session_id)
            again = coding.grade_session(db, session_id, force=True)
        assert again["graded"] == 1

    def _answer(self, staff, world, source: str) -> tuple[uuid.UUID, uuid.UUID]:
        """Sit the exam and submit one program. Returns (question id, session id)."""
        exam_id = make_exam(staff, world)
        client.post(f"{API}/exams/{exam_id}/schedule", headers=staff, json={})
        client.post(
            f"{API}/exams/{exam_id}/start", headers=staff,
            json={"idempotencyKey": f"coding-run-{exam_id}"},
        )
        candidate = _login(world["students"][0]["email"])
        sessions = client.get(f"{API}/me/sessions", headers=candidate).json()
        mine = next(s for s in sessions if s["examId"] == exam_id)
        paper = client.post(
            f"{API}/sessions/{mine['id']}/checkin", headers=candidate, json={}
        ).json()
        question_id = paper["questions"][0]["id"]

        saved = client.put(
            f"{API}/sessions/{mine['id']}/answers/{question_id}",
            headers=candidate,
            json={"value": {"kind": "code", "source": source}, "clientSeq": 1},
        )
        assert saved.status_code == 200, saved.text
        client.post(f"{API}/sessions/{mine['id']}/submit", headers=candidate, json={})
        return uuid.UUID(question_id), uuid.UUID(mine["id"])


class TestPendingUntilMarked:
    @needs_sandbox
    def test_an_unmarked_program_is_pending_rather_than_zero(self, staff, world, database):
        """A results screen that shows 0/10 while nobody has run the code is
        telling a candidate they failed."""
        marking = TestMarking()
        question, session_id = marking._answer(
            staff, world, "a, b = map(int, input().split())\nprint(a + b)"
        )
        with SessionLocal() as db:
            answer = db.get(Answer, {"session_id": session_id, "question_id": question})
            assert answer.awarded_marks is None


class TestNormalisingOutput:
    def test_a_trailing_newline_does_not_fail_a_correct_answer(self):
        assert coding.normalise("5\n\n") == coding.normalise("5")

    def test_trailing_spaces_do_not_fail_a_correct_answer(self):
        assert coding.normalise("5   ") == coding.normalise("5")

    def test_a_blank_line_in_the_middle_still_counts(self):
        """Forgiving about the edges, strict about the content."""
        assert coding.normalise("a\n\nb") != coding.normalise("a\nb")

    def test_case_still_counts(self):
        assert coding.normalise("Yes") != coding.normalise("yes")
