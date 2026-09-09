"""Lab computer enrolment and reporting.

A workstation is not a person, and these assert what falls out of that: it
claims a known machine rather than inventing one, it holds its own secret
rather than sharing the room's, and the credential it ends up with reaches
exactly two endpoints and no more.
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


@pytest.fixture(scope="module")
def lab(admin) -> dict:
    labs = client.get(f"{API}/labs", headers=admin).json()
    return labs[0]


@pytest.fixture(scope="module")
def machine(admin, lab) -> str:
    computers = client.get(f"{API}/labs/{lab['id']}/computers", headers=admin).json()
    return computers[0]["machineId"]


def _mint(admin, lab) -> str:
    response = client.post(f"{API}/labs/{lab['id']}/enrolment-token", headers=admin)
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _enrol(admin, lab, machine_id: str) -> dict:
    token = _mint(admin, lab)
    response = client.post(
        f"{API}/auth/machine/enrol",
        json={"enrolmentToken": token, "machineId": machine_id, "hostname": "probe.local"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _machine_headers(credential: dict) -> dict[str, str]:
    response = client.post(
        f"{API}/auth/machine/token",
        json={"machineId": credential["machineId"], "secret": credential["secret"]},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


class TestMintingTheEnrolmentToken:
    def test_an_administrator_can_mint_one(self, admin, lab):
        response = client.post(f"{API}/labs/{lab['id']}/enrolment-token", headers=admin)
        assert response.status_code == 200
        body = response.json()
        assert body["token"]
        assert body["labName"] == lab["name"]
        assert body["expiresAt"]

    def test_faculty_cannot_mint_one(self, faculty, lab):
        """Adding a machine to an examination room is an administrative act."""
        assert client.post(f"{API}/labs/{lab['id']}/enrolment-token", headers=faculty).status_code == 403

    def test_an_anonymous_caller_cannot_mint_one(self, lab):
        assert client.post(f"{API}/labs/{lab['id']}/enrolment-token").status_code == 401

    def test_minting_again_replaces_the_previous_token(self, admin, lab, machine):
        """So a token written on a whiteboard can be retired."""
        old = _mint(admin, lab)
        _mint(admin, lab)
        response = client.post(
            f"{API}/auth/machine/enrol", json={"enrolmentToken": old, "machineId": machine}
        )
        assert response.status_code == 401


class TestEnrolment:
    def test_a_machine_can_claim_itself_with_a_valid_token(self, admin, lab, machine):
        credential = _enrol(admin, lab, machine)
        assert credential["machineId"] == machine
        assert credential["secret"]
        assert credential["labId"] == lab["id"]

    def test_the_secret_is_never_readable_again(self, admin, lab, machine):
        """It is stored hashed, so the enrolment response is the only copy."""
        _enrol(admin, lab, machine)
        listed = client.get(f"{API}/labs/{lab['id']}/computers", headers=admin).text
        assert "secret" not in listed

    def test_enrolment_needs_no_prior_credential(self, admin, lab, machine):
        """A machine being set up has none — that is what the token is for."""
        token = _mint(admin, lab)
        response = client.post(
            f"{API}/auth/machine/enrol", json={"enrolmentToken": token, "machineId": machine}
        )
        assert response.status_code == 200

    def test_a_wrong_token_is_refused(self, machine):
        response = client.post(
            f"{API}/auth/machine/enrol", json={"enrolmentToken": "nonsense", "machineId": machine}
        )
        assert response.status_code == 401

    def test_a_machine_not_on_the_floor_plan_cannot_enrol(self, admin, lab):
        """A workstation that can invent its own identity is one an attacker
        can add to the room."""
        token = _mint(admin, lab)
        response = client.post(
            f"{API}/auth/machine/enrol",
            json={"enrolmentToken": token, "machineId": "ROGUE-PC-99"},
        )
        assert response.status_code == 404

    def test_one_labs_token_does_not_enrol_another_labs_machine(self, admin):
        """Otherwise a token leaked in one room would open every room."""
        labs = client.get(f"{API}/labs", headers=admin).json()
        if len(labs) < 2:
            pytest.skip("needs two seeded labs")
        first, second = labs[0], labs[1]
        elsewhere = client.get(f"{API}/labs/{second['id']}/computers", headers=admin).json()[0]
        token = _mint(admin, first)
        response = client.post(
            f"{API}/auth/machine/enrol",
            json={"enrolmentToken": token, "machineId": elsewhere["machineId"]},
        )
        assert response.status_code == 401


class TestMachineTokens:
    def test_a_credential_buys_a_token(self, admin, lab, machine):
        credential = _enrol(admin, lab, machine)
        response = client.post(
            f"{API}/auth/machine/token",
            json={"machineId": machine, "secret": credential["secret"]},
        )
        assert response.status_code == 200
        assert response.json()["labId"] == lab["id"]

    def test_a_wrong_secret_is_refused(self, admin, lab, machine):
        _enrol(admin, lab, machine)
        response = client.post(
            f"{API}/auth/machine/token", json={"machineId": machine, "secret": "wrong"}
        )
        assert response.status_code == 401

    def test_an_unenrolled_machine_has_no_token(self, admin, lab):
        computers = client.get(f"{API}/labs/{lab['id']}/computers", headers=admin).json()
        never = computers[-1]["machineId"]
        response = client.post(
            f"{API}/auth/machine/token", json={"machineId": never, "secret": "anything"}
        )
        assert response.status_code == 401


class TestWhatAMachineMayReach:
    """The point of a separate subject type: a machine gets two endpoints."""

    def test_a_machine_can_report_its_own_liveness(self, admin, lab, machine):
        headers = _machine_headers(_enrol(admin, lab, machine))
        response = client.post(
            f"{API}/computers/{machine}/heartbeat", json={"machineId": machine}, headers=headers
        )
        assert response.status_code == 202, response.text

    def test_a_machine_cannot_report_for_another_machine(self, admin, lab, machine):
        headers = _machine_headers(_enrol(admin, lab, machine))
        others = client.get(f"{API}/labs/{lab['id']}/computers", headers=admin).json()
        someone_else = next(c["machineId"] for c in others if c["machineId"] != machine)
        response = client.post(
            f"{API}/computers/{someone_else}/heartbeat",
            json={"machineId": someone_else},
            headers=headers,
        )
        assert response.status_code == 403

    def test_a_machine_cannot_read_the_admin_surface(self, admin, lab, machine):
        headers = _machine_headers(_enrol(admin, lab, machine))
        assert client.get(f"{API}/exams", headers=headers).status_code == 403
        assert client.get(f"{API}/students", headers=headers).status_code == 403

    def test_a_person_cannot_send_a_heartbeat(self, admin, machine):
        """The reverse guard: a human credential is not a workstation."""
        response = client.post(
            f"{API}/computers/{machine}/heartbeat", json={"machineId": machine}, headers=admin
        )
        assert response.status_code == 403

    def test_heartbeats_show_up_as_liveness(self, admin, lab, machine):
        headers = _machine_headers(_enrol(admin, lab, machine))
        client.post(f"{API}/computers/{machine}/heartbeat", json={"machineId": machine}, headers=headers)
        computers = client.get(f"{API}/labs/{lab['id']}/computers", headers=admin).json()
        row = next(c for c in computers if c["machineId"] == machine)
        assert row["connection"] == "online"
        assert row["lastHeartbeatAt"]


class TestInvigilationSignals:
    @pytest.fixture
    def live_session(self, faculty) -> dict | None:
        exams = client.get(f"{API}/exams?status=LIVE", headers=faculty).json()["items"]
        if not exams:
            return None
        rows = client.get(f"{API}/exams/{exams[0]['id']}/sessions", headers=faculty).json()
        return rows[0] if rows else None

    def test_a_focus_loss_is_recorded_and_counted(self, admin, lab, machine, faculty, live_session):
        if live_session is None:
            pytest.skip("no live session in the seed")
        headers = _machine_headers(_enrol(admin, lab, machine))
        before = live_session["warningCount"]

        response = client.post(
            f"{API}/sessions/{live_session['id']}/events",
            json={
                "event": "FOCUS_LOST",
                "occurredAt": "2026-09-09T10:00:00Z",
                "detail": "Switched away from the exam window",
            },
            headers=headers,
        )
        assert response.status_code == 202, response.text

        rows = client.get(f"{API}/sessions/{live_session['id']}/detail", headers=faculty).json()
        assert rows["warningCount"] == before + 1
        assert any(entry["event"] == "FOCUS_LOST" for entry in rows["activity"])

    def test_returning_to_the_window_is_recorded_but_not_counted(
        self, admin, lab, machine, faculty, live_session
    ):
        """Coming back is not an offence, so it must not raise the tally."""
        if live_session is None:
            pytest.skip("no live session in the seed")
        headers = _machine_headers(_enrol(admin, lab, machine))
        before = client.get(f"{API}/sessions/{live_session['id']}/detail", headers=faculty).json()

        client.post(
            f"{API}/sessions/{live_session['id']}/events",
            json={"event": "FOCUS_RESTORED", "occurredAt": "2026-09-09T10:00:05Z"},
            headers=headers,
        )
        after = client.get(f"{API}/sessions/{live_session['id']}/detail", headers=faculty).json()
        assert after["warningCount"] == before["warningCount"]

    def test_a_machine_cannot_invent_an_event_type(self, admin, lab, machine, live_session):
        """The trail is evidence; a workstation must not be able to write
        arbitrary entries into it."""
        if live_session is None:
            pytest.skip("no live session in the seed")
        headers = _machine_headers(_enrol(admin, lab, machine))
        response = client.post(
            f"{API}/sessions/{live_session['id']}/events",
            json={"event": "EXAM_STARTED", "occurredAt": "2026-09-09T10:00:00Z"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_an_unknown_event_is_refused(self, admin, lab, machine, live_session):
        if live_session is None:
            pytest.skip("no live session in the seed")
        headers = _machine_headers(_enrol(admin, lab, machine))
        response = client.post(
            f"{API}/sessions/{live_session['id']}/events",
            json={"event": "NONSENSE", "occurredAt": "2026-09-09T10:00:00Z"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_a_candidate_cannot_report_their_own_focus_loss(self, faculty, live_session):
        """Otherwise the evidence would be written by the person it is about."""
        if live_session is None:
            pytest.skip("no live session in the seed")
        response = client.post(
            f"{API}/sessions/{live_session['id']}/events",
            json={"event": "FOCUS_LOST", "occurredAt": "2026-09-09T10:00:00Z"},
            headers=faculty,
        )
        assert response.status_code == 403
