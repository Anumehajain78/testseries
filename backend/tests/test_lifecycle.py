"""Exam lifecycle tests, against the real database.

These assert the three properties the write path exists to guarantee: the
server owns the clock, start is idempotent, and capacity is enforced where it
cannot be edited away.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import issue_user_tokens
from app.main import app
from app.schemas.enums import Role

client = TestClient(app)
API = "/api/v1"


@pytest.fixture(scope="module")
def staff(database) -> dict[str, str]:
    """A real seeded faculty credential.

    Obtained by logging in rather than minted locally: the role guard reads the
    user back from the database, so a token naming nobody is correctly refused.
    """
    response = client.post(
        f"{API}/auth/login",
        json={"email": "anita.rao@northbridge.edu", "password": "examcontrol"},
    )
    if response.status_code != 200:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


@pytest.fixture(scope="module")
def world(staff) -> dict:
    labs = client.get(f"{API}/labs", headers=staff)
    if labs.status_code != 200 or not labs.json():
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    students = client.get(f"{API}/students?limit=200", headers=staff).json()["items"]
    return {"labs": labs.json(), "students": students}


def make_draft(staff, world, *, students: int = 3, lab_index: int = 0, duration: int = 30) -> str:
    """A minimal draft with an inline paper."""
    lab = world["labs"][lab_index]
    payload = {
        "title": f"Lifecycle Probe {uuid.uuid4().hex[:6]}",
        "code": f"PROBE-{uuid.uuid4().hex[:4].upper()}",
        "course": "Lifecycle Testing",
        "department": "Computer Science",
        "durationMinutes": duration,
        "scheduledAt": "2026-09-01T10:00:00Z",
        "labId": lab["id"],
        "studentIds": [s["id"] for s in world["students"][:students]],
        "questions": [
            {
                "type": "mcq",
                "prompt": "Does the server own the clock?",
                "marks": 2,
                "options": [{"body": "Yes", "isCorrect": True}, {"body": "No", "isCorrect": False}],
            }
        ],
    }
    response = client.post(f"{API}/exams", json=payload, headers=staff)
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestCreate:
    def test_a_new_exam_starts_as_a_draft_with_no_window(self, staff, world):
        exam = client.get(f"{API}/exams/{make_draft(staff, world)}", headers=staff).json()
        assert exam["status"] == "DRAFT"
        # A draft has never run, so it must not carry an authoritative window.
        assert exam["startsAt"] is None
        assert exam["endsAt"] is None

    def test_inline_questions_land_in_the_paper(self, staff, world):
        exam = client.get(f"{API}/exams/{make_draft(staff, world)}", headers=staff).json()
        assert exam["questionCount"] == 1
        assert exam["totalMarks"] == 2

    def test_an_exam_without_questions_is_refused(self, staff, world):
        payload = {
            "title": "Empty", "code": "EMPTY-1", "course": "C", "department": "D",
            "durationMinutes": 30, "scheduledAt": "2026-09-01T10:00:00Z",
            "labId": world["labs"][0]["id"], "studentIds": [], "questions": [],
        }
        assert client.post(f"{API}/exams", json=payload, headers=staff).status_code == 422


class TestSchedule:
    def test_scheduling_seats_every_enrolled_candidate(self, staff, world):
        exam_id = make_draft(staff, world, students=5)
        response = client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        assert response.status_code == 200, response.text
        # Seating is what READY means.
        assert response.json()["status"] == "READY"
        rows = client.get(f"{API}/exams/{exam_id}/sessions", headers=staff).json()
        assert len(rows) == 5
        assert all(row["machineId"] for row in rows)

    def test_scheduling_twice_does_not_duplicate_sessions(self, staff, world):
        exam_id = make_draft(staff, world, students=4)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        # The second call is refused, and the roster is untouched either way.
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        rows = client.get(f"{API}/exams/{exam_id}/sessions", headers=staff).json()
        assert len(rows) == 4

    def test_a_roster_larger_than_the_lab_is_refused(self, staff, world):
        # Networks Laboratory seats 24; the seeded roster is 60.
        small = min(world["labs"], key=lambda lab: lab["computerCount"])
        lab_index = world["labs"].index(small)
        exam_id = make_draft(staff, world, students=len(world["students"]), lab_index=lab_index)
        response = client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        assert response.status_code == 422
        assert "seats" in response.text

    def test_an_empty_roster_cannot_be_scheduled(self, staff, world):
        exam_id = make_draft(staff, world, students=0)
        assert client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff).status_code == 422


class TestStart:
    def test_starting_stamps_a_server_owned_window(self, staff, world):
        exam_id = make_draft(staff, world, students=3, duration=45)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        response = client.post(f"{API}/exams/{exam_id}/start", json={}, headers=staff)
        assert response.status_code == 200, response.text
        window = response.json()
        assert window["status"] == "LIVE"
        assert window["startsAt"] < window["endsAt"]
        assert window["releasedSessionCount"] == 3

    def test_a_retry_does_not_move_the_deadline(self, staff, world):
        """An invigilator double-clicking must not extend a room's exam."""
        exam_id = make_draft(staff, world, students=3)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        key = {"idempotencyKey": "same-attempt"}
        first = client.post(f"{API}/exams/{exam_id}/start", json=key, headers=staff).json()
        second = client.post(f"{API}/exams/{exam_id}/start", json=key, headers=staff).json()
        assert first["startsAt"] == second["startsAt"]
        assert first["endsAt"] == second["endsAt"]

    def test_a_retry_does_not_re_release_candidates(self, staff, world):
        exam_id = make_draft(staff, world, students=3)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        client.post(f"{API}/exams/{exam_id}/start", json={}, headers=staff)
        before = client.get(f"{API}/exams/{exam_id}/sessions", headers=staff).json()
        client.post(f"{API}/exams/{exam_id}/start", json={}, headers=staff)
        after = client.get(f"{API}/exams/{exam_id}/sessions", headers=staff).json()
        assert [r["startedAt"] for r in before] == [r["startedAt"] for r in after]

    def test_a_draft_cannot_be_started(self, staff, world):
        """Without seating there is no roster to release."""
        exam_id = make_draft(staff, world)
        response = client.post(f"{API}/exams/{exam_id}/start", json={}, headers=staff)
        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["currentState"] == "DRAFT"
        assert body["requestedState"] == "LIVE"


