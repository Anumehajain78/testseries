"""Authentication, token, and liveness tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import DEV_JWT_SECRET, Settings
from app.core.security import (
    ACCESS,
    REFRESH,
    TokenError,
    decode_token,
    hash_secret,
    issue_machine_token,
    issue_user_tokens,
    verify_secret,
)
from app.domain.liveness import connection_state
from app.schemas.enums import ConnectionState, Role, SubjectType


class TestPasswordHashing:
    def test_a_correct_secret_verifies(self):
        hashed = hash_secret("correct horse battery staple")
        assert verify_secret("correct horse battery staple", hashed)

    def test_a_wrong_secret_does_not(self):
        assert not verify_secret("wrong", hash_secret("right"))

    def test_the_hash_is_salted(self):
        # Identical passwords must not produce identical hashes, or the store
        # leaks which accounts share one.
        assert hash_secret("same") != hash_secret("same")

    def test_a_malformed_stored_hash_is_a_failed_login_not_a_crash(self):
        # One corrupt row must not take the login endpoint down for everyone.
        assert verify_secret("anything", "not-a-hash") is False

    def test_a_long_password_is_not_silently_truncated(self):
        # bcrypt would ignore everything past 72 bytes; Argon2 must not.
        base = "x" * 100
        assert verify_secret(base, hash_secret(base))
        assert not verify_secret(base + "difference", hash_secret(base))


class TestUserTokens:
    def test_an_access_token_carries_subject_role_and_type(self):
        user_id = uuid.uuid4()
        access, _, _ = issue_user_tokens(user_id, Role.FACULTY)
        payload = decode_token(access)
        assert payload["sub"] == str(user_id)
        assert payload["role"] == Role.FACULTY.value
        assert payload["sty"] == SubjectType.USER.value

    def test_a_refresh_token_is_rejected_where_an_access_token_is_required(self):
        # Without the type check a refresh token would silently grant a much
        # longer-lived credential than intended.
        _, refresh, _ = issue_user_tokens(uuid.uuid4(), Role.STUDENT)
        with pytest.raises(TokenError):
            decode_token(refresh, expected_type=ACCESS)

    def test_a_refresh_token_validates_as_a_refresh_token(self):
        _, refresh, _ = issue_user_tokens(uuid.uuid4(), Role.STUDENT)
        assert decode_token(refresh, expected_type=REFRESH)["sub"]

    def test_a_tampered_token_is_rejected(self):
        access, _, _ = issue_user_tokens(uuid.uuid4(), Role.ADMIN)
        head, payload, signature = access.split(".")
        with pytest.raises(TokenError):
            decode_token(f"{head}.{payload}.{signature[:-2]}xx")

    def test_garbage_is_rejected(self):
        with pytest.raises(TokenError):
            decode_token("not.a.token")

    def test_the_access_token_expiry_is_reported_to_the_client(self):
        _, _, expires_at = issue_user_tokens(uuid.uuid4(), Role.FACULTY)
        assert expires_at > datetime.now(UTC)


class TestMachineTokens:
    def test_a_machine_token_carries_no_role(self):
        # A workstation is not a person; authorization refuses it everywhere
        # except heartbeat and event reporting.
        token, _ = issue_machine_token("LAB1-PC-01", uuid.uuid4())
        payload = decode_token(token)
        assert payload["sty"] == SubjectType.MACHINE.value
        assert "role" not in payload

    def test_a_machine_token_identifies_its_lab(self):
        lab_id = uuid.uuid4()
        token, _ = issue_machine_token("LAB1-PC-01", lab_id)
        assert decode_token(token)["lab"] == str(lab_id)


class TestProductionGuards:
    def test_development_tolerates_the_placeholder_secret(self):
        Settings(environment="development", jwt_secret=DEV_JWT_SECRET).check_production()

    def test_production_refuses_to_start_with_the_placeholder_secret(self):
        settings = Settings(environment="production", jwt_secret=DEV_JWT_SECRET)
        with pytest.raises(RuntimeError, match="development default"):
            settings.check_production()

    def test_production_accepts_a_real_secret(self):
        Settings(environment="production", jwt_secret="a-genuinely-configured-secret").check_production()

    def test_offline_threshold_must_exceed_the_warning_threshold(self):
        with pytest.raises(ValueError):
            Settings(heartbeat_warning_seconds=60, heartbeat_offline_seconds=30)


class TestLiveness:
    NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    def test_a_recent_heartbeat_is_online(self):
        assert connection_state(self.NOW - timedelta(seconds=5), now=self.NOW) is ConnectionState.ONLINE

    def test_a_stale_heartbeat_is_a_warning(self):
        assert connection_state(self.NOW - timedelta(seconds=45), now=self.NOW) is ConnectionState.WARNING

    def test_a_long_silence_is_offline(self):
        assert connection_state(self.NOW - timedelta(minutes=5), now=self.NOW) is ConnectionState.OFFLINE

    def test_a_machine_that_never_reported_is_offline(self):
        assert connection_state(None, now=self.NOW) is ConnectionState.OFFLINE

    def test_a_future_heartbeat_does_not_read_as_healthier_than_the_present(self):
        # A workstation with a skewed clock must not be able to report itself
        # permanently online.
        assert connection_state(self.NOW + timedelta(hours=1), now=self.NOW) is ConnectionState.ONLINE
