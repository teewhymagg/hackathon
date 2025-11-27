"""
RAG (Retrieval-Augmented Generation) utility functions for meeting transcripts.

Provides functions to retrieve relevant transcript chunks using semantic search
with pgvector embeddings and metadata filtering.
"""
import hashlib
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, date

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from shared_models.models import TranscriptEmbedding, Meeting


@dataclass
class Chunk:
    """Represents a retrieved transcript chunk with metadata."""
    id: int
    meeting_id: int
    meeting_native_id: Optional[str]
    platform: Optional[str]
    speaker: Optional[str]
    text: str
    start_time: Optional[float]
    end_time: Optional[float]
    timestamp: Optional[datetime]
    chunk_type: str
    language: Optional[str]
    topics: Optional[List[str]]
    similarity_score: float


def compute_chunk_hash(text: str, meeting_id: int, chunk_type: str) -> str:
    """Compute a hash for deduplication of chunks."""
    content = f"{meeting_id}:{chunk_type}:{text}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def fetch_chunks(
    session: Session,
    query_embedding: List[float],
    limit: int = 8,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Chunk]:
    """
    Retrieve relevant transcript chunks using semantic search.
    
    Args:
        session: SQLAlchemy session
        query_embedding: Query vector embedding (1536 dimensions)
        limit: Maximum number of chunks to return
        filters: Optional filters:
            - meeting_id: Filter by specific meeting ID
            - meeting_ids: List of meeting IDs to include
            - platform: Filter by platform (google_meet, microsoft_teams)
            - speaker: Filter by speaker name
            - language: Filter by language code
            - chunk_type: Filter by chunk type (transcript, insight, action_item)
            - date_from: Filter by meeting date (inclusive)
            - date_to: Filter by meeting date (inclusive)
            - exclude_meeting_ids: List of meeting IDs to exclude
    
    Returns:
        List of Chunk objects ordered by similarity (highest first)
    """
    if filters is None:
        filters = {}
    
    # Build base query with cosine similarity
    similarity_expr = (1 - TranscriptEmbedding.embedding.cosine_distance(query_embedding)).label('similarity')
    query = select(
        TranscriptEmbedding,
        similarity_expr
    )
    
    # Apply filters
    conditions = []
    
    if 'meeting_id' in filters:
        conditions.append(TranscriptEmbedding.meeting_id == filters['meeting_id'])
    
    if 'meeting_ids' in filters:
        conditions.append(TranscriptEmbedding.meeting_id.in_(filters['meeting_ids']))
    
    if 'exclude_meeting_ids' in filters:
        conditions.append(~TranscriptEmbedding.meeting_id.in_(filters['exclude_meeting_ids']))
    
    if 'platform' in filters:
        conditions.append(TranscriptEmbedding.platform == filters['platform'])
    
    if 'speaker' in filters:
        conditions.append(TranscriptEmbedding.speaker == filters['speaker'])
    
    if 'language' in filters:
        conditions.append(TranscriptEmbedding.language == filters['language'])
    
    if 'chunk_type' in filters:
        conditions.append(TranscriptEmbedding.chunk_type == filters['chunk_type'])
    
    if 'date_from' in filters:
        date_from = filters['date_from']
        if isinstance(date_from, str):
            date_from = datetime.fromisoformat(date_from).date()
        conditions.append(TranscriptEmbedding.meeting_date >= date_from)
    
    if 'date_to' in filters:
        date_to = filters['date_to']
        if isinstance(date_to, str):
            date_to = datetime.fromisoformat(date_to).date()
        conditions.append(TranscriptEmbedding.meeting_date <= date_to)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Order by similarity (descending) and limit - use text() to reference the label
    query = query.order_by(text('similarity DESC')).limit(limit)
    
    # Execute query
    results = session.execute(query).all()
    
    # Convert to Chunk objects
    chunks = []
    seen_meetings = set()  # For deduplication by meeting
    
    for row in results:
        embedding_row = row[0]
        similarity = float(row[1])
        
        # Deduplication: if we already have chunks from this meeting, skip if we have enough
        if embedding_row.meeting_id in seen_meetings and len(chunks) >= limit:
            continue
        
        chunk = Chunk(
            id=embedding_row.id,
            meeting_id=embedding_row.meeting_id,
            meeting_native_id=embedding_row.meeting_native_id,
            platform=embedding_row.platform,
            speaker=embedding_row.speaker,
            text=embedding_row.text,
            start_time=embedding_row.segment_start,
            end_time=embedding_row.segment_end,
            timestamp=embedding_row.timestamp,
            chunk_type=embedding_row.chunk_type or 'transcript',
            language=embedding_row.language,
            topics=embedding_row.topics,
            similarity_score=similarity,
        )
        chunks.append(chunk)
        seen_meetings.add(embedding_row.meeting_id)
    
    return chunks


def get_meeting_insights_context(
    session: Session,
    meeting_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve structured insights for a meeting to include as context.
    
    Args:
        session: SQLAlchemy session
        meeting_id: Meeting ID
    
    Returns:
        Dictionary with overview, critical_deadlines, action_items, or None
    """
    meeting = session.get(Meeting, meeting_id)
    if not meeting or not meeting.data:
        return None
    
    insights = meeting.data.get('insights_ru')
    if not isinstance(insights, dict):
        return None
    
    return {
        'overview': insights.get('overview', {}),
        'critical_deadlines': insights.get('critical_deadlines', []),
        'action_items': insights.get('action_items', []),
        'blockers': insights.get('blockers', []),
    }

