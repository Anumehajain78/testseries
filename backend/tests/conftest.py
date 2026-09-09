"""Test database isolation.

The lifecycle tests create exams, schedule them and start them. Run against the
development database they leave dozens of probe rows behind and quietly corrupt
the world you are trying to look at in the browser — which is exactly what
happened before this file existed.

So the suite gets its own database, created and dropped around the session.
The environment variable is set before any application module is imported,
because the engine is built from settings at import time.
"""

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text

TEST_DB_NAME = "exam_control_test"

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _url_from_env_file() -> str | None:
    """Read the developer's own database URL out of ``.env``.

    pytest does not load ``.env``, and this file sets the variable before the
    application can. A hardcoded fallback here drifts the moment the port
    changes — and it drifts silently, because every database-backed test then
    skips and the run still reports no failures.
    """
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text().splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "EXAM_DATABASE_URL":
            return value.strip().strip('"').strip("'") or None
    return None


def _admin_url(url: str) -> str:
    """The same server and driver, but the maintenance database — you cannot
    drop a database while connected to it."""
    parts = urlparse(url)
    return urlunparse(parts._replace(path="/postgres"))


def _test_url(url: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path=f"/{TEST_DB_NAME}"))


# Whatever the developer's database is, the tests use a sibling of it.
_source = (
    os.environ.get("EXAM_DATABASE_URL")
    or _url_from_env_file()
    or "postgresql+psycopg://exam:exam_local_dev@localhost:5432/exam_control"
)
os.environ["EXAM_DATABASE_URL"] = _test_url(_source)


@pytest.fixture(scope="session")
def database():
    """Create the test database, populate it, and drop it afterwards.

    Deliberately *not* autouse. Skipping at session scope would take the pure
    unit tests down with it whenever Postgres happened to be stopped, and a
    suite that reports "no failures" because it ran nothing is worse than one
    that fails: only the tests that actually need a database should skip.
    """
    admin = create_engine(_admin_url(_source), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    except Exception as exc:  # pragma: no cover - environment problem, not a test failure
        pytest.skip(f"needs Postgres: {exc}")

    # Imported only now, so the engine picks up the overridden URL.
    from app.db.base import Base
    from app.db.session import engine
    import app.db.models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(engine)

    from app.db.seed import seed
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        seed(db)

    yield

    engine.dispose()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    admin.dispose()
