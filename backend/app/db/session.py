"""Engine and session lifecycle.

Synchronous SQLAlchemy on purpose. The heavy concurrency in this system is
websocket fan-out and heartbeats, which Redis will absorb; the request path is
short transactional work where async drivers buy complexity rather than
throughput. Revisit only if measurement says otherwise.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    str(settings.database_url),
    echo=settings.database_echo,
    pool_pre_ping=True,  # a lab session must survive an idle connection being reaped
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed.

    Commits are explicit in the service layer, so a handler that raises can
    never leave a half-applied transition behind.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