class TestEndAndCancel:
    def test_ending_sweeps_active_candidates_to_auto_submitted(self, staff, world):
        exam_id = make_draft(staff, world, students=3)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        client.post(f"{API}/exams/{exam_id}/start", json={}, headers=staff)
        assert client.post(f"{API}/exams/{exam_id}/end", json={}, headers=staff).status_code == 200

        exam = client.get(f"{API}/exams/{exam_id}", headers=staff).json()
        assert exam["status"] == "COMPLETED"
        rows = client.get(f"{API}/exams/{exam_id}/sessions", headers=staff).json()
        assert all(row["status"] == "AUTO_SUBMITTED" for row in rows)

    def test_a_candidate_who_never_started_is_terminated_not_auto_submitted(self, staff, world):
        """An absent candidate is not one who submitted nothing."""
        exam_id = make_draft(staff, world, students=3)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        client.post(f"{API}/exams/{exam_id}/cancel", json={"reason": "Power failure in the block"},
                    headers=staff)
        rows = client.get(f"{API}/exams/{exam_id}/sessions", headers=staff).json()
        assert all(row["status"] == "TERMINATED" for row in rows)

    def test_cancelling_requires_a_reason(self, staff, world):
        exam_id = make_draft(staff, world)
        assert client.post(f"{API}/exams/{exam_id}/cancel", json={}, headers=staff).status_code == 422

    def test_a_completed_exam_cannot_be_restarted(self, staff, world):
        exam_id = make_draft(staff, world, students=2)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        client.post(f"{API}/exams/{exam_id}/start", json={}, headers=staff)
        client.post(f"{API}/exams/{exam_id}/end", json={}, headers=staff)
        assert client.post(f"{API}/exams/{exam_id}/start", json={}, headers=staff).status_code == 409


class TestEditability:
    def test_a_draft_can_be_edited(self, staff, world):
        exam_id = make_draft(staff, world)
        response = client.patch(f"{API}/exams/{exam_id}", json={"title": "Renamed"}, headers=staff)
        assert response.status_code == 200
        assert response.json()["title"] == "Renamed"

    def test_a_scheduled_exam_cannot_be_edited(self, staff, world):
        """Changing a paper after candidates are seated would invalidate the
        seating and the window they were promised."""
        exam_id = make_draft(staff, world, students=2)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        response = client.patch(f"{API}/exams/{exam_id}", json={"title": "Too late"}, headers=staff)
        assert response.status_code == 409


