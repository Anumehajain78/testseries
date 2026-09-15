"""Getting back into an account.

A password that can never be changed is a candidate locked out on exam
morning, and a password that changes without ending the sessions it opened is
no change at all. These pin both halves.

Three ways back in, each for a different person:

* somebody who knows their password changes it themselves;
* a candidate who has lost theirs is reset by the exam cell;
* the exam cell, who has nobody above them, is reset from the server itself.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import RefreshToken
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)
API = "/api/v1"
SEEDED = "examcontrol"


def sign_in(email: str, password: str = SEEDED):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def bearer(email: str, password: str = SEEDED) -> dict[str, str]:
    response = sign_in(email, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


@pytest.fixture
def admin(database) -> dict[str, str]:
    response = sign_in("admin@northbridge.edu")
    if response.status_code != 200:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


@pytest.fixture
def candidate(admin) -> dict:
    """A candidate of this test's own, so changing their password disturbs
    nobody else's fixtures."""
    suffix = uuid.uuid4().hex[:6]
    created = client.post(f"{API}/students", headers=admin, json={
        "registrationNo": f"24PWD{suffix}",
        "fullName": f"Password Probe {suffix}",
        "email": f"pwd.{suffix}@northbridge.edu",
        "program": "B.Tech CSE",
        "semester": 3,
        "section": "A",
    }).json()
    return {
        "id": created["student"]["id"],
        "email": created["student"]["email"],
        "password": created["temporaryPassword"],
    }


def live_sessions(user_id: str) -> int:
    with SessionLocal() as db:
        return len([
            row for row in db.query(RefreshToken)
            .filter(RefreshToken.user_id == uuid.UUID(user_id), RefreshToken.consumed_at.is_(None))
            .all()
        ])


class TestChangingYourOwn:
    def test_the_new_password_works_and_the_old_one_stops(self, candidate):
        headers = bearer(candidate["email"], candidate["password"])
        response = client.post(f"{API}/auth/password", headers=headers, json={
            "currentPassword": candidate["password"],
            "newPassword": "a-new-one-entirely",
        })
        assert response.status_code == 200, response.text

        assert sign_in(candidate["email"], "a-new-one-entirely").status_code == 200
        assert sign_in(candidate["email"], candidate["password"]).status_code == 401

    def test_the_current_password_is_required_even_though_you_are_signed_in(self, candidate):
        """Being signed in is not proof that the person at the keyboard is the
        account holder. On a shared lab machine it is frequently proof of the
        opposite, because the last candidate walked away without signing out."""
        headers = bearer(candidate["email"], candidate["password"])
        response = client.post(f"{API}/auth/password", headers=headers, json={
            "currentPassword": "not-their-password",
            "newPassword": "a-new-one-entirely",
        })
        assert response.status_code == 401
        assert sign_in(candidate["email"], candidate["password"]).status_code == 200

    def test_every_session_is_ended_not_just_this_one(self, candidate):
        """The point of the change. Somebody who has the old password keeps
        their seat until the token happens to expire, otherwise."""
        first = bearer(candidate["email"], candidate["password"])
        bearer(candidate["email"], candidate["password"])  # a second device
        assert live_sessions(candidate["id"]) == 2

        client.post(f"{API}/auth/password", headers=first, json={
            "currentPassword": candidate["password"],
            "newPassword": "a-new-one-entirely",
        })
        assert live_sessions(candidate["id"]) == 0

    def test_a_refresh_token_from_before_the_change_is_dead(self, candidate):
        signed_in = sign_in(candidate["email"], candidate["password"]).json()
        client.post(
            f"{API}/auth/password",
            headers={"Authorization": f"Bearer {signed_in['accessToken']}"},
            json={"currentPassword": candidate["password"], "newPassword": "a-new-one-entirely"},
        )
        replay = client.post(f"{API}/auth/refresh", json={"refreshToken": signed_in["refreshToken"]})
        assert replay.status_code == 401

    def test_reusing_the_same_password_is_refused(self, candidate):
        headers = bearer(candidate["email"], candidate["password"])
        response = client.post(f"{API}/auth/password", headers=headers, json={
            "currentPassword": candidate["password"],
            "newPassword": candidate["password"],
        })
        assert response.status_code == 422

    def test_a_short_password_is_refused(self, candidate):
        headers = bearer(candidate["email"], candidate["password"])
        response = client.post(f"{API}/auth/password", headers=headers, json={
            "currentPassword": candidate["password"],
            "newPassword": "short",
        })
        assert response.status_code == 422

    def test_signing_out_still_ends_only_one_session(self, candidate):
        """The contrast that makes the above meaningful: an ordinary sign-out
        must not sign a candidate out of their own laptop."""
        first = sign_in(candidate["email"], candidate["password"]).json()
        sign_in(candidate["email"], candidate["password"])
        client.post(f"{API}/auth/logout", json={"refreshToken": first["refreshToken"]})
        assert live_sessions(candidate["id"]) == 1


