"""Add meeting insights tables and pgvector support

Revision ID: 3d8c7f37b8c4
Revises: 5befe308fa8b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = '3d8c7f37b8c4'
down_revision = '5befe308fa8b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column('meetings', sa.Column('processed_at', sa.DateTime(), nullable=True))
    op.add_column('meetings', sa.Column('summary_state', sa.String(length=50), server_default='pending', nullable=False))

    op.create_table(
        'meeting_metadata',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('llm_version', sa.String(length=100), nullable=False),
        sa.Column('goal', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('sentiment', sa.String(length=32), nullable=True),
        sa.Column('blockers', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('deadlines', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    op.create_table(
        'speaker_highlights',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('speaker', sa.String(length=255), nullable=True),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('absolute_start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('absolute_end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_speaker_highlights_meeting_id', 'speaker_highlights', ['meeting_id'])

    op.create_table(
        'action_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('priority', sa.String(length=50), nullable=True),
        sa.Column('reference_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_action_items_meeting_id', 'action_items', ['meeting_id'])

    op.create_table(
        'transcript_embeddings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('meeting_id', sa.Integer(), sa.ForeignKey('meetings.id', ondelete='CASCADE'), nullable=False),
        sa.Column('segment_start', sa.Float(), nullable=True),
        sa.Column('segment_end', sa.Float(), nullable=True),
        sa.Column('speaker', sa.String(length=255), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_transcript_embeddings_meeting_id', 'transcript_embeddings', ['meeting_id'])

    op.alter_column('meetings', 'summary_state', server_default=None)


def downgrade() -> None:
    op.drop_index('ix_transcript_embeddings_meeting_id', table_name='transcript_embeddings')
    op.drop_table('transcript_embeddings')

    op.drop_index('ix_action_items_meeting_id', table_name='action_items')
    op.drop_table('action_items')

    op.drop_index('ix_speaker_highlights_meeting_id', table_name='speaker_highlights')
    op.drop_table('speaker_highlights')

    op.drop_table('meeting_metadata')

    op.drop_column('meetings', 'summary_state')
    op.drop_column('meetings', 'processed_at')