class TestResultsPublication:
    def test_publishing_reveals_scores_and_withholding_hides_them(self, staff, world):
        # Earlier tests in this module complete their own probe exams, which
        # have no grades, so pick a completed exam that actually has rows.
        exam_id = None
        for exam in client.get(f"{API}/exams?limit=200", headers=staff).json()["items"]:
            if exam["status"] != "COMPLETED":
                continue
            page = client.get(f"{API}/exams/{exam['id']}/results", headers=staff).json()
            if page["rows"]:
                exam_id = exam["id"]
                break
        if exam_id is None:
            pytest.skip("no graded completed exam: run `python -m app.db.seed`")

        published = client.post(f"{API}/exams/{exam_id}/results/publish",
                                json={"published": True}, headers=staff).json()
        assert published["published"] is True
        assert published["rows"][0]["score"] is not None

        withheld = client.post(f"{API}/exams/{exam_id}/results/publish",
                               json={"published": False}, headers=staff).json()
        # Withheld means the score never reaches the client, not that the UI
        # hides a value it was given.
        assert withheld["published"] is False
        assert withheld["rows"][0]["score"] is None


class TestWriteGuards:
    def test_writes_require_a_credential(self, world):
        assert client.post(f"{API}/exams", json={}).status_code == 401

    def test_a_candidate_cannot_create_an_exam(self, world):
        student = world["students"][0]
        token = client.post(
            f"{API}/auth/login",
            json={"email": student["email"], "password": "examcontrol"},
        ).json()["accessToken"]
        response = client.post(f"{API}/exams", json={}, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    def test_a_token_naming_a_deleted_account_is_refused(self, world):
        # A token outlives the row it names; it must stop working immediately,
        # not at expiry.
        access, _, _ = issue_user_tokens(uuid.uuid4(), Role.FACULTY)
        response = client.get(f"{API}/exams", headers={"Authorization": f"Bearer {access}"})
        assert response.status_code == 401


class TestEditingADraft:
    """Editing exists so a mistake in a draft can be corrected without
    starting over. It stops the moment candidates are seated."""

    def test_the_basics_can_be_changed(self, staff, world):
        exam_id = make_draft(staff, world)
        response = client.patch(
            f"{API}/exams/{exam_id}",
            json={"title": "Renamed Paper", "durationMinutes": 55, "course": "New Course"},
            headers=staff,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["title"] == "Renamed Paper"
        assert body["durationMinutes"] == 55
        assert body["course"] == "New Course"

    def test_the_paper_can_be_rewritten(self, staff, world):
        """Without this the editor could change everything about an exam
        except the questions, which is the thing most likely to be wrong."""
        exam_id = make_draft(staff, world)
        response = client.patch(
            f"{API}/exams/{exam_id}",
            json={"questions": [
                {"type": "mcq", "prompt": "Replaced question one?", "marks": 4,
                 "options": [{"body": "Yes", "isCorrect": True}, {"body": "No", "isCorrect": False}]},
                {"type": "mcq", "prompt": "Replaced question two?", "marks": 6,
                 "options": [{"body": "Yes", "isCorrect": True}, {"body": "No", "isCorrect": False}]},
            ]},
            headers=staff,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["questionCount"] == 2
        assert body["totalMarks"] == 10
        assert [q["prompt"] for q in body["questions"]] == [
            "Replaced question one?", "Replaced question two?"
        ]

    def test_the_roster_can_be_changed(self, staff, world):
        exam_id = make_draft(staff, world, students=2)
        ids = [s["id"] for s in world["students"][:5]]
        response = client.patch(f"{API}/exams/{exam_id}", json={"studentIds": ids}, headers=staff)
        assert response.status_code == 200
        assert response.json()["enrolledCount"] == 5

    def test_fields_left_out_are_left_alone(self, staff, world):
        """A partial edit must not blank everything the form did not send."""
        exam_id = make_draft(staff, world, students=3)
        before = client.get(f"{API}/exams/{exam_id}", headers=staff).json()
        after = client.patch(f"{API}/exams/{exam_id}", json={"title": "Only the title"}, headers=staff).json()
        assert after["title"] == "Only the title"
        assert after["enrolledCount"] == before["enrolledCount"]
        assert after["questionCount"] == before["questionCount"]
        assert after["durationMinutes"] == before["durationMinutes"]

    def test_a_seated_exam_cannot_be_edited(self, staff, world):
        exam_id = make_draft(staff, world, students=2)
        client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=staff)
        response = client.patch(f"{API}/exams/{exam_id}", json={"title": "Too late"}, headers=staff)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "not_editable"

    def test_a_candidate_cannot_edit_an_exam(self, staff, world):
        exam_id = make_draft(staff, world)
        token = client.post(
            f"{API}/auth/login",
            json={"email": world["students"][0]["email"], "password": "examcontrol"},
        ).json()["accessToken"]
        response = client.patch(
            f"{API}/exams/{exam_id}", json={"title": "Nope"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
