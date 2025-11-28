import os
import json
from typing import List, Optional, Dict, Any

import streamlit as st
import httpx
from sqlalchemy.orm import sessionmaker

from shared_models.database import sync_engine
from shared_models.models import Meeting, MeetingMetadata
from sqlalchemy import select


SessionLocal = sessionmaker(bind=sync_engine)

RAG_API_URL = os.environ.get("RAG_API_URL", "http://meeting-insights-worker:8002")

st.set_page_config(page_title="Чат", layout="wide")
st.title("💬 AI Scrum Master • Чат")

# Initialize session state for chat
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_mode" not in st.session_state:
    st.session_state.chat_mode = "global"
if "selected_meeting_for_chat" not in st.session_state:
    st.session_state.selected_meeting_for_chat = None


def fetch_meetings():
    """Fetch list of processed meetings."""
    with SessionLocal() as session:
        stmt = (
            select(Meeting, MeetingMetadata)
            .join(MeetingMetadata, MeetingMetadata.meeting_id == Meeting.id, isouter=True)
            .where(Meeting.summary_state.in_(["completed", "no_data"]))
            .order_by(Meeting.start_time.desc().nullslast())
        )
        records = session.execute(stmt).all()
        result = []
        for meeting, metadata in records:
            label = meeting.platform_specific_id or f"Meeting #{meeting.id}"
            if meeting.start_time:
                label = f"{label} ({meeting.start_time.isoformat()})"
            result.append(
                {
                    "id": meeting.id,
                    "label": label,
                    "meeting": meeting,
                    "metadata": metadata,
                }
            )
        return result


def call_rag_api(query: str, mode: str, meeting_id: Optional[int] = None, conversation: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """Call the RAG API endpoint."""
    try:
        with httpx.Client(timeout=60.0) as client:
            payload = {
                "query": query,
                "mode": mode,
                "conversation": conversation or [],
            }
            if meeting_id:
                payload["meeting_id"] = meeting_id
            
            response = client.post(
                f"{RAG_API_URL}/rag/query",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        st.error(f"Failed to call RAG API: {e}")
        return {"answer": "Ошибка при обращении к API.", "chunks": [], "token_usage": None}
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return {"answer": "Произошла неожиданная ошибка.", "chunks": [], "token_usage": None}


# Mode selection
col1, col2 = st.columns([1, 2])
with col1:
    chat_mode = st.radio(
        "Режим",
        ["Knowledge Chat (all meetings)", "Ask the Meeting"],
        key="chat_mode_selector",
    )

# Meeting selector for Ask mode
selected_meeting_id = None
if chat_mode == "Ask the Meeting":
    meetings = fetch_meetings()
    if not meetings:
        st.warning("Нет обработанных встреч. Убедитесь, что worker сгенерировал инсайты.")
        st.stop()
    
    meeting_options = {m["label"]: m["id"] for m in meetings}
    selected_label = st.selectbox(
        "Выберите встречу",
        options=list(meeting_options.keys()),
        key="chat_meeting_selector",
    )
    selected_meeting_id = meeting_options[selected_label]
    st.session_state.selected_meeting_for_chat = selected_meeting_id

# Chat history display
st.divider()

# Display chat history
for msg in st.session_state.chat_history:
    role = msg.get("role", "user")
    content = msg.get("content", "")
    chunks = msg.get("chunks", [])
    
    if role == "user":
        with st.chat_message("user"):
            st.write(content)
    else:
        with st.chat_message("assistant"):
            st.write(content)
            
            # Show citations if available
            if chunks:
                with st.expander(f"📎 Источники ({len(chunks)})"):
                    for i, chunk in enumerate(chunks, 1):
                        meeting_info = chunk.get("meeting_native_id") or f"Meeting #{chunk.get('meeting_id')}"
                        speaker = chunk.get("speaker") or "Неизвестно"
                        timestamp = chunk.get("timestamp") or "н/д"
                        similarity = chunk.get("similarity_score", 0)
                        
                        st.markdown(
                            f"**{i}. {meeting_info}** ({speaker} @ {timestamp}) "
                            f"*[схожесть: {similarity:.3f}]*"
                        )
                        st.caption(chunk.get("text", "")[:200] + "...")

# Chat input
query = st.chat_input("Задайте вопрос о встречах...")

if query:
    # Add user message to history
    st.session_state.chat_history.append({
        "role": "user",
        "content": query,
    })
    
    # Prepare conversation history for API
    conversation = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state.chat_history[-10:]  # Last 10 messages
    ]
    
    # Determine mode
    mode = "meeting" if chat_mode == "Ask the Meeting" else "global"
    
    # Show loading
    with st.spinner("Ищу ответ..."):
        # Call RAG API
        result = call_rag_api(
            query=query,
            mode=mode,
            meeting_id=selected_meeting_id,
            conversation=conversation[:-1],  # Exclude current query
        )
        
        # Add assistant response to history
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": result.get("answer", "Не удалось получить ответ."),
            "chunks": result.get("chunks", []),
        })
    
    # Rerun to display new messages
    st.rerun()

# Clear chat button
if st.session_state.chat_history:
    if st.button("🗑️ Очистить историю чата"):
        st.session_state.chat_history = []
        st.rerun()

