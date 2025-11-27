"""Add RAG columns to transcript_embeddings

Revision ID: e8f9a2b4c5d6
Revises: 3d8c7f37b8c4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'e8f9a2b4c5d6'
down_revision = '3d8c7f37b8c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to transcript_embeddings table
    op.add_column('transcript_embeddings', sa.Column('chunk_type', sa.String(50), nullable=True, server_default='transcript'))
    op.add_column('transcript_embeddings', sa.Column('meeting_native_id', sa.String(255), nullable=True))
    op.add_column('transcript_embeddings', sa.Column('platform', sa.String(100), nullable=True))
    op.add_column('transcript_embeddings', sa.Column('language', sa.String(10), nullable=True))
    op.add_column('transcript_embeddings', sa.Column('topics', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('transcript_embeddings', sa.Column('chunk_hash', sa.String(64), nullable=True))
    op.add_column('transcript_embeddings', sa.Column('meeting_date', sa.Date(), nullable=True))
    
    # Create indexes for better query performance
    op.create_index('ix_transcript_embeddings_chunk_type', 'transcript_embeddings', ['chunk_type'])
    op.create_index('ix_transcript_embeddings_meeting_native_id', 'transcript_embeddings', ['meeting_native_id'])
    op.create_index('ix_transcript_embeddings_platform', 'transcript_embeddings', ['platform'])
    op.create_index('ix_transcript_embeddings_language', 'transcript_embeddings', ['language'])
    op.create_index('ix_transcript_embeddings_chunk_hash', 'transcript_embeddings', ['chunk_hash'], unique=False)
    op.create_index('ix_transcript_embeddings_meeting_date', 'transcript_embeddings', ['meeting_date'])
    
    # Note: ivfflat index for vector similarity search should be created separately after data is populated
    # Example: CREATE INDEX ON transcript_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    
    # Backfill meeting_native_id and platform from meetings table
    op.execute("""
        UPDATE transcript_embeddings te
        SET meeting_native_id = m.platform_specific_id,
            platform = m.platform,
            meeting_date = DATE(m.start_time)
        FROM meetings m
        WHERE te.meeting_id = m.id
    """)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_transcript_embeddings_meeting_date', table_name='transcript_embeddings')
    op.drop_index('ix_transcript_embeddings_chunk_hash', table_name='transcript_embeddings')
    op.drop_index('ix_transcript_embeddings_language', table_name='transcript_embeddings')
    op.drop_index('ix_transcript_embeddings_platform', table_name='transcript_embeddings')
    op.drop_index('ix_transcript_embeddings_meeting_native_id', table_name='transcript_embeddings')
    op.drop_index('ix_transcript_embeddings_chunk_type', table_name='transcript_embeddings')
    
    # Drop columns
    op.drop_column('transcript_embeddings', 'meeting_date')
    op.drop_column('transcript_embeddings', 'chunk_hash')
    op.drop_column('transcript_embeddings', 'topics')
    op.drop_column('transcript_embeddings', 'language')
    op.drop_column('transcript_embeddings', 'platform')
    op.drop_column('transcript_embeddings', 'meeting_native_id')
    op.drop_column('transcript_embeddings', 'chunk_type')

