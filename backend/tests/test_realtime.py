"""Realtime channel tests.

The socket is an accelerator, so what matters is that it is guarded like the
REST API, that a transition actually produces a frame, and that a client can
tell it missed something. Correctness under a dropped connection is covered by
the fact that every frame only ever says "refetch".
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import issue_user_tokens
from app.main import app
from app.schemas.enums import Role

API = "/api/v1"


def _token(email: str, client: TestClient) -> str | None:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "examcontrol"})
    return response.json()["accessToken"] if response.status_code == 200 else None


@pytest.fixture(scope="module")
def client(database):
    # The lifespan starts the broker, so the socket has something to subscribe
    # to; a bare TestClient would not.
    with TestClient(app) as running:
        yield running


@pytest.fixture(scope="module")
def staff_token(client) -> str:
    token = _token("anita.rao@northbridge.edu", client)
    if token is None:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    return token


@pytest.fixture(scope="module")
def ready_exam(client, staff_token) -> str:
    """An exam that can still be started, created for this test."""
    headers = {"Authorization": f"Bearer {staff_token}"}
    labs = client.get(f"{API}/labs", headers=headers).json()
    students = client.get(f"{API}/students?limit=5", headers=headers).json()["items"]
    created = client.post(
        f"{API}/exams",
        headers=headers,
        json={
            "title": f"Realtime Probe {uuid.uuid4().hex[:6]}",
            "code": f"RT-{uuid.uuid4().hex[:4].upper()}",
            "course": "Realtime", "department": "Computer Science",
            "durationMinutes": 30, "scheduledAt": "2026-09-08T10:00:00Z",
            "labId": labs[0]["id"], "studentIds": [s["id"] for s in students[:2]],
            "questions": [{
                "type": "mcq", "prompt": "Live?", "marks": 1,
                "options": [{"body": "Yes", "isCorrect": True}, {"body": "No", "isCorrect": False}],
            }],
        },
    )
    exam_id = created.json()["id"]
    client.post(f"{API}/exams/{exam_id}/schedule", json={}, headers=headers)
    return exam_id


class TestSocketIsGuarded:
    def test_a_socket_without_a_token_is_refused(self, client, ready_exam):
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/exams/{ready_exam}/monitor"):
                pass

    def test_a_garbage_token_is_refused(self, client, ready_exam):
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/exams/{ready_exam}/monitor?token=nonsense"):
                pass

    def test_a_candidate_cannot_watch_the_monitor(self, client, ready_exam):
        """The monitor shows the whole room; it is an invigilator's view."""
        token = _token("aarav.mehta@northbridge.edu", client)
        if token is None:
            pytest.skip("candidate cannot sign in")
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/exams/{ready_exam}/monitor?token={token}"):
                pass

    def test_a_token_naming_a_deleted_account_is_refused(self, client, ready_exam):
        access, _, _ = issue_user_tokens(uuid.uuid4(), Role.FACULTY)
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/exams/{ready_exam}/monitor?token={access}"):
                pass


class TestFrames:
    def test_the_first_frame_carries_the_current_sequence(self, client, staff_token, ready_exam):
        """So a client reconnecting can tell at once whether it missed
        anything while it was away."""
        with client.websocket_connect(
            f"/ws/exams/{ready_exam}/monitor?token={staff_token}"
        ) as socket:
            hello = socket.receive_json()
        assert hello["event"] == "HELLO"
        assert hello["examId"] == ready_exam
        assert isinstance(hello["seq"], int)
        assert hello["serverTime"]

    def test_starting_an_exam_pushes_a_frame(self, client, staff_token, ready_exam):
        headers = {"Authorization": f"Bearer {staff_token}"}
        with client.websocket_connect(
            f"/ws/exams/{ready_exam}/monitor?token={staff_token}"
        ) as socket:
            hello = socket.receive_json()
            client.post(f"{API}/exams/{ready_exam}/start", json={}, headers=headers)

            frame = socket.receive_json()
            assert frame["event"] == "EXAM_STARTED"
            # The sequence advances, which is what lets a client detect a gap.
            assert frame["seq"] > hello["seq"]
            assert frame["startsAt"] < frame["endsAt"]
            assert frame["releasedSessionCount"] >= 1

    def test_a_frame_never_carries_an_answer_key(self, client, staff_token, ready_exam):
        """Frames are notifications, not payloads — nothing sensitive rides
        on a channel a socket could be left open on."""
        headers = {"Authorization": f"Bearer {staff_token}"}
        with client.websocket_connect(
            f"/ws/exams/{ready_exam}/monitor?token={staff_token}"
        ) as socket:
            socket.receive_json()
            client.post(f"{API}/exams/{ready_exam}/end", json={}, headers=headers)
            frame = socket.receive_json()
        assert "isCorrect" not in str(frame)
        assert frame["event"] == "EXAM_ENDED"


class TestBrokerDegradation:
    @pytest.mark.anyio
    async def test_publishing_without_redis_still_reaches_local_sockets(self):
        """A single worker needs no cross-process hop, and a Redis outage must
        cost live updates rather than the API."""
        from app.realtime.broker import Broker

        local = Broker(redis_url=None)
        await local.connect()
        received = []

        subscription = local.subscribe("exam-control:exam:test")

        async def collect():
            async for frame in subscription:
                received.append(frame)
                break

        import asyncio

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)
        await local.publish("exam-control:exam:test", {"event": "PING"})
        await asyncio.wait_for(task, timeout=2)
        await local.close()

        assert received == [{"event": "PING"}]
