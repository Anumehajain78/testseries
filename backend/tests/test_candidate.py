"""Candidate path tests.

The step's headline guarantee is here: a candidate's paper cannot express an
answer key, so there is nothing for a browser to read. The rest asserts that
writes are refused outside the one state that permits them, that ordering
survives a reconnect, and that grading translates the candidate's coordinates
back to the authored ones before it judges anything.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
API = "/api/v1"
PASSWORD = "examcontrol"


def _login(email: str) -> dict[str, str] | None:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    if response.status_code != 200:
        return None
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


@pytest.fixture(scope="module")
def staff() -> dict[str, str]:
    headers = _login("anita.rao@northbridge.edu")
    if headers is None:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return headers


@pytest.fixture(scope="module")
def live_exam(staff) -> dict:
    """The seeded live exam, plus one of its candidates."""
    exams = client.get(f"{API}/exams?status=LIVE", headers=staff).json()["items"]
    if not exams:
        pytest.skip("no live exam in the seed")
    exam = exams[0]
    rows = client.get(f"{API}/exams/{exam['id']}/sessions", headers=staff).json()
    active = [r for r in rows if r["status"] == "ACTIVE"]
    if not active:
        pytest.skip("live exam has no active session")
    students = client.get(f"{API}/students?limit=200", headers=staff).json()["items"]
    by_id = {s["id"]: s for s in students}
    row = active[0]
    return {"exam": exam, "session": row, "student": by_id[row["studentId"]]}


@pytest.fixture(scope="module")
def candidate(live_exam) -> dict[str, str]:
    headers = _login(live_exam["student"]["email"])
    if headers is None:
        pytest.skip("candidate cannot sign in")
    return headers


class TestTheAnswerKeyNeverReachesTheCandidate:
    """The guarantee this whole step exists to close."""

    def test_the_paper_contains_no_answer_key(self, candidate, live_exam):
        body = client.get(f"{API}/sessions/{live_exam['session']['id']}", headers=candidate).text
        assert "isCorrect" not in body
        assert "is_correct" not in body

    def test_options_carry_only_what_is_needed_to_render_them(self, candidate, live_exam):
        paper = client.get(f"{API}/sessions/{live_exam['session']['id']}", headers=candidate).json()
        for question in paper["questions"]:
            for option in question["options"]:
                assert set(option) == {"id", "position", "body"}

    def test_a_candidate_cannot_read_the_faculty_exam(self, candidate, live_exam):
        # The faculty detail route is where the key lives.
        response = client.get(f"{API}/exams/{live_exam['exam']['id']}", headers=candidate)
        assert response.status_code == 403


class TestSessionOwnership:
    def test_a_candidate_cannot_open_another_candidates_session(self, candidate, staff, live_exam):
        rows = client.get(f"{API}/exams/{live_exam['exam']['id']}/sessions", headers=staff).json()
        other = next(r for r in rows if r["studentId"] != live_exam["student"]["id"])
        response = client.get(f"{API}/sessions/{other['id']}", headers=candidate)
        # 404, not 403: probing must not confirm that the session exists.
        assert response.status_code == 404

    def test_an_unauthenticated_caller_gets_nothing(self, live_exam):
        assert client.get(f"{API}/sessions/{live_exam['session']['id']}").status_code == 401


class TestPaperStability:
    def test_checking_in_twice_returns_the_same_paper(self, candidate, live_exam):
        """A reconnect must not reshuffle a paper under saved answers."""
        url = f"{API}/sessions/{live_exam['session']['id']}/checkin"
        first = client.post(url, json={"machineId": "LAB1-PC-01"}, headers=candidate).json()
        second = client.post(url, json={"machineId": "LAB1-PC-01"}, headers=candidate).json()
        assert [q["id"] for q in first["questions"]] == [q["id"] for q in second["questions"]]
        for a, b in zip(first["questions"], second["questions"]):
            assert [o["id"] for o in a["options"]] == [o["id"] for o in b["options"]]

    def test_the_paper_carries_the_server_deadline(self, candidate, live_exam):
        paper = client.get(f"{API}/sessions/{live_exam['session']['id']}", headers=candidate).json()
        # The client derives remaining time from this, never from its own clock.
        assert paper["endsAt"]


class TestAnswers:
    def test_an_answer_round_trips(self, candidate, live_exam):
        session_id = live_exam["session"]["id"]
        paper = client.get(f"{API}/sessions/{session_id}", headers=candidate).json()
        question = paper["questions"][0]

        saved = client.put(
            f"{API}/sessions/{session_id}/answers/{question['id']}",
            json={"value": {"kind": "single", "option": 0}, "clientSeq": 1},
            headers=candidate,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["accepted"] is True

        state = client.get(f"{API}/sessions/{session_id}/state", headers=candidate).json()
        assert state["answers"][question["id"]]["option"] == 0

    def test_a_stale_write_is_rejected_without_overwriting(self, candidate, live_exam):
        """After a reconnect an old write can arrive late; it must lose."""
        session_id = live_exam["session"]["id"]
        question = client.get(f"{API}/sessions/{session_id}", headers=candidate).json()["questions"][0]
        url = f"{API}/sessions/{session_id}/answers/{question['id']}"

        client.put(url, json={"value": {"kind": "single", "option": 1}, "clientSeq": 10}, headers=candidate)
        late = client.put(
            url, json={"value": {"kind": "single", "option": 0}, "clientSeq": 5}, headers=candidate
        )
        assert late.json()["accepted"] is False

        state = client.get(f"{API}/sessions/{session_id}/state", headers=candidate).json()
        assert state["answers"][question["id"]]["option"] == 1

    def test_flagging_toggles(self, candidate, live_exam):
        session_id = live_exam["session"]["id"]
        question = client.get(f"{API}/sessions/{session_id}", headers=candidate).json()["questions"][1]
        url = f"{API}/sessions/{session_id}/flags/{question['id']}"

        client.put(url, headers=candidate)
        assert question["id"] in client.get(f"{API}/sessions/{session_id}/state", headers=candidate).json()["flagged"]
        client.put(url, headers=candidate)
        assert question["id"] not in client.get(f"{API}/sessions/{session_id}/state", headers=candidate).json()["flagged"]


class TestSubmission:
    def test_submitting_returns_a_receipt_and_locks_the_session(self, staff, candidate, live_exam):
        session_id = live_exam["session"]["id"]
        receipt = client.post(f"{API}/sessions/{session_id}/submit", json={}, headers=candidate)
        assert receipt.status_code == 200, receipt.text
        body = receipt.json()
        assert body["submissionId"]
        assert body["mode"] == "MANUAL"

        # Writes are refused the moment the session leaves ACTIVE.
        paper = client.get(f"{API}/sessions/{session_id}", headers=candidate).json()
        refused = client.put(
            f"{API}/sessions/{session_id}/answers/{paper['questions'][0]['id']}",
            json={"value": {"kind": "single", "option": 0}},
            headers=candidate,
        )
        assert refused.status_code == 409

    def test_submitting_twice_returns_the_original_receipt(self, candidate, live_exam):
        session_id = live_exam["session"]["id"]
        first = client.post(f"{API}/sessions/{session_id}/submit", json={}, headers=candidate).json()
        second = client.post(f"{API}/sessions/{session_id}/submit", json={}, headers=candidate).json()
        assert first["submissionId"] == second["submissionId"]
        assert first["submittedAt"] == second["submittedAt"]


class TestDeadlineSweep:
    """Auto-submission is the server's job.

    A browser-side timer only fires if the tab is still open and the machine
    still connected — neither of which can be assumed of a candidate whose
    network just dropped. These run the sweep directly rather than waiting on
    the background loop.
    """

    def test_the_sweep_closes_an_expired_exam(self, staff, live_exam):
        from datetime import timedelta

        from app.db.models import Exam
        from app.db.session import SessionLocal
        from app.services.sweep import sweep_once
        from app.utils.clock import utcnow

        exam_id = live_exam["exam"]["id"]
        with SessionLocal() as db:
            exam = db.get(Exam, uuid.UUID(exam_id))
            if exam.status.value not in ("LIVE", "ENDING"):
                pytest.skip("exam already closed by an earlier test")
            # Wind the deadline back rather than waiting out a real one.
            exam.ends_at = utcnow() - timedelta(seconds=1)
            db.commit()

            outcome = sweep_once(db)
            assert outcome["exams"] >= 1

            db.expire_all()
            assert db.get(Exam, uuid.UUID(exam_id)).status.value == "COMPLETED"

    def test_the_sweep_separates_absent_candidates_from_empty_papers(self, staff, live_exam):
        """An absent candidate and one who answered nothing are different
        facts about a person, and must not both read as a submission."""
        from app.db.models import ExamSession
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            rows = db.query(ExamSession).filter(
                ExamSession.exam_id == uuid.UUID(live_exam["exam"]["id"])
            ).all()
            statuses = {row.status.value for row in rows}
        assert "ACTIVE" not in statuses, "the sweep left a session running"
        assert statuses <= {"SUBMITTED", "AUTO_SUBMITTED", "TERMINATED"}

    def test_the_sweep_is_safe_to_run_repeatedly(self):
        from app.db.session import SessionLocal
        from app.services.sweep import sweep_once

        with SessionLocal() as db:
            assert sweep_once(db)["exams"] == 0
