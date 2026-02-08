"""Initial migration

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Traces table
    op.create_table(
        'traces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('goal', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('step_count', sa.Integer(), default=0),
        sa.Column('tags', sa.JSON(), default=list),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id')
    )
    op.create_index('ix_traces_session_id', 'traces', ['session_id'])

    # Runs table
    op.create_table(
        'runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(255), nullable=False),
        sa.Column('mode', sa.Enum('REPLAY', 'AGENT', name='runmode'), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='runstatus'), nullable=True),
        sa.Column('trace_set', sa.String(255), nullable=True),
        sa.Column('seed', sa.Integer(), nullable=True),
        sa.Column('agent_url', sa.String(512), nullable=True),
        sa.Column('total_sessions', sa.Integer(), default=0),
        sa.Column('completed_sessions', sa.Integer(), default=0),
        sa.Column('success_rate', sa.Float(), nullable=True),
        sa.Column('median_time_to_complete', sa.Float(), nullable=True),
        sa.Column('error_recovery_rate', sa.Float(), nullable=True),
        sa.Column('harmful_action_blocks', sa.Integer(), default=0),
        sa.Column('tool_call_count', sa.Integer(), default=0),
        sa.Column('abandonment_rate', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('config', sa.JSON(), default=dict),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id')
    )
    op.create_index('ix_runs_run_id', 'runs', ['run_id'])

    # Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('trace_session_id', sa.String(255), nullable=True),
        sa.Column('goal', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='runstatus'), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('abandoned', sa.Boolean(), default=False),
        sa.Column('duration_ms', sa.Float(), nullable=True),
        sa.Column('step_count', sa.Integer(), default=0),
        sa.Column('error_count', sa.Integer(), default=0),
        sa.Column('blocked_action_count', sa.Integer(), default=0),
        sa.Column('recovery_count', sa.Integer(), default=0),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('was_mutated', sa.Boolean(), default=False),
        sa.Column('mutation_summary', sa.JSON(), default=dict),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sessions_session_id', 'sessions', ['session_id'])

    # Events table
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_record_id', sa.Integer(), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(2048), nullable=True),
        sa.Column('page_title', sa.String(512), nullable=True),
        sa.Column('dom_summary', sa.Text(), nullable=True),
        sa.Column('visible_elements', sa.JSON(), default=list),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('action_selector', sa.String(512), nullable=True),
        sa.Column('action_text', sa.Text(), nullable=True),
        sa.Column('action_url', sa.String(2048), nullable=True),
        sa.Column('action_reasoning', sa.Text(), nullable=True),
        sa.Column('result', sa.Enum('SUCCESS', 'FAILURE', 'BLOCKED', 'SKIPPED', 'TIMEOUT', name='eventresult'), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Float(), default=0.0),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_record_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Artifacts table
    op.create_table(
        'artifacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_record_id', sa.Integer(), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=True),
        sa.Column('artifact_type', sa.String(50), nullable=False),
        sa.Column('file_path', sa.String(1024), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_record_id'], ['sessions.id']),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('artifacts')
    op.drop_table('events')
    op.drop_table('sessions')
    op.drop_table('runs')
    op.drop_table('traces')
