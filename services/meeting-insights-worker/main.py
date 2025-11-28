import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import httpx

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from shared_models.database import sync_engine
from shared_models.models import (
    ActionItem,
    Meeting,
    MeetingMetadata,
    SpeakerHighlight,
    TranscriptEmbedding,
    Transcription,
)
from shared_models.rag import compute_chunk_hash


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("meeting_insights_worker")


SessionLocal = sessionmaker(bind=sync_engine)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY must be set for meeting insights worker")

SUMMARY_MODEL = os.environ.get("OPENAI_SUMMARY_MODEL", "gpt-5-nano")
EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
POLL_INTERVAL = int(os.environ.get("INSIGHTS_POLL_INTERVAL", "30"))
BATCH_SIZE = int(os.environ.get("INSIGHTS_BATCH_SIZE", "1"))
TARGET_STATUSES = [
    status.strip()
    for status in os.environ.get("INSIGHTS_TARGET_STATUSES", "completed").split(",")
    if status.strip()
]
SEGMENT_LIMIT = int(os.environ.get("INSIGHTS_SEGMENT_LIMIT", "300"))
TEAM_ROSTER_PATH = os.environ.get("TEAM_ROSTER_PATH", "team_roster.txt")

client = OpenAI(api_key=OPENAI_API_KEY)


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def select_next_meeting(session: Session) -> Optional[Meeting]:
    stmt = (
        select(Meeting)
        .where(
            Meeting.status.in_(TARGET_STATUSES),
            Meeting.summary_state.in_(["pending", "error", None]),
        )
        .order_by(Meeting.updated_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    meeting = session.execute(stmt).scalars().first()
    if meeting:
        meeting.summary_state = "processing"
        session.commit()
        session.refresh(meeting)
    return meeting


def build_transcript_payload(meeting: Meeting, segments: List[Transcription]) -> str:
    lines = []
    base_time = meeting.start_time
    for idx, segment in enumerate(segments[:SEGMENT_LIMIT], start=1):
        speaker = segment.speaker or "Unknown"
        rel_window = f"{segment.start_time:.2f}-{segment.end_time:.2f}s"
        abs_time = (
            (base_time + timedelta(seconds=segment.start_time)).isoformat()
            if base_time
            else "n/a"
        )
        lines.append(
            f"{idx}. [{rel_window} | {abs_time}] {speaker}: {segment.text.strip()}"
        )
    return "\n".join(lines)


def load_team_context() -> Optional[str]:
    if not TEAM_ROSTER_PATH:
        return None
    try:
        with open(TEAM_ROSTER_PATH, "r", encoding="utf-8") as roster_file:
            data = roster_file.read().strip()
            return data or None
    except FileNotFoundError:
        logger.warning("Team roster file %s not found; continuing without roster context", TEAM_ROSTER_PATH)
        return None


def build_insights_prompt(
    meeting: Meeting,
    transcript_payload: str,
    team_context: Optional[str],
) -> List[Dict[str, str]]:
    system_prompt = (
        "Ты — русскоязычный AI Scrum Master ForteBank. "
        "Анализируй стенограммы встреч, выделяй бизнес-эффект, риски, ответственных и план действий. "
        "Пиши в деловом стиле, чтобы результаты можно было сразу переносить в дашборды.\n\n"
        "ВАЖНО: Транскрипты могут содержать галлюцинации (ошибочные или нерелевантные фразы, появившиеся из-за ошибок распознавания речи). "
        "Игнорируй любой текст из транскрипта, который:\n"
        "- Не относится к теме встречи или деловой тематике\n"
        "- Выглядит бессмысленным или нелогичным\n"
        "- Не соответствует контексту обсуждения\n"
        "- Содержит случайные слова или фразы, не связанные с бизнес-контекстом\n"
        "- Является техническими артефактами распознавания (например, повторяющиеся символы, тестовые фразы)\n\n"
        "Используй только релевантный, осмысленный контекст, который логично связан с деловой тематикой встречи. "
        "Если фраза выглядит подозрительно или не относится к обсуждаемой теме, исключи её из анализа."
    )

    schema_description = """
Верни JSON строго в следующей структуре (все поля на русском языке):
{
  "overview": {
    "goal": "Ключевая цель встречи",
    "summary": "Краткое резюме (2-3 предложения)",
    "sentiment": "позитивный|нейтральный|негативный"
  },
  "responsible_people": [
    {
      "person": "Имя/роль",
      "role": "Зона ответственности",
      "key_tasks": ["Список ключевых задач"],
      "workload": "низкая|средняя|высокая",
      "notes": "Особые замечания/риски"
    }
  ],
  "critical_deadlines": [
    {
      "name": "Название шага",
      "owner": "Ответственный",
      "date": "ISO8601",
      "risk": "Последствия срыва",
      "dependencies": "Что требуется или предшествует"
    }
  ],
  "blockers": [
    {
      "description": "Описание проблемы",
      "owner": "Кто решает",
      "impact": "Как влияет на бизнес/проект",
      "proposed_action": "Шаги разблокировки"
    }
  ],
  "task_breakdown": [
    {
      "parent_task": "Название инициативы",
      "description": "Суть работы",
      "priority": "высокий|средний|низкий",
      "recommended_tools": ["Рекомендуемые LLM/сервисы"],
      "subtasks": [
        {
          "title": "Название подзадачи",
          "owner": "Кому поручить",
          "due_date": "ISO8601 или пусто",
          "dependencies": "Что нужно для старта",
          "handoff_notes": "Информация для следующей роли"
        }
      ]
    }
  ],
  "action_items": [
    {
      "description": "Конкретное действие",
      "owner": "Ответственный",
      "due_date": "ISO8601 или пусто",
      "status": "новая|в работе|завершена|заблокирована",
      "priority": "высокий|средний|низкий",
      "reference": "Ссылки/контекст при наличии"
    }
  ],
  "speaker_digests": [
    {
      "name": "Имя спикера",
      "highlights": [
        {"text": "Ключевой тезис", "start": 0, "end": 0, "label": "обновление|решение|блокер|другое"}
      ]
    }
  ],
  "llm_suggestions": {
    "task_assignments": [
      {
        "task_description": "Описание задачи без ответственного",
        "suggested_owner": "Имя из команды",
        "reasoning": "Обоснование назначения на основе роли и зоны ответственности",
        "confidence": "высокая|средняя|низкая"
      }
    ],
    "subtask_breakdowns": [
      {
        "parent_task": "Название большой задачи",
        "suggested_subtasks": [
          {
            "title": "Название подзадачи",
            "suggested_owner": "Имя из команды",
            "estimated_effort": "низкая|средняя|высокая",
            "dependencies": "Что нужно для старта",
            "reasoning": "Почему эта декомпозиция поможет"
          }
        ],
        "reasoning": "Почему эта задача нуждается в декомпозиции"
      }
    ]
  }
}
"""

    roster_section = (
        f"\nСостав команды и роли (из текстового файла):\n{team_context}\n"
        if team_context
        else ""
    )

    user_prompt = f"""
Информация о встрече:
- Платформа: {meeting.platform}
- Идентификатор: {meeting.platform_specific_id}
- Начало: {meeting.start_time}
{roster_section}
Фрагменты транскрипта (до {SEGMENT_LIMIT} записей):
{transcript_payload}

ВАЖНО: 
1. Некоторые фразы в транскрипте могут быть галлюцинациями (ошибками распознавания речи). 
При анализе:
- Игнорируй фразы, которые не относятся к деловой тематике встречи
- Исключай бессмысленные или нелогичные фрагменты
- Не используй случайные слова или технические артефакты распознавания
- Фокусируйся только на релевантном контенте, который логично связан с обсуждаемой темой

2. В поле "llm_suggestions.task_assignments" добавь предложения по назначению ответственных для задач, которые упомянуты в транскрипте БЕЗ указания ответственного. Используй состав команды из roster_section для определения подходящего человека на основе роли и зоны ответственности.

3. В поле "llm_suggestions.subtask_breakdowns" добавь декомпозицию больших или сложных задач на подзадачи. Определи задачи, которые слишком большие или неопределенные, и разбей их на конкретные подзадачи с назначением ответственных.

4. Если в транскрипте все задачи уже имеют ответственных и все задачи достаточно конкретны, оставь массивы пустыми, но поле "llm_suggestions" должно присутствовать.

Сформируй JSON ровно по схеме выше без пояснений снаружи, используя только релевантный контекст из транскрипта.
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": schema_description},
        {"role": "user", "content": user_prompt},
    ]


def call_summary_model(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Calls the Responses API and returns the parsed JSON payload. Newer versions of
    openai-python (>=2.8.x) expose `response.output_text`, but the SDK may also
    stream structured content blocks. This helper normalizes both cases.
    """
    response = client.responses.create(model=SUMMARY_MODEL, input=messages)

    text_payload = getattr(response, "output_text", None)

    if not text_payload:
        chunks: List[str] = []
        for block in getattr(response, "output", []) or []:
            for content in getattr(block, "content", []) or []:
                text_obj = getattr(content, "text", None)
                if isinstance(text_obj, dict):
                    value = text_obj.get("value")
                else:
                    value = getattr(text_obj, "value", None) or text_obj
                if value:
                    chunks.append(value)
        text_payload = "".join(chunks).strip()

    if not text_payload:
        raise RuntimeError(f"Unexpected response format: {response}")

    return json.loads(text_payload)


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    embeddings: List[List[float]] = []
    for chunk in chunk_list(texts, 50):
        result = client.embeddings.create(model=EMBEDDING_MODEL, input=chunk)
        embeddings.extend([data.embedding for data in result.data])
    return embeddings


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def embed_structured_insights(
    session: Session,
    meeting: Meeting,
    insights: Dict[str, Any],
    client: OpenAI,
) -> None:
    """
    Create embeddings for structured insights content (overview, blockers, action items).
    These are stored as separate chunks with chunk_type='insight' or 'action_item'.
    """
    texts_to_embed = []
    metadata_list = []
    
    # Embed overview
    overview = insights.get("overview", {})
    if overview:
        overview_text = f"Цель встречи: {overview.get('goal', '')}\nРезюме: {overview.get('summary', '')}\nНастроение: {overview.get('sentiment', '')}"
        texts_to_embed.append(overview_text)
        metadata_list.append({
            'chunk_type': 'insight',
            'text': overview_text,
            'source': 'overview',
        })
    
    # Embed blockers
    blockers = insights.get("blockers", [])
    for blocker in blockers:
        blocker_text = f"Блокер: {blocker.get('description', '')}\nВладелец: {blocker.get('owner', '')}\nВлияние: {blocker.get('impact', '')}"
        texts_to_embed.append(blocker_text)
        metadata_list.append({
            'chunk_type': 'insight',
            'text': blocker_text,
            'source': 'blocker',
        })
    
    # Embed critical deadlines
    deadlines = insights.get("critical_deadlines", [])
    for deadline in deadlines:
        deadline_text = f"Критичный срок: {deadline.get('name', '')}\nОтветственный: {deadline.get('owner', '')}\nДата: {deadline.get('date', '')}\nРиск: {deadline.get('risk', '')}"
        texts_to_embed.append(deadline_text)
        metadata_list.append({
            'chunk_type': 'insight',
            'text': deadline_text,
            'source': 'deadline',
        })
    
    # Embed action items
    action_items = insights.get("action_items", [])
    for item in action_items:
        action_text = f"Действие: {item.get('description', '')}\nОтветственный: {item.get('owner', '')}\nСрок: {item.get('due_date', '')}\nПриоритет: {item.get('priority', '')}"
        texts_to_embed.append(action_text)
        metadata_list.append({
            'chunk_type': 'action_item',
            'text': action_text,
            'source': 'action_item',
        })
    
    if not texts_to_embed:
        return
    
    # Generate embeddings
    embeddings_result = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts_to_embed
    )
    
    meeting_date = meeting.start_time.date() if meeting.start_time else None
    
    # Store embeddings
    for metadata, embedding_data in zip(metadata_list, embeddings_result.data):
        chunk_hash = compute_chunk_hash(metadata['text'], meeting.id, metadata['chunk_type'])
        
        # Check if chunk already exists
        existing = session.query(TranscriptEmbedding).filter_by(
            meeting_id=meeting.id,
            chunk_hash=chunk_hash
        ).first()
        
        if existing:
            # Update existing embedding
            existing.embedding = embedding_data.embedding
            existing.text = metadata['text']
        else:
            # Create new embedding
            session.add(
                TranscriptEmbedding(
                    meeting_id=meeting.id,
                    text=metadata['text'],
                    embedding=embedding_data.embedding,
                    chunk_type=metadata['chunk_type'],
                    meeting_native_id=meeting.platform_specific_id,
                    platform=meeting.platform,
                    chunk_hash=chunk_hash,
                    meeting_date=meeting_date,
                    timestamp=meeting.start_time,
                )
            )


def persist_insights(
    session: Session,
    meeting: Meeting,
    insights: Dict[str, Any],
    segments: List[Transcription],
    embeddings: List[List[float]],
) -> None:
    session.query(SpeakerHighlight).filter_by(meeting_id=meeting.id).delete()
    session.query(ActionItem).filter_by(meeting_id=meeting.id).delete()
    session.query(TranscriptEmbedding).filter_by(meeting_id=meeting.id).delete()

    metadata_record = meeting.metadata_record or MeetingMetadata(meeting_id=meeting.id)
    overview = insights.get("overview", {})
    metadata_record.llm_version = SUMMARY_MODEL
    metadata_record.goal = overview.get("goal")
    metadata_record.summary = overview.get("summary")
    metadata_record.sentiment = overview.get("sentiment")
    metadata_record.blockers = insights.get("blockers") or []
    metadata_record.deadlines = insights.get("critical_deadlines") or []
    metadata_record.updated_at = datetime.utcnow()

    if not meeting.metadata_record:
        session.add(metadata_record)

    for speaker_entry in insights.get("speaker_digests", []):
        speaker_name = speaker_entry.get("name")
        for highlight in speaker_entry.get("highlights", []):
            start = highlight.get("start")
            end = highlight.get("end")
            absolute_start = (
                meeting.start_time + timedelta(seconds=start)
                if meeting.start_time and isinstance(start, (int, float))
                else None
            )
            absolute_end = (
                meeting.start_time + timedelta(seconds=end)
                if meeting.start_time and isinstance(end, (int, float))
                else None
            )
            session.add(
                SpeakerHighlight(
                    meeting_id=meeting.id,
                    speaker=speaker_name,
                    start_time=start,
                    end_time=end,
                    absolute_start_time=absolute_start,
                    absolute_end_time=absolute_end,
                    text=highlight.get("text"),
                    label=highlight.get("label"),
                )
            )

    def enqueue_action(
        description: str,
        owner: Optional[str],
        due_date: Optional[str],
        status: Optional[str],
        priority: Optional[str],
        reference: Optional[str] = None,
    ):
        session.add(
            ActionItem(
                meeting_id=meeting.id,
                owner=owner,
                description=description,
                due_date=parse_iso_datetime(due_date),
                status=status,
                priority=priority,
                reference_url=reference,
            )
        )

    for item in insights.get("action_items", []):
        enqueue_action(
            item.get("description", ""),
            item.get("owner"),
            item.get("due_date"),
            item.get("status"),
            item.get("priority"),
            item.get("reference"),
        )

    for epic in insights.get("task_breakdown", []):
        parent = epic.get("parent_task")
        priority = epic.get("priority")
        for subtask in epic.get("subtasks", []):
            description = f"[{parent}] {subtask.get('title')}"
            enqueue_action(
                description,
                subtask.get("owner"),
                subtask.get("due_date"),
                "новая",
                priority,
                subtask.get("dependencies"),
            )

    for segment, vector in zip(segments, embeddings):
        absolute_ts = (
            meeting.start_time + timedelta(seconds=segment.start_time)
            if meeting.start_time
            else None
        )
        meeting_date = meeting.start_time.date() if meeting.start_time else None
        chunk_hash = compute_chunk_hash(segment.text, meeting.id, 'transcript')
        
        session.add(
            TranscriptEmbedding(
                meeting_id=meeting.id,
                segment_start=segment.start_time,
                segment_end=segment.end_time,
                speaker=segment.speaker,
                text=segment.text,
                timestamp=absolute_ts,
                embedding=vector,
                chunk_type='transcript',
                meeting_native_id=meeting.platform_specific_id,
                platform=meeting.platform,
                language=segment.language,
                chunk_hash=chunk_hash,
                meeting_date=meeting_date,
            )
        )


def process_meeting(session: Session, meeting: Meeting) -> None:
    segments = (
        session.execute(
            select(Transcription)
            .where(Transcription.meeting_id == meeting.id)
            .order_by(Transcription.start_time.asc())
        )
        .scalars()
        .all()
    )

    if not segments:
        logger.info("Meeting %s has no transcripts; marking as completed", meeting.id)
        meeting.summary_state = "no_data"
        meeting.processed_at = datetime.utcnow()
        session.commit()
        return

    transcript_payload = build_transcript_payload(meeting, segments)
    team_context = load_team_context()
    messages = build_insights_prompt(meeting, transcript_payload, team_context)
    insights = call_summary_model(messages)

    texts = [seg.text for seg in segments]
    embeddings = generate_embeddings(texts)

    persist_insights(session, meeting, insights, segments, embeddings)

    meeting.data = meeting.data or {}
    meeting.data["insights_ru"] = insights
    if team_context:
        meeting.data["team_roster_snapshot"] = team_context

    # Embed structured insights content
    try:
        embed_structured_insights(session, meeting, insights, client)
    except Exception as e:
        logger.warning("Failed to embed structured insights for meeting %s: %s", meeting.id, e)

    meeting.summary_state = "completed"
    meeting.processed_at = datetime.utcnow()
    session.commit()
    logger.info("Meeting %s processed successfully", meeting.id)
    
    # Trigger email notification for this meeting
    try:
        email_notifier_url = os.environ.get("EMAIL_NOTIFIER_URL", "http://email-notifier:8003")
        trigger_url = f"{email_notifier_url}/trigger"
        
        response = httpx.post(
            trigger_url,
            json={"meeting_id": meeting.id},
            timeout=5.0
        )
        if response.status_code == 200:
            logger.info("Email notification triggered for meeting %s", meeting.id)
        else:
            logger.warning("Failed to trigger email notification for meeting %s: %s", meeting.id, response.text)
    except Exception as e:
        # Don't fail meeting processing if email trigger fails
        logger.warning("Error triggering email notification for meeting %s: %s", meeting.id, e)
    
    # Trigger Jira sync for this meeting
    try:
        jira_sync_url = os.environ.get("JIRA_SYNC_URL", "http://jira-sync-worker:8004")
        trigger_url = f"{jira_sync_url}/trigger"
        
        response = httpx.post(
            trigger_url,
            json={"meeting_id": meeting.id},
            timeout=5.0
        )
        if response.status_code == 200:
            logger.info("Jira sync triggered for meeting %s", meeting.id)
        else:
            logger.warning("Failed to trigger Jira sync for meeting %s: %s", meeting.id, response.text)
    except Exception as e:
        # Don't fail meeting processing if Jira sync trigger fails
        logger.warning("Error triggering Jira sync for meeting %s: %s", meeting.id, e)


def process_batch() -> bool:
    processed_any = False
    with SessionLocal() as session:
        for _ in range(BATCH_SIZE):
            meeting = select_next_meeting(session)
            if not meeting:
                break
            try:
                process_meeting(session, meeting)
                processed_any = True
            except Exception as exc:
                logger.exception("Failed to process meeting %s", meeting.id)
                meeting.summary_state = "error"
                session.commit()
    return processed_any


def main():
    logger.info("Starting meeting insights worker (summary model: %s)", SUMMARY_MODEL)
    while True:
        had_work = process_batch()
        sleep_for = 2 if had_work else POLL_INTERVAL
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()