class TestTheExamCellResettingACandidate:
    def test_a_new_password_is_issued_and_works(self, admin, candidate):
        response = client.post(f"{API}/students/{candidate['id']}/password", headers=admin)
        assert response.status_code == 200, response.text

        issued = response.json()["temporaryPassword"]
        assert issued and issued != candidate["password"]
        assert sign_in(candidate["email"], issued).status_code == 200
        assert sign_in(candidate["email"], candidate["password"]).status_code == 401

    def test_the_candidates_sessions_are_ended(self, admin, candidate):
        """If the reset is happening because somebody else knew the password,
        leaving their session open makes the reset pointless."""
        bearer(candidate["email"], candidate["password"])
        assert live_sessions(candidate["id"]) == 1

        client.post(f"{API}/students/{candidate['id']}/password", headers=admin)
        assert live_sessions(candidate["id"]) == 0

    def test_it_is_shown_once_and_not_stored_in_the_clear(self, admin, candidate):
        """The same contract as adding a candidate: readable at this moment
        and never again."""
        issued = client.post(
            f"{API}/students/{candidate['id']}/password", headers=admin
        ).json()["temporaryPassword"]

        listed = client.get(f"{API}/students?search={candidate['email']}", headers=admin).text
        assert issued not in listed

    def test_faculty_cannot_reset_a_candidates_password(self, database, candidate):
        """Handing out credentials is the exam cell's, like the rest of the
        register."""
        faculty = bearer("anita.rao@northbridge.edu")
        response = client.post(f"{API}/students/{candidate['id']}/password", headers=faculty)
        assert response.status_code == 403

    def test_a_candidate_cannot_reset_anybodys(self, candidate):
        headers = bearer(candidate["email"], candidate["password"])
        response = client.post(f"{API}/students/{candidate['id']}/password", headers=headers)
        assert response.status_code == 403

    def test_an_unknown_candidate_is_a_404(self, admin):
        response = client.post(f"{API}/students/{uuid.uuid4()}/password", headers=admin)
        assert response.status_code == 404


class TestMachinesHaveSecretsNotPasswords:
    def test_a_workstation_is_told_to_enrol_again(self, admin):
        """A machine credential is rotated by re-enrolling, which is a
        different act with a different authority behind it.

        Enrolled through the API rather than minted locally, because the guard
        reads the machine back from the database — a token naming a workstation
        that does not exist is refused earlier, and would prove nothing about
        this rule.
        """
        labs = client.get(f"{API}/labs", headers=admin).json()
        minted = client.post(
            f"{API}/labs/{labs[0]['id']}/enrolment-token", headers=admin, json={}
        ).json()
        machines = client.get(f"{API}/labs/{labs[0]['id']}/computers", headers=admin).json()

        credential = client.post(f"{API}/auth/machine/enrol", json={
            "enrolmentToken": minted["token"],
            "machineId": machines[0]["machineId"],
        }).json()
        issued = client.post(f"{API}/auth/machine/token", json={
            "machineId": credential["machineId"],
            "secret": credential["secret"],
        }).json()

        response = client.post(
            f"{API}/auth/password",
            headers={"Authorization": f"Bearer {issued['accessToken']}"},
            json={"currentPassword": "whatever", "newPassword": "a-new-one-entirely"},
        )
        assert response.status_code == 403
