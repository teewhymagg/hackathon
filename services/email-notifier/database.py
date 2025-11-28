from sqlalchemy import create_engine, select, func, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import sys
import os

# Add shared models to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '../..')
shared_models_path = os.path.join(project_root, 'libs/shared-models')
sys.path.insert(0, shared_models_path)

from shared_models.models import (
    User,
    Meeting,
    MeetingMetadata,
    ActionItem,
    Transcription,
    SpeakerHighlight,
)
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

# Database connection
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_upcoming_deadlines(session: Session, days_ahead: int = 7) -> List[Dict]:
    """
    Get all action items with deadlines within the next N days.
    Returns list of dicts with meeting info, action item details, and user email.
    """
    now = datetime.now(timezone.utc)
    future_date = now + timedelta(days=days_ahead)
    
    query = (
        session.query(ActionItem, Meeting, User)
        .join(Meeting, ActionItem.meeting_id == Meeting.id)
        .join(User, Meeting.user_id == User.id)
        .filter(
            and_(
                ActionItem.due_date.isnot(None),
                ActionItem.due_date >= now,
                ActionItem.due_date <= future_date,
                or_(
                    ActionItem.status.is_(None),
                    ActionItem.status != 'completed'
                )
            )
        )
        .order_by(ActionItem.due_date.asc())
    )
    
    results = []
    for action_item, meeting, user in query.all():
        results.append({
            'action_item_id': action_item.id,
            'description': action_item.description,
            'owner': action_item.owner,
            'due_date': action_item.due_date,
            'priority': action_item.priority,
            'status': action_item.status,
            'meeting_id': meeting.id,
            'meeting_platform': meeting.platform,
            'meeting_start_time': meeting.start_time,
            'user_email': user.email,
            'user_name': user.name,
        })
    
    return results


def get_meeting_summary(session: Session, meeting_id: Optional[int] = None, user_id: Optional[int] = None) -> Optional[Dict]:
    """
    Get a completed meeting with summary, insights, blockers, and key highlights.
    If meeting_id is provided, get that specific meeting.
    If user_id is provided, get the most recent meeting for that user.
    Otherwise, get the most recent meeting.
    """
    query = (
        session.query(Meeting, MeetingMetadata, User)
        .join(MeetingMetadata, Meeting.id == MeetingMetadata.meeting_id)
        .join(User, Meeting.user_id == User.id)
        .filter(
            and_(
                Meeting.status == 'completed',
                Meeting.summary_state == 'completed',
                MeetingMetadata.summary.isnot(None),
                MeetingMetadata.summary != ''
            )
        )
    )
    
    # If meeting_id is provided, get that specific meeting
    if meeting_id:
        query = query.filter(Meeting.id == meeting_id)
        result = query.first()
    elif user_id:
        # Get most recent meeting for specific user
        query = query.filter(Meeting.user_id == user_id)
        result = query.order_by(
            func.coalesce(Meeting.processed_at, Meeting.created_at).desc()
        ).first()
    else:
        # Get most recent meeting overall
        result = query.order_by(
            func.coalesce(Meeting.processed_at, Meeting.created_at).desc()
        ).first()
    
    if not result:
        return None
    
    meeting, metadata, user = result
    
    # Get blockers
    blockers = metadata.blockers or []
    
    # Get deadlines from metadata
    deadlines_from_metadata = metadata.deadlines or []
    
    # Get key speaker highlights
    highlights = (
        session.query(SpeakerHighlight)
        .filter(SpeakerHighlight.meeting_id == meeting.id)
        .order_by(SpeakerHighlight.start_time.asc())
        .limit(10)  # Top 10 highlights
        .all()
    )
    
    highlight_list = [
        {
            'speaker': h.speaker,
            'text': h.text,
            'label': h.label,
            'time': h.start_time,
        }
        for h in highlights
    ]
    
    # Get meeting insights from data field
    insights_data = meeting.data.get('insights_ru', {}) if meeting.data else {}
    
    # Get transcript count for context
    transcript_count = (
        session.query(func.count(Transcription.id))
        .filter(Transcription.meeting_id == meeting.id)
        .scalar() or 0
    )
    
    return {
        'meeting_id': meeting.id,
        'platform': meeting.platform,
        'platform_specific_id': meeting.platform_specific_id,
        'start_time': meeting.start_time,
        'end_time': meeting.end_time,
        'summary': metadata.summary,
        'goal': metadata.goal,
        'sentiment': metadata.sentiment,
        'blockers': blockers,
        'deadlines': deadlines_from_metadata,
        'highlights': highlight_list,
        'insights': insights_data,
        'transcript_count': transcript_count,
        'user_email': user.email,
        'user_name': user.name,
    }


def get_all_users_with_meetings(session: Session) -> List[Dict]:
    """
    Get all users who have completed meetings.
    """
    query = (
        session.query(User)
        .join(Meeting, User.id == Meeting.user_id)
        .filter(Meeting.status == 'completed')
        .distinct()
    )
    
    users = []
    for user in query.all():
        users.append({
            'id': user.id,
            'email': user.email,
            'name': user.name,
        })
    
    return users

