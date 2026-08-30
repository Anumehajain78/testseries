"""Contract tests.

Two jobs. First, prove every route's example payload actually validates against
the response model it claims — a contract that only type-checks on paper is not
a contract. Second, assert the guarantees the design depends on, so a later
refactor cannot quietly undo them.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import issue_user_tokens
from app.main import app
from app.schemas.enums import Role

client = TestClient(app)

SESSION_ID = "44444444-4444-4444-8444-444444444444"
QUESTION_ID = "66666666-6666-4666-8666-666666666666"
API = "/api/v1"


@pytest.fixture(scope="module")
def schema() -> dict:
    return app.openapi()


@pytest.fixture(scope="module")
def staff_headers() -> dict[str, str]:
    """A faculty credential.

    Minted directly rather than via /auth/login: these tests are about route
    shapes and guards, and should not fail because a seed password changed.
    """
    access, _, _ = issue_user_tokens(uuid.uuid4(), Role.FACULTY)
    return {"Authorization": f"Bearer {access}"}


@pytest.fixture(scope="module")
def seeded(staff_headers) -> dict[str, str]:
    """Ids discovered from the running database.

    The read routes are wired to Postgres now, so the tests address real rows
    instead of hardcoded example ids.
    """
    exams = client.get(f"{API}/exams", headers=staff_headers)
    if exams.status_code != 200 or not exams.json()["items"]:
        pytest.skip("no seeded database: run `python -m app.db.seed`")
    labs = client.get(f"{API}/labs", headers=staff_headers).json()
    return {"exam_id": exams.json()["items"][0]["id"], "lab_id": labs[0]["id"]}


class TestRoutesAnswer:
    """FastAPI validates outgoing payloads against each response_model, so a
    200 here means the row genuinely satisfies the schema."""

    def test_health_needs_no_credential(self):
        assert client.get("/health").status_code == 200

    @pytest.mark.parametrize(
        "path",
        [
            "/exams",
            "/students",
            "/labs",
            "/audit",
            "/auth/me",
        ],
    )
    def test_listing_routes_return_valid_payloads(self, path, staff_headers):
        response = client.get(f"{API}{path}", headers=staff_headers)
        assert response.status_code == 200, response.text

    @pytest.mark.parametrize("suffix", ["", "/sessions", "/monitor", "/results"])
    def test_exam_routes_return_valid_payloads(self, suffix, seeded, staff_headers):
        response = client.get(f"{API}/exams/{seeded['exam_id']}{suffix}", headers=staff_headers)
        assert response.status_code == 200, response.text

    def test_lab_computers_return_valid_payloads(self, seeded, staff_headers):
        response = client.get(f"{API}/labs/{seeded['lab_id']}/computers", headers=staff_headers)
        assert response.status_code == 200, response.text

    def test_an_unknown_exam_is_a_404_not_a_crash(self, staff_headers):
        response = client.get(f"{API}/exams/{uuid.uuid4()}", headers=staff_headers)
        assert response.status_code == 404

    def test_reads_require_a_credential(self):
        # The whole admin surface is staff-only; an anonymous caller sees
        # nothing, not an empty list.
        assert client.get(f"{API}/exams").status_code == 401

    def test_a_garbage_token_is_rejected(self):
        response = client.get(f"{API}/exams", headers={"Authorization": "Bearer nonsense"})
        assert response.status_code == 401

    def test_a_candidate_cannot_reach_the_admin_surface(self):
        # Answer keys live behind these routes, so a STUDENT subject must be
        # refused even though it is a perfectly valid credential.
        access, _, _ = issue_user_tokens(uuid.uuid4(), Role.STUDENT)
        response = client.get(f"{API}/exams", headers={"Authorization": f"Bearer {access}"})
        assert response.status_code == 403

    def test_start_returns_an_authoritative_window(self, seeded, staff_headers):
        response = client.post(f"{API}/exams/{seeded['exam_id']}/start", json={}, headers=staff_headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["startsAt"] < body["endsAt"], "the window must move forwards"

    def test_submit_returns_a_receipt(self):
        response = client.post(f"{API}/sessions/{SESSION_ID}/submit", json={})
        assert response.status_code == 200, response.text
        assert response.json()["submissionId"]

    def test_save_answer_accepts_the_discriminated_union(self):
        response = client.put(
            f"{API}/sessions/{SESSION_ID}/answers/{QUESTION_ID}",
            json={"value": {"kind": "single", "option": 1}, "clientSeq": 7},
        )
        assert response.status_code == 200, response.text

    def test_save_answer_rejects_a_malformed_value(self):
        response = client.put(
            f"{API}/sessions/{SESSION_ID}/answers/{QUESTION_ID}",
            json={"value": {"kind": "nonsense"}},
        )
        assert response.status_code == 422

    def test_heartbeat_is_accepted(self):
        response = client.post(
            f"{API}/computers/LAB1-PC-01/heartbeat",
            json={"machineId": "LAB1-PC-01"},
        )
        assert response.status_code == 202, response.text


class TestAnswerKeysCannotReachCandidates:
    """The single most important guarantee in the contract."""

    def test_only_the_faculty_option_model_carries_the_answer_key(self, schema: dict):
        leaky = [
            name
            for name, definition in schema["components"]["schemas"].items()
            if "isCorrect" in (definition.get("properties") or {})
        ]
        assert leaky == ["OptionOut"], (
            f"answer keys must exist on exactly one faculty-facing model, found: {leaky}"
        )

    def test_the_candidate_option_model_has_no_answer_key_field(self, schema: dict):
        props = schema["components"]["schemas"]["StudentOptionOut"]["properties"]
        assert set(props) == {"id", "position", "body"}

    def test_the_candidate_paper_only_references_candidate_models(self, schema: dict):
        paper = schema["components"]["schemas"]["SessionPaper"]
        ref = paper["properties"]["questions"]["items"]["$ref"]
        assert ref.endswith("/StudentQuestionOut")

    def test_a_live_paper_response_contains_no_answer_key(self):
        body = client.get(f"{API}/sessions/{SESSION_ID}").text
        assert "isCorrect" not in body
        assert "is_correct" not in body


class TestSchemaHygiene:
    def test_every_operation_has_a_stable_id(self, schema: dict):
        """Operation ids name the generated client's functions, so an
        auto-derived one would rename functions whenever a path changes."""
        missing = [
            f"{method.upper()} {path}"
            for path, methods in schema["paths"].items()
            for method, operation in methods.items()
            if "operationId" not in operation
        ]
        assert not missing

    def test_operation_ids_are_unique(self, schema: dict):
        ids = [
            operation["operationId"]
            for methods in schema["paths"].values()
            for operation in methods.values()
        ]
        assert len(ids) == len(set(ids))

    def test_no_input_output_schema_splits(self, schema: dict):
        """Pydantic splits a model in two when its input and output shapes
        differ, which produces awkward generated types. Using `alias` rather
        than `serialization_alias` keeps them unified."""
        split = [n for n in schema["components"]["schemas"] if n.endswith(("-Input", "-Output"))]
        assert not split, f"unify these models: {split}"

    def test_realtime_frames_are_published_for_the_client(self, schema: dict):
        """FastAPI does not document websocket routes, so the frames are
        injected deliberately — the frontend needs their generated types."""
        schemas = schema["components"]["schemas"]
        for frame in ("ExamStartedFrame", "SessionStateFrame", "WarningFrame", "HeartbeatFrame"):
            assert frame in schemas

    def test_the_exam_window_is_optional_before_it_is_stamped(self, schema: dict):
        """starts_at/ends_at are null until faculty press start; a required
        field here would force a fake timestamp onto every draft."""
        props = schema["components"]["schemas"]["ExamSummary"]
        assert "startsAt" not in props.get("required", [])
        assert "endsAt" not in props.get("required", [])
