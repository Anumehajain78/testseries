"""Time.

Every timestamp in the system comes from here, so "the server owns the clock"
has a single implementation rather than scattered ``datetime.now()`` calls with
inconsistent awareness. Always UTC and always tz-aware — a naive datetime
reaching Postgres is how off-by-five-and-a-half-hours bugs start.
"""

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def exam_window(duration_minutes: int, *, start: datetime | None = None) -> tuple[datetime, datetime]:
    """The authoritative window, stamped once when faculty press start."""
    starts_at = start or utcnow()
    return starts_at, starts_at + timedelta(minutes=duration_minutes)
