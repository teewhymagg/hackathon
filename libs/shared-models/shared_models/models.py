import sqlalchemy
from sqlalchemy import (Column, String, Text, Integer, DateTime, Float, ForeignKey, Index, UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func, text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime # Needed for Transcription model default
from shared_models.schemas import Platform # Import Platform for the static method
from typing import Optional # Added for the return type hint in constructed_meeting_url
from pgvector.sqlalchemy import Vector

# Define the base class for declarative models
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True) # Added index=True
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100))
    image_url = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    max_concurrent_bots = Column(Integer, nullable=False, server_default='1', default=1) # Added field
    data = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=lambda: {})
    
    meetings = relationship("Meeting", back_populates="user")
    api_tokens = relationship("APIToken", back_populates="user")

class APIToken(Base):
    __tablename__ = "api_tokens"
    id = Column(Integer, primary_key=True, index=True) # Added index=True
    token = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    
    user = relationship("User", back_populates="api_tokens")

class Meeting(Base):
    __tablename__ = "meetings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String(100), nullable=False) # e.g., 'google_meet', 'zoom'
    # Database column name is platform_specific_id but we use native_meeting_id in the code
    platform_specific_id = Column(String(255), index=True, nullable=True)
    status = Column(String(50), nullable=False, default='requested', index=True)  # Values: requested, joining, awaiting_admission, active, completed, failed
    bot_container_id = Column(String(255), nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    data = Column(JSONB, nullable=False, default=text("'{}'::jsonb"))
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    processed_at = Column(DateTime, nullable=True)
    summary_state = Column(String(50), nullable=False, server_default='pending')

    user = relationship("User", back_populates="meetings")
    transcriptions = relationship("Transcription", back_populates="meeting")
    sessions = relationship("MeetingSession", back_populates="meeting", cascade="all, delete-orphan")
    metadata_record = relationship("MeetingMetadata", back_populates="meeting", uselist=False, cascade="all, delete-orphan")
    speaker_highlights = relationship("SpeakerHighlight", back_populates="meeting", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")
    transcript_embeddings = relationship("TranscriptEmbedding", back_populates="meeting", cascade="all, delete-orphan")

    # Add composite index for efficient lookup by user, platform, and native ID, including created_at for sorting
    __table_args__ = (
        Index(
            'ix_meeting_user_platform_native_id_created_at',
            'user_id',
            'platform',
            'platform_specific_id',
            'created_at' # Include created_at because the query orders by it
        ),
        Index('ix_meeting_data_gin', 'data', postgresql_using='gin'),
        # Optional: Unique constraint (uncomment if needed, ensure native_meeting_id cannot be NULL if unique)
        # UniqueConstraint('user_id', 'platform', 'platform_specific_id', name='_user_platform_native_id_uc'),
    )

    # Add property getters/setters for compatibility
    @property
    def native_meeting_id(self):
        return self.platform_specific_id
        
    @native_meeting_id.setter
    def native_meeting_id(self, value):
        self.platform_specific_id = value
        
    @property
    def constructed_meeting_url(self) -> Optional[str]: # Added return type hint
        # Calculate the URL on demand using the static method from schemas.py
        if self.platform and self.platform_specific_id:
             return Platform.construct_meeting_url(self.platform, self.platform_specific_id)
        return None

class Transcription(Base):
    __tablename__ = "transcriptions"
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=False, index=True) # Changed nullable to False, should always link
    # Removed redundant platform, meeting_url, token, client_uid, server_id as they belong to the Meeting
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    speaker = Column(String(255), nullable=True) # Speaker identifier
    language = Column(String(10), nullable=True) # e.g., 'en', 'es'
    created_at = Column(DateTime, default=datetime.utcnow)

    meeting = relationship("Meeting", back_populates="transcriptions")
    
    session_uid = Column(String, nullable=True, index=True) # Link to the specific bot session

    # Index for efficient querying by meeting_id and start_time
    __table_args__ = (Index('ix_transcription_meeting_start', 'meeting_id', 'start_time'),)

# New table to store session start times
class MeetingSession(Base):
    __tablename__ = 'meeting_sessions'
    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey('meetings.id'), nullable=False, index=True)
    session_uid = Column(String, nullable=False, index=True) # Stores the 'uid' (based on connectionId)
    # Store timezone-aware timestamp to avoid ambiguity
    session_start_time = Column(sqlalchemy.DateTime(timezone=True), nullable=False, server_default=func.now())

    meeting = relationship("Meeting", back_populates="sessions") # Define relationship

    __table_args__ = (UniqueConstraint('meeting_id', 'session_uid', name='_meeting_session_uc'),) # Ensure unique session per meeting


class MeetingMetadata(Base):
    __tablename__ = "meeting_metadata"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, unique=True)
    llm_version = Column(String(100), nullable=False)
    goal = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String(32), nullable=True)
    blockers = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    deadlines = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    meeting = relationship("Meeting", back_populates="metadata_record")


class SpeakerHighlight(Base):
    __tablename__ = "speaker_highlights"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    speaker = Column(String(255), nullable=True)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    absolute_start_time = Column(sqlalchemy.DateTime(timezone=True), nullable=True)
    absolute_end_time = Column(sqlalchemy.DateTime(timezone=True), nullable=True)
    text = Column(Text, nullable=False)
    label = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    meeting = relationship("Meeting", back_populates="speaker_highlights")


class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    owner = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    due_date = Column(sqlalchemy.DateTime(timezone=True), nullable=True)
    status = Column(String(50), nullable=True)
    priority = Column(String(50), nullable=True)
    reference_url = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    meeting = relationship("Meeting", back_populates="action_items")


class TranscriptEmbedding(Base):
    __tablename__ = "transcript_embeddings"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_start = Column(Float, nullable=True)
    segment_end = Column(Float, nullable=True)
    speaker = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    timestamp = Column(sqlalchemy.DateTime(timezone=True), nullable=True)
    embedding = Column(Vector(1536), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    meeting = relationship("Meeting", back_populates="transcript_embeddings")
