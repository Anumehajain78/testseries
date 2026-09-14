"""test cases corrected audit event

Revision ID: 7feceb0e9462
Revises: 735486fa83b1
Create Date: 2026-09-14 14:29:58.760986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7feceb0e9462'
down_revision: Union[str, Sequence[str], None] = '735486fa83b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add TEST_CASES_CORRECTED to the audit event enum.

    Autogenerate does not notice a new member of a Postgres enum, and the test
    database is built with ``create_all`` straight from the Python enum — so a
    missing value here passes every test and then fails the first time a real,
    migrated database records the event. That is exactly how this one was
    found: on a running server, not in the suite.

    Outside the transaction, because older PostgreSQL refuses to use a newly
    added enum value in the transaction that added it.
    """
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'TEST_CASES_CORRECTED'")


def downgrade() -> None:
    """Left in place. PostgreSQL cannot drop an enum member, and recreating the
    type would mean rewriting every audit row that references it — a far larger
    risk than an unused label."""
