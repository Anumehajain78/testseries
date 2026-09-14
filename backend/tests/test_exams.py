"""Who may author an assessment.

The route has always admitted any staff principal, but ``exams.created_by``
and ``questions.owner_id`` both reference the faculty table, and an exam cell
administrator has no row there. So an administrator creating an assessment
died as a foreign key violation and reached them as a 500.

Found by the load harness, which signs in as an administrator to set its
cohort up — which is also exactly what the seeded admin account does in the
browser.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
API = "/api/v1"


def _login(email: str) -> dict[str, str] | None:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "examcontrol"})
    if response.status_code != 200:
        return None
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


@pytest.fixture(scope="module")
def admin(database) -> dict[str, str]:
    headers = _login("admin@northbridge.edu")
    if headers is None:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return headers


@pytest.fixture(scope="module")
def faculty(database) -> dict[str, str]:
    headers = _login("anita.rao@northbridge.edu")
    if headers is None:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return headers


@pytest.fixture(scope="module")
def lab_id(admin) -> str:
    labs = client.get(f"{API}/labs", headers=admin)
    if labs.status_code != 200 or not labs.json():
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return labs.json()[0]["id"]


def _payload(lab: str) -> dict:
    return {
        "title": f"Authoring Probe {uuid.uuid4().hex[:6]}",
        "code": f"AUTH-{uuid.uuid4().hex[:6].upper()}",
        "course": "Authoring",
        "department": "Computer Science",
        "durationMinutes": 30,
        "scheduledAt": "2026-09-01T10:00:00Z",
        "labId": lab,
        "questions": [
            {
                "type": "mcq",
                "prompt": "May an administrator author this?",
                "marks": 1,
                "options": [{"body": "Yes", "isCorrect": True}, {"body": "No", "isCorrect": False}],
            }
        ],
    }


class TestAdministratorAuthoring:
    def test_an_administrator_can_create_an_exam(self, admin, lab_id):
        response = client.post(f"{API}/exams", headers=admin, json=_payload(lab_id))
        assert response.status_code == 201, response.text

    def test_the_administrator_is_named_as_the_author(self, admin, lab_id):
        """Not left null. An assessment with no author is a record of nothing."""
        created = client.post(f"{API}/exams", headers=admin, json=_payload(lab_id)).json()
        assert created["createdBy"]

    def test_a_second_exam_reuses_the_same_authoring_record(self, admin, lab_id):
        """The record is created once for the person, not once per exam."""
        first = client.post(f"{API}/exams", headers=admin, json=_payload(lab_id))
        second = client.post(f"{API}/exams", headers=admin, json=_payload(lab_id))
        assert (first.status_code, second.status_code) == (201, 201)
        assert first.json()["createdBy"] == second.json()["createdBy"]

    def test_faculty_authoring_is_unchanged(self, faculty, lab_id):
        """The fix must not disturb the people it was already working for."""
        response = client.post(f"{API}/exams", headers=faculty, json=_payload(lab_id))
        assert response.status_code == 201, response.text

    def test_an_administrator_can_schedule_and_start_one(self, admin, lab_id):
        """The one that mattered: start happens with a room already waiting.

        ``exams.started_by`` references faculty too, so fixing only creation
        moved the 500 from the quiet action to the loudest one.
        """
        students = client.get(f"{API}/students?limit=3", headers=admin).json()["items"]
        payload = _payload(lab_id) | {"studentIds": [s["id"] for s in students]}
        exam = client.post(f"{API}/exams", headers=admin, json=payload).json()

        scheduled = client.post(f"{API}/exams/{exam['id']}/schedule", headers=admin, json={})
        assert scheduled.status_code == 200, scheduled.text

        started = client.post(
            f"{API}/exams/{exam['id']}/start",
            headers=admin,
            json={"idempotencyKey": f"admin-start-{exam['id']}"},
        )
        assert started.status_code == 200, started.text
        assert started.json()["startsAt"]

    def test_an_administrator_can_edit_a_draft(self, admin, lab_id):
        """Editing authors questions, and those carry an owner."""
        exam = client.post(f"{API}/exams", headers=admin, json=_payload(lab_id)).json()
        response = client.patch(f"{API}/exams/{exam['id']}", headers=admin, json={
            "title": "Edited by the exam cell",
            "questions": [{
                "type": "mcq",
                "prompt": "Authored during an edit?",
                "marks": 1,
                "options": [{"body": "Yes", "isCorrect": True}, {"body": "No", "isCorrect": False}],
            }],
        })
        assert response.status_code == 200, response.text

    def test_a_candidate_still_cannot_author_one(self, lab_id, database):
        headers = _login("aarav.mehta@northbridge.edu")
        assert headers is not None
        response = client.post(f"{API}/exams", headers=headers, json=_payload(lab_id))
        assert response.status_code == 403
