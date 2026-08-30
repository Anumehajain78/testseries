"""Request dependencies: authentication and role guards.

Authorization is expressed as dependencies rather than checks inside handlers,
so a route's permissions are visible in its signature and a handler cannot
forget to call the guard.
"""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.schemas.auth import Principal
from app.schemas.enums import Role, SubjectType
from app.utils.clock import utcnow

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    """Whoever is making this request, human or machine."""
    if credentials is None:
        raise _unauthorized("Authentication required")
    try:
        payload = decode_token(credentials.credentials)
    except TokenError as exc:
        raise _unauthorized(str(exc)) from exc

    subject_type = SubjectType(payload.get("sty", SubjectType.USER.value))
    role_claim = payload.get("role")
    return Principal(
        subject_type=subject_type,
        subject_id=payload["sub"],
        role=Role(role_claim) if role_claim else None,
        server_time=utcnow(),
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_roles(*allowed: Role):
    """Guard a route to specific human roles.

    Machines are refused unconditionally here: a workstation is not a person
    and must never reach a management endpoint, whatever role claim it carries.
    """

    def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.subject_type is not SubjectType.USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is not available to lab clients",
            )
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role does not permit this action",
            )
        return principal

    return dependency


def require_machine(principal: CurrentPrincipal) -> Principal:
    """Guard the two endpoints a lab client is allowed to reach."""
    if principal.subject_type is not SubjectType.MACHINE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a lab client credential",
        )
    return principal


# Convenience aliases so route signatures read as permissions.
Staff = Annotated[Principal, Depends(require_roles(Role.ADMIN, Role.FACULTY))]
Admin = Annotated[Principal, Depends(require_roles(Role.ADMIN))]
Candidate = Annotated[Principal, Depends(require_roles(Role.STUDENT))]
Machine = Annotated[Principal, Depends(require_machine)]


def current_student_id(principal: Candidate) -> UUID:
    """The authenticated candidate's own id.

    Every candidate route derives the subject from the token rather than a path
    or body parameter, so one student cannot address another's session by
    editing a request.
    """
    return UUID(principal.subject_id)


CurrentStudentId = Annotated[UUID, Depends(current_student_id)]


def db_session() -> Iterator[Session]:
    yield from get_db()
