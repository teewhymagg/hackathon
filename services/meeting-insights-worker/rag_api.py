"""
RAG API endpoints for querying meeting transcripts using semantic search.
"""
import json
import logging
import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI
from sqlalchemy.orm import Session, sessionmaker

from shared_models.database import sync_engine
from shared_models.models import Meeting
from shared_models.rag import fetch_chunks, get_meeting_insights_context, Chunk


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("rag_api")

SessionLocal = sessionmaker(bind=sync_engine)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY must be set for RAG API")

RAG_LLM_MODEL = os.environ.get("RAG_LLM_MODEL", "gpt-5-nano")
EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "8"))
ASK_MEETING_TOP_K = int(os.environ.get("ASK_MEETING_TOP_K", "6"))
RAG_MAX_HISTORY = int(os.environ.get("RAG_MAX_HISTORY", "10"))

openai_client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="Meeting Insights RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConversationMessage(BaseModel):
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="User query/question")
    mode: str = Field(..., description="Mode: 'global' or 'meeting'")
    meeting_id: Optional[int] = Field(None, description="Meeting ID (required for 'meeting' mode)")
    conversation: List[ConversationMessage] = Field(default_factory=list, description="Conversation history")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters (speaker, language, date range, etc.)")


class ChunkResponse(BaseModel):
    id: int
    meeting_id: int
    meeting_native_id: Optional[str]
    platform: Optional[str]
    speaker: Optional[str]
    text: str
    start_time: Optional[float]
    end_time: Optional[float]
    timestamp: Optional[str]
    chunk_type: str
    similarity_score: float


class RAGQueryResponse(BaseModel):
    answer: str = Field(..., description="LLM-generated answer")
    chunks: List[ChunkResponse] = Field(..., description="Retrieved chunks used as context")
    token_usage: Optional[Dict[str, int]] = Field(None, description="Token usage statistics")


