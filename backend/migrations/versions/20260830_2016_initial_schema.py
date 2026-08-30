"""initial schema

Every table, constraint, index and enum for the examination platform.

Notable constraints are load-bearing rather than decorative:

* ``ck_exams_window_moves_forward`` and ``ck_exams_live_exam_has_window`` make
  "the server owns the exam clock" a database guarantee — a LIVE exam without a
  window, or one ending before it began, cannot be stored.
* ``uq_exam_sessions_exam_id_student_id`` is what makes seating and submission
  idempotent at the storage layer instead of by convention.
* ``uq_exam_sessions_exam_computer`` (partial, on non-null computers) stops two
  candidates being seated at one workstation for the same exam.
* ``ck_results_score_within_max`` refuses the 63/60 the mock once rendered
  as 105%.

Revision ID: 78d79d3dcaa4
Revises:
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '78d79d3dcaa4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Postgres keeps an enum type after the last table using it is dropped, so a
# downgrade that only drops tables leaves the types behind and the next upgrade
# fails with "type already exists". Dropping them explicitly is what makes the
# migration reversible.
ENUM_TYPES = (
    "audit_event_type",
    "audit_category",
    "audit_severity",
    "submit_mode",
    "session_status",
    "exam_status",
    "question_type",
    "lab_status",
    "student_status",
    "subject_type",
    "role",
)


def _drop_enum_types() -> None:
    for name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {name}")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.Enum('ADMIN', 'FACULTY', 'STUDENT', name='role'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('faculty',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('employee_no', sa.String(length=40), nullable=False),
    sa.Column('department', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_faculty_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_faculty')),
    sa.UniqueConstraint('employee_no', name=op.f('uq_faculty_employee_no'))
    )
    op.create_table('students',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('registration_no', sa.String(length=40), nullable=False),
    sa.Column('program', sa.String(length=120), nullable=False),
    sa.Column('semester', sa.Integer(), nullable=False),
    sa.Column('section', sa.String(length=10), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'BLOCKED', name='student_status'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('semester BETWEEN 1 AND 12', name=op.f('ck_students_semester_range')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_students_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_students'))
    )
    op.create_index(op.f('ix_students_registration_no'), 'students', ['registration_no'], unique=True)
    op.create_table('labs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('building', sa.String(length=120), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('READY', 'OCCUPIED', 'MAINTENANCE', name='lab_status'), nullable=False),
    sa.Column('invigilator_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('capacity >= 0', name=op.f('ck_labs_capacity_non_negative')),
    sa.ForeignKeyConstraint(['invigilator_id'], ['faculty.user_id'], name=op.f('fk_labs_invigilator_id_faculty'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_labs')),
    sa.UniqueConstraint('name', name=op.f('uq_labs_name'))
    )
    op.create_table('questions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=True),
    sa.Column('course', sa.String(length=200), nullable=True),
    sa.Column('type', sa.Enum('mcq', 'multiple', 'text', name='question_type'), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('marks', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('marks > 0', name=op.f('ck_questions_marks_positive')),
    sa.ForeignKeyConstraint(['owner_id'], ['faculty.user_id'], name=op.f('fk_questions_owner_id_faculty'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_questions'))
    )
    op.create_index(op.f('ix_questions_course'), 'questions', ['course'], unique=False)
    op.create_table('computers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('lab_id', sa.Uuid(), nullable=False),
    sa.Column('machine_id', sa.String(length=60), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('hostname', sa.String(length=255), nullable=True),
    sa.Column('secret_hash', sa.String(length=255), nullable=True),
    sa.Column('enrolled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['lab_id'], ['labs.id'], name=op.f('fk_computers_lab_id_labs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_computers')),
    sa.UniqueConstraint('lab_id', 'position', name='uq_computers_lab_position')
    )
    op.create_index(op.f('ix_computers_last_heartbeat_at'), 'computers', ['last_heartbeat_at'], unique=False)
    op.create_index(op.f('ix_computers_machine_id'), 'computers', ['machine_id'], unique=True)
    op.create_table('exams',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('course', sa.String(length=200), nullable=False),
    sa.Column('department', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('instructions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.Enum('DRAFT', 'SCHEDULED', 'READY', 'LIVE', 'ENDING', 'COMPLETED', 'CANCELLED', name='exam_status'), nullable=False),
    sa.Column('lab_id', sa.Uuid(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('started_by', sa.Uuid(), nullable=True),
    sa.Column('cancelled_reason', sa.Text(), nullable=True),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('start_idempotency_key', sa.String(length=80), nullable=True),
    sa.Column('event_seq', sa.Integer(), nullable=False),
    sa.Column('results_published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status NOT IN ('LIVE', 'ENDING') OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)", name=op.f('ck_exams_live_exam_has_window')),
    sa.CheckConstraint('duration_minutes >= 5', name=op.f('ck_exams_duration_minimum')),
    sa.CheckConstraint('starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at', name=op.f('ck_exams_window_moves_forward')),
    sa.ForeignKeyConstraint(['created_by'], ['faculty.user_id'], name=op.f('fk_exams_created_by_faculty'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lab_id'], ['labs.id'], name=op.f('fk_exams_lab_id_labs'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['started_by'], ['faculty.user_id'], name=op.f('fk_exams_started_by_faculty'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_exams'))
    )
    op.create_index(op.f('ix_exams_code'), 'exams', ['code'], unique=False)
    op.create_index(op.f('ix_exams_ends_at'), 'exams', ['ends_at'], unique=False)
    op.create_index(op.f('ix_exams_scheduled_at'), 'exams', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_exams_status'), 'exams', ['status'], unique=False)
    op.create_table('question_options',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], name=op.f('fk_question_options_question_id_questions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_question_options')),
    sa.UniqueConstraint('question_id', 'position', name='uq_question_options_question_id_position')
    )
    op.create_table('exam_enrolments',
    sa.Column('exam_id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('enrolled_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name=op.f('fk_exam_enrolments_exam_id_exams'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['students.user_id'], name=op.f('fk_exam_enrolments_student_id_students'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('exam_id', 'student_id', name=op.f('pk_exam_enrolments'))
    )
    op.create_table('exam_questions',
    sa.Column('exam_id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('marks_override', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name=op.f('fk_exam_questions_exam_id_exams'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], name=op.f('fk_exam_questions_question_id_questions'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('exam_id', 'question_id', name=op.f('pk_exam_questions'))
    )
    op.create_table('exam_sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('exam_id', sa.Uuid(), nullable=False),
    sa.Column('student_id', sa.Uuid(), nullable=False),
    sa.Column('computer_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('NOT_STARTED', 'WAITING', 'READY', 'ACTIVE', 'SUBMITTED', 'AUTO_SUBMITTED', 'TERMINATED', name='session_status'), nullable=False),
    sa.Column('question_order', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('option_order', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('checked_in_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submit_mode', sa.Enum('MANUAL', 'AUTO', 'TERMINATED', name='submit_mode'), nullable=True),
    sa.Column('submission_id', sa.Uuid(), nullable=True),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('warning_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status NOT IN ('SUBMITTED', 'AUTO_SUBMITTED') OR (submitted_at IS NOT NULL AND submit_mode IS NOT NULL)", name=op.f('ck_exam_sessions_submitted_session_has_receipt')),
    sa.CheckConstraint('warning_count >= 0', name=op.f('ck_exam_sessions_warning_count_non_negative')),
    sa.ForeignKeyConstraint(['computer_id'], ['computers.id'], name=op.f('fk_exam_sessions_computer_id_computers'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name=op.f('fk_exam_sessions_exam_id_exams'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['students.user_id'], name=op.f('fk_exam_sessions_student_id_students'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_exam_sessions')),
    sa.UniqueConstraint('exam_id', 'student_id', name='uq_exam_sessions_exam_id_student_id')
    )
    op.create_index(op.f('ix_exam_sessions_exam_id'), 'exam_sessions', ['exam_id'], unique=False)
    op.create_index(op.f('ix_exam_sessions_last_heartbeat_at'), 'exam_sessions', ['last_heartbeat_at'], unique=False)
    op.create_index(op.f('ix_exam_sessions_student_id'), 'exam_sessions', ['student_id'], unique=False)
    op.create_index('uq_exam_sessions_exam_computer', 'exam_sessions', ['exam_id', 'computer_id'], unique=True, postgresql_where=sa.text('computer_id IS NOT NULL'))
    op.create_table('answers',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('question_id', sa.Uuid(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('flagged', sa.Boolean(), nullable=False),
    sa.Column('client_seq', sa.Integer(), nullable=False),
    sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], name=op.f('fk_answers_question_id_questions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], name=op.f('fk_answers_session_id_exam_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('session_id', 'question_id', name=op.f('pk_answers'))
    )
    op.create_table('audit_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('event', sa.Enum('LOGIN', 'LOGOUT', 'EXAM_CREATED', 'EXAM_SCHEDULED', 'EXAM_STARTED', 'EXAM_ENDED', 'EXAM_CANCELLED', 'SESSION_CHECKED_IN', 'CONNECTION_LOST', 'CONNECTION_RESTORED', 'FOCUS_LOST', 'FOCUS_RESTORED', 'EXAM_CLIENT_CLOSED', 'ANSWER_SAVED', 'SUBMISSION', 'AUTO_SUBMISSION', 'SESSION_TERMINATED', 'RESULTS_PUBLISHED', name='audit_event_type'), nullable=False),
    sa.Column('category', sa.Enum('AUTH', 'EXAM', 'SESSION', 'CONNECTION', 'SYSTEM', name='audit_category'), nullable=False),
    sa.Column('severity', sa.Enum('INFO', 'WARNING', 'CRITICAL', name='audit_severity'), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_type', sa.Enum('user', 'machine', name='subject_type'), nullable=False),
    sa.Column('actor_label', sa.String(length=200), nullable=False),
    sa.Column('actor_id', sa.String(length=80), nullable=True),
    sa.Column('exam_id', sa.Uuid(), nullable=True),
    sa.Column('session_id', sa.Uuid(), nullable=True),
    sa.Column('student_id', sa.Uuid(), nullable=True),
    sa.Column('machine_id', sa.String(length=60), nullable=True),
    sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], name=op.f('fk_audit_events_exam_id_exams'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], name=op.f('fk_audit_events_session_id_exam_sessions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['student_id'], ['students.user_id'], name=op.f('fk_audit_events_student_id_students'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    op.create_index(op.f('ix_audit_events_event'), 'audit_events', ['event'], unique=False)
    op.create_index(op.f('ix_audit_events_exam_id'), 'audit_events', ['exam_id'], unique=False)
    op.create_index(op.f('ix_audit_events_recorded_at'), 'audit_events', ['recorded_at'], unique=False)
    op.create_index(op.f('ix_audit_events_severity'), 'audit_events', ['severity'], unique=False)
    op.create_table('results',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('score', sa.Numeric(precision=7, scale=2), nullable=False),
    sa.Column('max_score', sa.Numeric(precision=7, scale=2), nullable=False),
    sa.Column('graded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('max_score > 0', name=op.f('ck_results_max_score_positive')),
    sa.CheckConstraint('score <= max_score', name=op.f('ck_results_score_within_max')),
    sa.CheckConstraint('score >= 0', name=op.f('ck_results_score_non_negative')),
    sa.ForeignKeyConstraint(['session_id'], ['exam_sessions.id'], name=op.f('fk_results_session_id_exam_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('session_id', name=op.f('pk_results'))
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('results')
    op.drop_index(op.f('ix_audit_events_severity'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_recorded_at'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_exam_id'), table_name='audit_events')
    op.drop_index(op.f('ix_audit_events_event'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_table('answers')
    op.drop_index('uq_exam_sessions_exam_computer', table_name='exam_sessions', postgresql_where=sa.text('computer_id IS NOT NULL'))
    op.drop_index(op.f('ix_exam_sessions_student_id'), table_name='exam_sessions')
    op.drop_index(op.f('ix_exam_sessions_last_heartbeat_at'), table_name='exam_sessions')
    op.drop_index(op.f('ix_exam_sessions_exam_id'), table_name='exam_sessions')
    op.drop_table('exam_sessions')
    op.drop_table('exam_questions')
    op.drop_table('exam_enrolments')
    op.drop_table('question_options')
    op.drop_index(op.f('ix_exams_status'), table_name='exams')
    op.drop_index(op.f('ix_exams_scheduled_at'), table_name='exams')
    op.drop_index(op.f('ix_exams_ends_at'), table_name='exams')
    op.drop_index(op.f('ix_exams_code'), table_name='exams')
    op.drop_table('exams')
    op.drop_index(op.f('ix_computers_machine_id'), table_name='computers')
    op.drop_index(op.f('ix_computers_last_heartbeat_at'), table_name='computers')
    op.drop_table('computers')
    op.drop_index(op.f('ix_questions_course'), table_name='questions')
    op.drop_table('questions')
    op.drop_table('labs')
    op.drop_index(op.f('ix_students_registration_no'), table_name='students')
    op.drop_table('students')
    op.drop_table('faculty')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    _drop_enum_types()
