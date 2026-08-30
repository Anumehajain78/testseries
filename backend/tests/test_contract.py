"""Contract tests.

Two jobs. First, prove every route's example payload actually validates against
the response model it claims — a contract that only type-checks on paper is not
a contract. Second, assert the guarantees the design depends on, so a later
refactor cannot quietly undo them.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

EXAM_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "44444444-4444-4444-8444-444444444444"
QUESTION_ID = "66666666-6666-4666-8666-666666666666"
LAB_ID = "22222222-2222-4222-8222-222222222222"
STUDENT_ID = "33333333-3333-4333-8333-333333333333"
API = "/api/v1"


@pytest.fixture(scope="module")
def schema() -> dict:
    return app.openapi()


class TestRoutesAnswer:
    """FastAPI validates outgoing payloads against each response_model, so a
    200 here means the example genuinely satisfies the schema."""

    @pytest.mark.parametrize(
        "path",
        [
            "/health",
            f"{API}/exams",
            f"{API}/exams/{EXAM_ID}",
            f"{API}/exams/{EXAM_ID}/sessions",
            f"{API}/exams/{EXAM_ID}/monitor",
            f"{API}/exams/{EXAM_ID}/results",
            f"{API}/sessions/{SESSION_ID}",
            f"{API}/sessions/{SESSION_ID}/state",
            f"{API}/sessions/{SESSION_ID}/detail",
            f"{API}/me/exams",
            f"{API}/students",
            f"{API}/labs",
            f"{API}/labs/{LAB_ID}/computers",
            f"{API}/audit",
            f"{API}/auth/me",
        ],
    )
    def test_get_returns_a_valid_payload(self, path: str):
        response = client.get(path)
        assert response.status_code == 200, response.text

    def test_start_returns_an_authoritative_window(self):
        response = client.post(f"{API}/exams/{EXAM_ID}/start", json={})
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
