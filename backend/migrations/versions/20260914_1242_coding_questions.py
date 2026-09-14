"""coding questions

Adds the coding question type, its test cases, and the per-question limits the
sandbox runs under.

Note the enum: autogenerate does not notice a new member of a Postgres enum
type, so adding 'coding' is written out by hand. Without it every insert of a
coding question fails at runtime against a database that migrated cleanly.

Revision ID: 735486fa83b1
Revises: 7ca3bb37f0b4
Create Date: 2026-09-14 12:42:23.583026

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '735486fa83b1'
down_revision: Union[str, Sequence[str], None] = '7ca3bb37f0b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Outside the transaction on purpose: older PostgreSQL refuses to use a
    # newly added enum value in the same transaction that added it. IF NOT
    # EXISTS so re-running the migration is not an error.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'coding'")

    op.create_table('question_tests',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('stdin', sa.Text(), nullable=False),
    sa.Column('expected_stdout', sa.Text(), nullable=False),
    sa.Column('hidden', sa.Boolean(), nullable=False),
    sa.Column('weight', sa.Integer(), nullable=False),
    sa.CheckConstraint('weight > 0', name=op.f('ck_question_tests_test_weight_positive')),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], name=op.f('fk_question_tests_question_id_questions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_question_tests')),
    sa.UniqueConstraint('question_id', 'position', name='uq_question_tests_position')
    )
    op.add_column('questions', sa.Column('language', sa.String(length=40), nullable=True))
    op.add_column('questions', sa.Column('starter_code', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('time_limit_ms', sa.Integer(), nullable=True))
    op.add_column('questions', sa.Column('memory_limit_mb', sa.Integer(), nullable=True))
    # How a coding answer earned its marks. "6 out of 10" is not reviewable.
    op.add_column('answers', sa.Column('run_report', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema.

    The enum member is left in place. PostgreSQL cannot drop one, and
    recreating the type would mean rewriting every row that references it —
    a far larger risk than an unused label.
    """
    op.drop_column('answers', 'run_report')
    op.drop_column('questions', 'memory_limit_mb')
    op.drop_column('questions', 'time_limit_ms')
    op.drop_column('questions', 'starter_code')
    op.drop_column('questions', 'language')
    op.drop_table('question_tests')
    # ### end Alembic commands ###