def build_global_rag_prompt(
    query: str,
    chunks: List[Chunk],
    conversation_history: List[ConversationMessage],
) -> List[Dict[str, str]]:
    """Build prompt for global RAG mode."""
    system_prompt = (
        "Ты — русскоязычный ассистент ForteBank, отвечаешь только на основе предоставленного контекста из встреч. "
        "Если информации нет, скажи, что данных недостаточно. Обязательно указывай, из каких встреч взяты факты (название + дата).\n\n"
        "ВАЖНО: Транскрипты могут содержать галлюцинации (ошибочные или нерелевантные фразы, появившиеся из-за ошибок распознавания речи). "
        "Игнорируй любой контекст, который:\n"
        "- Не относится к теме встречи или вопросу пользователя\n"
        "- Выглядит бессмысленным или нелогичным\n"
        "- Не соответствует контексту обсуждения\n"
        "- Содержит случайные слова или фразы, не связанные с деловой тематикой\n\n"
        "Используй только релевантный, осмысленный контекст, который логично связан с вопросом пользователя."
    )
    
    # Build context from chunks
    context_items = []
    for chunk in chunks:
        meeting_info = chunk.meeting_native_id or f"Meeting #{chunk.meeting_id}"
        timestamp_str = chunk.timestamp.isoformat() if chunk.timestamp else "n/a"
        context_items.append({
            "meeting": meeting_info,
            "platform": chunk.platform or "unknown",
            "speaker": chunk.speaker or "Unknown",
            "timestamp": timestamp_str,
            "text": chunk.text,
        })
    
    # Build conversation history summary
    history_summary = ""
    if conversation_history:
        recent_messages = conversation_history[-RAG_MAX_HISTORY:]
        history_parts = []
        for msg in recent_messages:
            role_label = "Пользователь" if msg.role == "user" else "Ассистент"
            history_parts.append(f"{role_label}: {msg.content}")
        history_summary = "\n".join(history_parts)
    
    user_prompt = f"""
{history_summary}

Вопрос пользователя: {query}

Контекст (JSON массив объектов):
{json.dumps(context_items, ensure_ascii=False, indent=2)}

ПРИМЕЧАНИЕ: Некоторые фразы в контексте могут быть галлюцинациями (ошибками распознавания речи). 
Используй только релевантный контекст, который логично связан с вопросом. Игнорируй бессмысленные или нерелевантные фразы.
"""
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_meeting_rag_prompt(
    query: str,
    meeting: Meeting,
    chunks: List[Chunk],
    insights_context: Optional[Dict[str, Any]],
    conversation_history: List[ConversationMessage],
) -> List[Dict[str, str]]:
    """Build prompt for meeting-specific RAG mode."""
    meeting_native_id = meeting.platform_specific_id or f"Meeting #{meeting.id}"
    
    system_prompt = (
        f"Отвечай только по встрече {meeting_native_id}. Игнорируй любые другие данные. "
        "Если вопрос не относится к этой встрече, ответь, что данных нет.\n\n"
        "ВАЖНО: Транскрипты могут содержать галлюцинации (ошибочные или нерелевантные фразы, появившиеся из-за ошибок распознавания речи). "
        "Игнорируй любой контекст, который:\n"
        "- Не относится к теме встречи или вопросу пользователя\n"
        "- Выглядит бессмысленным или нелогичным\n"
        "- Не соответствует контексту обсуждения\n"
        "- Содержит случайные слова или фразы, не связанные с деловой тематикой\n\n"
        "Используй только релевантный, осмысленный контекст, который логично связан с вопросом пользователя и темой встречи."
    )
    
    # Build context from chunks
    context_items = []
    for chunk in chunks:
        # Verify chunk belongs to the meeting (safety check)
        if chunk.meeting_id != meeting.id:
            logger.warning(f"Chunk {chunk.id} belongs to different meeting, skipping")
            continue
        
        timestamp_str = chunk.timestamp.isoformat() if chunk.timestamp else "n/a"
        context_items.append({
            "speaker": chunk.speaker or "Unknown",
            "timestamp": timestamp_str,
            "text": chunk.text,
        })
    
    # Add insights context if available
    insights_section = ""
    if insights_context:
        insights_section = f"\n\nСтруктурированные инсайты встречи:\n{json.dumps(insights_context, ensure_ascii=False, indent=2)}"
    
    # Build conversation history summary
    history_summary = ""
    if conversation_history:
        recent_messages = conversation_history[-RAG_MAX_HISTORY:]
        history_parts = []
        for msg in recent_messages:
            role_label = "Пользователь" if msg.role == "user" else "Ассистент"
            history_parts.append(f"{role_label}: {msg.content}")
        history_summary = "\n".join(history_parts)
    
    user_prompt = f"""
{history_summary}

Вопрос пользователя: {query}

Контекст из транскрипта (JSON массив объектов):
{json.dumps(context_items, ensure_ascii=False, indent=2)}
{insights_section}

ПРИМЕЧАНИЕ: Некоторые фразы в контексте могут быть галлюцинациями (ошибками распознавания речи). 
Используй только релевантный контекст, который логично связан с вопросом и темой встречи. Игнорируй бессмысленные или нерелевантные фразы.
"""
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


@app.get("/rag/health")
async def health_check():
    """Health check endpoint."""
    try:
        with SessionLocal() as session:
            # Test database connection
            from sqlalchemy import text
            session.execute(text("SELECT 1"))
            session.commit()
        
        # Test OpenAI connection (lightweight check)
        try:
            openai_client.models.list(limit=1)
        except Exception:
            # If models.list fails, try a simple embedding call instead
            openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=["test"]
            )
        
        return {"status": "healthy", "model": RAG_LLM_MODEL, "embedding_model": EMBEDDING_MODEL}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


