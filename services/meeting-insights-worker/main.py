import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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
        "Пиши в деловом стиле, чтобы результаты можно было сразу переносить в дашборды."
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
  ]
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

Сформируй JSON ровно по схеме выше без пояснений снаружи.
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
        session.add(
            TranscriptEmbedding(
                meeting_id=meeting.id,
                segment_start=segment.start_time,
                segment_end=segment.end_time,
                speaker=segment.speaker,
                text=segment.text,
                timestamp=absolute_ts,
                embedding=vector,
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

    meeting.summary_state = "completed"
    meeting.processed_at = datetime.utcnow()
    session.commit()
    logger.info("Meeting %s processed successfully", meeting.id)


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

