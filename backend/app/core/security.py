"""Password hashing and token issuance.

Argon2id for secrets at rest and short-lived JWTs for request auth. Nothing
here reads the database — that separation keeps the crypto testable on its own
and stops authorization logic leaking into token handling.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings
from app.schemas.enums import Role, SubjectType

# Argon2id at library defaults: memory-hard, and the winner of the password
# hashing competition. Chosen over bcrypt for GPU resistance and because it has
# no silent 72-byte truncation.
_hasher = PasswordHasher()


def hash_secret(secret: str) -> str:
    """Hash a password or a machine credential."""
    return _hasher.hash(secret)


def verify_secret(secret: str, hashed: str) -> bool:
    """Constant-time verification that never raises on a bad input.

    A malformed stored hash is a failed login, not a 500 — an operator error in
    one row must not take the login endpoint down for everyone.
    """
    try:
        return _hasher.verify(hashed, secret)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when a stored hash predates the current Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

ACCESS = "access"
REFRESH = "refresh"


def _encode(claims: dict[str, Any], expires: timedelta) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + expires
    payload = {**claims, "iat": now, "exp": expires_at}
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_at


def issue_user_tokens(user_id: UUID, role: Role) -> tuple[str, str, datetime]:
    """Access and refresh tokens for a human principal.

    The refresh lifetime outlasts a long paper plus overrun, because being
    logged out mid-examination is not an acceptable failure mode.
    """
    settings = get_settings()
    access, expires_at = _encode(
        {"sub": str(user_id), "typ": ACCESS, "sty": SubjectType.USER.value, "role": role.value},
        timedelta(minutes=settings.access_token_minutes),
    )
    refresh, _ = _encode(
        {"sub": str(user_id), "typ": REFRESH, "sty": SubjectType.USER.value},
        timedelta(hours=settings.refresh_token_hours),
    )
    return access, refresh, expires_at


def issue_machine_token(machine_id: str, lab_id: UUID) -> tuple[str, datetime]:
    """A workstation's token.

    Carries ``sty=machine`` and no role. Authorization can therefore refuse a
    machine everywhere except heartbeat and event reporting, without every
    handler having to remember that machines exist.
    """
    settings = get_settings()
    return _encode(
        {"sub": machine_id, "typ": ACCESS, "sty": SubjectType.MACHINE.value, "lab": str(lab_id)},
        timedelta(hours=settings.machine_token_hours),
    )


class TokenError(Exception):
    """Raised for any token that cannot be trusted."""


def decode_token(token: str, *, expected_type: str = ACCESS) -> dict[str, Any]:
    """Verify signature, expiry, and token type.

    Checking ``typ`` matters: without it a refresh token would be accepted as
    an access token, silently granting a much longer-lived credential.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token is invalid") from exc

    if payload.get("typ") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return payload