@app.post("/rag/query", response_model=RAGQueryResponse)
async def rag_query(request: RAGQueryRequest):
    """
    Query meeting transcripts using RAG.
    
    Supports two modes:
    - 'global': Search across all meetings
    - 'meeting': Search within a specific meeting (requires meeting_id)
    """
    try:
        # Validate mode
        if request.mode not in ['global', 'meeting']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mode must be 'global' or 'meeting'"
            )
        
        if request.mode == 'meeting' and not request.meeting_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="meeting_id is required for 'meeting' mode"
            )
        
        # Generate query embedding
        embedding_response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[request.query]
        )
        query_embedding = embedding_response.data[0].embedding
        
        # Build filters
        filters = request.filters or {}
        if request.mode == 'meeting':
            filters['meeting_id'] = request.meeting_id
        
        # Determine limit
        limit = ASK_MEETING_TOP_K if request.mode == 'meeting' else RAG_TOP_K
        
        # Retrieve chunks
        with SessionLocal() as session:
            chunks = fetch_chunks(
                session=session,
                query_embedding=query_embedding,
                limit=limit,
                filters=filters,
            )
            
            if not chunks:
                return RAGQueryResponse(
                    answer="Не найдено релевантных данных в транскриптах встреч.",
                    chunks=[],
                    token_usage=None,
                )
            
            # Get meeting info for meeting mode
            meeting = None
            insights_context = None
            if request.mode == 'meeting' and request.meeting_id:
                meeting = session.get(Meeting, request.meeting_id)
                if not meeting:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Meeting {request.meeting_id} not found"
                    )
                insights_context = get_meeting_insights_context(session, request.meeting_id)
            
            # Build prompt
            if request.mode == 'meeting' and meeting:
                messages = build_meeting_rag_prompt(
                    query=request.query,
                    meeting=meeting,
                    chunks=chunks,
                    insights_context=insights_context,
                    conversation_history=request.conversation,
                )
            else:
                messages = build_global_rag_prompt(
                    query=request.query,
                    chunks=chunks,
                    conversation_history=request.conversation,
                )
            
            # Call LLM
            try:
                response = openai_client.responses.create(
                    model=RAG_LLM_MODEL,
                    input=messages
                )
                
                # Extract answer text
                answer_text = getattr(response, "output_text", None)
                if not answer_text:
                    chunks_list = []
                    for block in getattr(response, "output", []) or []:
                        for content in getattr(block, "content", []) or []:
                            text_obj = getattr(content, "text", None)
                            if isinstance(text_obj, dict):
                                value = text_obj.get("value")
                            else:
                                value = getattr(text_obj, "value", None) or text_obj
                            if value:
                                chunks_list.append(value)
                    answer_text = "".join(chunks_list).strip()
                
                if not answer_text:
                    raise RuntimeError(f"Unexpected response format: {response}")
                
                # Extract token usage if available
                token_usage = None
                if hasattr(response, 'usage'):
                    token_usage = {
                        'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
                        'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
                        'total_tokens': getattr(response.usage, 'total_tokens', 0),
                    }
                
            except Exception as e:
                logger.error(f"LLM call failed: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to generate answer: {str(e)}"
                )
            
            # Convert chunks to response format
            chunk_responses = [
                ChunkResponse(
                    id=chunk.id,
                    meeting_id=chunk.meeting_id,
                    meeting_native_id=chunk.meeting_native_id,
                    platform=chunk.platform,
                    speaker=chunk.speaker,
                    text=chunk.text,
                    start_time=chunk.start_time,
                    end_time=chunk.end_time,
                    timestamp=chunk.timestamp.isoformat() if chunk.timestamp else None,
                    chunk_type=chunk.chunk_type,
                    similarity_score=chunk.similarity_score,
                )
                for chunk in chunks
            ]
            
            return RAGQueryResponse(
                answer=answer_text,
                chunks=chunk_responses,
                token_usage=token_usage,
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("RAG_API_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)

