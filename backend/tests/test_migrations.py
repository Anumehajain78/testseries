"""The schema the migrations build, not the one Python imagines.

Every other test runs against a database created with ``create_all`` straight
from the models — so the enums always match the Python ones, because they were
made from them. A real deployment is migrated instead, and the two can drift:
adding a member to a Python ``StrEnum`` does not add it to the Postgres type,
and alembic's autogenerate does not notice.

That drift passes the entire suite and then fails the first time a real server
writes the new value. It has now happened twice — once for ``question_type``
and once for ``audit_event_type``, the second found by hand on a running
server. This is the test that should have found it.
"""

import os
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text

from app.schemas.enums import (
    AuditCategory,
    AuditEventType,
    AuditSeverity,
    ExamStatus,
    LabStatus,
    QuestionType,
    Role,
    SessionStatus,
    StudentStatus,
    SubjectType,
    SubmitMode,
)

#: Python enum against the name of the Postgres type built from it. Kept
#: explicit rather than discovered, so adding a database enum without adding it
#: here is a deliberate omission rather than a silent one.
ENUMS = {
    "question_type": QuestionType,
    "audit_event_type": AuditEventType,
    "audit_category": AuditCategory,
    "audit_severity": AuditSeverity,
    "exam_status": ExamStatus,
    "session_status": SessionStatus,
    "submit_mode": SubmitMode,
    "lab_status": LabStatus,
    "student_status": StudentStatus,
    "role": Role,
    "subject_type": SubjectType,
}

MIGRATED_DB = "exam_control_migration_check"


def _named(url: str, name: str) -> str:
    return urlunparse(urlparse(url)._replace(path=f"/{name}"))


def _admin(url: str) -> str:
    return urlunparse(urlparse(url)._replace(path="/postgres"))


@pytest.fixture(scope="module")
def migrated_url(database) -> str:
    """A database built the way a deployment is: by running the migrations.

    Its own database rather than the test one, because the test database is
    created from the models and proving anything about migrations needs a
    schema that never saw them.
    """
    import subprocess
    import sys
    from pathlib import Path

    source = os.environ["EXAM_DATABASE_URL"]
    admin = create_engine(_admin(source), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATED_DB}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{MIGRATED_DB}"'))
    admin.dispose()

    target = _named(source, MIGRATED_DB)
    # A separate process, because alembic reads the URL from settings at import
    # and this one has already imported them pointing elsewhere.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "EXAM_DATABASE_URL": target},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"migrations did not apply:\n{result.stdout}\n{result.stderr}")

    yield target

    admin = create_engine(_admin(source), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{MIGRATED_DB}" WITH (FORCE)'))
    admin.dispose()


def test_the_migrations_apply_to_an_empty_database(migrated_url):
    """Nothing below means anything if this does not hold."""
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        revision = connection.execute(text("select version_num from alembic_version")).scalar_one()
    engine.dispose()
    assert revision


@pytest.mark.parametrize("type_name", sorted(ENUMS))
def test_every_python_enum_member_exists_in_the_database(migrated_url, type_name):
    """A member added in Python and not in a migration passes every other test
    and then fails the first time a server writes it."""
    engine = create_engine(migrated_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text("select unnest(enum_range(null::" + type_name + "))::text")
        ).scalars().all()
    engine.dispose()

    missing = {member.value for member in ENUMS[type_name]} - set(rows)
    assert not missing, (
        f"{type_name} is missing {sorted(missing)} in a migrated database. "
        f"Add an ALTER TYPE ... ADD VALUE migration; autogenerate will not."
    )
