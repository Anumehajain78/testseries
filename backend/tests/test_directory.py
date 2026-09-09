"""Candidate records.

Adding people is the point at which a college stops being able to use the seed
and starts using the platform. These assert that it works, that it refuses the
things that would corrupt a register, and that an import survives the one bad
row every real roster has in it.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
API = "/api/v1"


def _token(email: str) -> str | None:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "examcontrol"})
    return response.json()["accessToken"] if response.status_code == 200 else None


@pytest.fixture(scope="module")
def admin(database) -> dict[str, str]:
    token = _token("admin@northbridge.edu")
    if token is None:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def faculty(database) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token('anita.rao@northbridge.edu')}"}


def _new(suffix: str) -> dict:
    return {
        "registrationNo": f"24TST{suffix}",
        "fullName": f"Test Candidate {suffix}",
        "email": f"candidate.{suffix}@northbridge.edu",
        "program": "B.Tech CSE",
        "semester": 3,
        "section": "A",
    }


class TestAddingACandidate:
    def test_a_candidate_can_be_added(self, admin):
        response = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin)
        assert response.status_code == 201, response.text
        assert response.json()["student"]["status"] == "ACTIVE"

    def test_the_password_is_generated_and_shown_once(self, admin):
        """A college cannot invent sixty passwords, and a guessable default
        would let any candidate sign in as any other."""
        created = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        password = created["temporaryPassword"]
        assert len(password) >= 8
        # It is not derived from anything a classmate would know.
        assert created["student"]["registrationNo"] not in password

        listed = client.get(f"{API}/students?limit=200", headers=admin).text
        assert password not in listed, "a password must never be readable again"

    def test_the_new_candidate_can_sign_in_with_it(self, admin):
        created = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        response = client.post(
            f"{API}/auth/login",
            json={"email": created["student"]["email"], "password": created["temporaryPassword"]},
        )
        assert response.status_code == 200

    def test_a_duplicate_email_is_refused(self, admin):
        payload = _new(uuid.uuid4().hex[:5])
        client.post(f"{API}/students", json=payload, headers=admin)
        again = client.post(f"{API}/students", json={**payload, "registrationNo": "24TSTZZZ"}, headers=admin)
        assert again.status_code == 409

    def test_a_duplicate_registration_number_is_refused(self, admin):
        """Two people sharing one number would make a results table ambiguous."""
        payload = _new(uuid.uuid4().hex[:5])
        client.post(f"{API}/students", json=payload, headers=admin)
        again = client.post(
            f"{API}/students",
            json={**payload, "email": f"other.{uuid.uuid4().hex[:5]}@northbridge.edu"},
            headers=admin,
        )
        assert again.status_code == 409

    def test_faculty_cannot_add_a_candidate(self, faculty):
        """Faculty author assessments; the register is the exam cell's.

        Gating only the bulk import would have been decoration: the same
        person could paste the same sixty rows one form at a time.
        """
        response = client.post(f"{API}/students", json=_new("F01"), headers=faculty)
        assert response.status_code == 403

    def test_a_candidate_cannot_add_candidates(self, admin):
        created = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        token = client.post(
            f"{API}/auth/login",
            json={"email": created["student"]["email"], "password": created["temporaryPassword"]},
        ).json()["accessToken"]
        response = client.post(
            f"{API}/students", json=_new(uuid.uuid4().hex[:5]),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


class TestEditingACandidate:
    def test_details_can_be_corrected(self, admin):
        created = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        response = client.patch(
            f"{API}/students/{created['student']['id']}",
            json={"fullName": "Corrected Name", "section": "B"},
            headers=admin,
        )
        assert response.status_code == 200
        assert response.json()["fullName"] == "Corrected Name"
        assert response.json()["section"] == "B"

    def test_blocking_a_candidate_stops_them_signing_in(self, admin):
        """Otherwise 'blocked' is decoration on a screen rather than a fact."""
        created = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        credentials = {
            "email": created["student"]["email"],
            "password": created["temporaryPassword"],
        }
        assert client.post(f"{API}/auth/login", json=credentials).status_code == 200

        client.patch(
            f"{API}/students/{created['student']['id']}", json={"status": "BLOCKED"}, headers=admin
        )
        assert client.post(f"{API}/auth/login", json=credentials).status_code == 403

    def test_unblocking_lets_them_back_in(self, admin):
        created = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        credentials = {
            "email": created["student"]["email"],
            "password": created["temporaryPassword"],
        }
        student_id = created["student"]["id"]
        client.patch(f"{API}/students/{student_id}", json={"status": "BLOCKED"}, headers=admin)
        client.patch(f"{API}/students/{student_id}", json={"status": "ACTIVE"}, headers=admin)
        assert client.post(f"{API}/auth/login", json=credentials).status_code == 200

    def test_faculty_cannot_edit_the_register(self, admin, faculty):
        student = client.post(f"{API}/students", json=_new("F02"), headers=admin).json()
        response = client.patch(
            f"{API}/students/{student['student']['id']}",
            json={"section": "C"},
            headers=faculty,
        )
        assert response.status_code == 403

    def test_taking_someone_elses_email_is_refused(self, admin):
        first = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        second = client.post(f"{API}/students", json=_new(uuid.uuid4().hex[:5]), headers=admin).json()
        response = client.patch(
            f"{API}/students/{second['student']['id']}",
            json={"email": first["student"]["email"]},
            headers=admin,
        )
        assert response.status_code == 409


class TestImportingARoster:
    HEADER = "registration_no,full_name,email,program,semester,section"

    def _csv(self, *rows: str) -> str:
        return "\n".join([self.HEADER, *rows])

    def test_a_clean_file_creates_everyone(self, admin):
        tag = uuid.uuid4().hex[:5]
        body = self._csv(
            f"24IMP{tag}1,Import One,imp.{tag}.1@northbridge.edu,B.Tech CSE,3,A",
            f"24IMP{tag}2,Import Two,imp.{tag}.2@northbridge.edu,B.Tech CSE,3,A",
        )
        response = client.post(f"{API}/students/import", json={"csv": body}, headers=admin)
        assert response.status_code == 200, response.text
        summary = response.json()
        assert len(summary["created"]) == 2
        assert summary["failed"] == []

    def test_one_bad_row_does_not_sink_the_file(self, admin):
        """Every real roster has a duplicate or a typo in it."""
        tag = uuid.uuid4().hex[:5]
        body = self._csv(
            f"24IMP{tag}3,Good One,good.{tag}@northbridge.edu,B.Tech CSE,3,A",
            f"24IMP{tag}4,Bad Email,not-an-email,B.Tech CSE,3,A",
            f"24IMP{tag}5,Good Two,good2.{tag}@northbridge.edu,B.Tech CSE,3,A",
        )
        summary = client.post(f"{API}/students/import", json={"csv": body}, headers=admin).json()
        assert len(summary["created"]) == 2
        assert len(summary["failed"]) == 1

    def test_a_rejected_row_says_which_line_and_why(self, admin):
        tag = uuid.uuid4().hex[:5]
        body = self._csv(f"24IMP{tag}6,Bad Email,nope,B.Tech CSE,3,A")
        failed = client.post(f"{API}/students/import", json={"csv": body}, headers=admin).json()["failed"][0]
        assert failed["line"] == 2  # the header is line 1
        assert failed["registrationNo"] == f"24IMP{tag}6"
        assert "email" in failed["reason"].lower()

    def test_a_duplicate_is_reported_rather_than_silently_skipped(self, admin):
        tag = uuid.uuid4().hex[:5]
        row = f"24IMP{tag}7,Twice Over,twice.{tag}@northbridge.edu,B.Tech CSE,3,A"
        client.post(f"{API}/students/import", json={"csv": self._csv(row)}, headers=admin)
        summary = client.post(f"{API}/students/import", json={"csv": self._csv(row)}, headers=admin).json()
        assert summary["created"] == []
        assert len(summary["failed"]) == 1
        assert "already" in summary["failed"][0]["reason"].lower()

    def test_a_file_missing_columns_is_refused_with_the_names(self, admin):
        response = client.post(
            f"{API}/students/import", json={"csv": "registration_no,full_name\n24X,Someone"}, headers=admin
        )
        assert response.status_code == 422
        assert "email" in response.json()["detail"]

    def test_faculty_cannot_import_a_roster(self, faculty):
        """Rewriting the register is an administrative act."""
        response = client.post(
            f"{API}/students/import",
            json={"csv": "registration_no,full_name,email,program,semester,section\n24X,A,a@b.edu,C,3,A"},
            headers=faculty,
        )
        assert response.status_code == 403
