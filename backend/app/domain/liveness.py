"""Connection liveness.

Derived from the last heartbeat, never stored. That is what lets a session be
described as "ACTIVE but offline for 40s" — a stored connection column would go
stale the moment a workstation stopped reporting, which is precisely when its
value matters most.
"""

from datetime import datetime

from app.core.config import get_settings
from app.schemas.enums import ConnectionState
from app.utils.clock import utcnow


def connection_state(
    last_heartbeat_at: datetime | None,
    *,
    now: datetime | None = None,
) -> ConnectionState:
    """Classify a workstation from its most recent heartbeat.

    A machine that has never reported is OFFLINE rather than unknown: before an
    exam that is the honest reading, and it keeps the roster's meaning simple.
    """
    if last_heartbeat_at is None:
        return ConnectionState.OFFLINE

    settings = get_settings()
    age = ((now or utcnow()) - last_heartbeat_at).total_seconds()

    # A clock skewed into the future must not read as healthier than one that
    # is merely current, so negative ages clamp to zero.
    age = max(0.0, age)

    if age <= settings.heartbeat_warning_seconds:
        return ConnectionState.ONLINE
    if age <= settings.heartbeat_offline_seconds:
        return ConnectionState.WARNING
    return ConnectionState.OFFLINE
