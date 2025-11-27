import os
from datetime import datetime
from typing import List, Optional

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from shared_models.database import sync_engine
from shared_models.models import (
    ActionItem,
    Meeting,
    MeetingMetadata,
    SpeakerHighlight,
)


SessionLocal = sessionmaker(bind=sync_engine)

st.set_page_config(page_title="Инсайты", layout="wide")
st.title("📊 AI Scrum Master • Инсайты")


def fetch_meetings():
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


def get_meeting_details(meeting_id: int):
    with SessionLocal() as session:
        meeting = session.get(Meeting, meeting_id)
        metadata = meeting.metadata_record if meeting else None
        action_items = (
            session.query(ActionItem)
            .filter(ActionItem.meeting_id == meeting_id)
            .order_by(ActionItem.due_date.asc().nulls_last())
            .all()
        )
        highlights = (
            session.query(SpeakerHighlight)
            .filter(SpeakerHighlight.meeting_id == meeting_id)
            .order_by(SpeakerHighlight.start_time.asc())
            .all()
        )
        return meeting, metadata, action_items, highlights


def format_datetime(value: Optional[datetime]) -> str:
    return value.isoformat(sep=" ", timespec="minutes") if value else "—"


meetings = fetch_meetings()

if not meetings:
    st.info("Нет обработанных встреч. Убедитесь, что worker сгенерировал инсайты.")
    st.stop()

meeting_labels = [entry["label"] for entry in meetings]
selected_label = st.sidebar.selectbox("Выберите встречу", meeting_labels, index=0)

selected_entry = next(entry for entry in meetings if entry["label"] == selected_label)
selected_meeting_id = selected_entry["id"]

meeting, metadata, action_items, highlights = get_meeting_details(selected_meeting_id)
insights_blob = (meeting.data or {}).get("insights_ru") if meeting else None
responsible_people = insights_blob.get("responsible_people", []) if isinstance(insights_blob, dict) else []
critical_deadlines = insights_blob.get("critical_deadlines", []) if isinstance(insights_blob, dict) else []
blockers = insights_blob.get("blockers", []) if isinstance(insights_blob, dict) else []
task_breakdown = insights_blob.get("task_breakdown", []) if isinstance(insights_blob, dict) else []
team_snapshot = (meeting.data or {}).get("team_roster_snapshot") if meeting else None

col1, col2, col3 = st.columns(3)
col1.metric("ID встречи", meeting.platform_specific_id or meeting.id)
col2.metric("Статус", meeting.status)
col3.metric(
    "Обработано",
    format_datetime(meeting.processed_at),
)

st.subheader("Обзор")
if metadata:
    st.write(f"**Цель:** {metadata.goal or 'н/д'}")
    st.write(f"**Резюме:** {metadata.summary or 'н/д'}")
    st.write(f"**Настроение:** {metadata.sentiment or 'неизвестно'}")
else:
    st.warning("Инсайты для этой встречи пока недоступны.")

if insights_blob:
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Ответственные", len(responsible_people))
    metric_col2.metric("Критичные сроки", len(critical_deadlines))
    metric_col3.metric("Блокеры", len(blockers))

    st.subheader("Ответственные и загрузка")
    if responsible_people:
        for person in responsible_people:
            st.markdown(
                f"**{person.get('person', '—')}** — {person.get('role', '—')} "
                f"(нагрузка: {person.get('workload', 'нет данных')})"
            )
            tasks = person.get("key_tasks") or []
            notes = person.get("notes")
            if tasks:
                st.write("Ключевые задачи: " + "; ".join(tasks))
            if notes:
                st.caption(notes)
            st.divider()
    else:
        st.info("Нет данных об ответственных.")

    st.subheader("Критичные сроки")
    if critical_deadlines:
        deadline_rows = []
        for entry in critical_deadlines:
            deadline_rows.append(
                {
                    "Этап": entry.get("name", ""),
                    "Ответственный": entry.get("owner", ""),
                    "Дата": entry.get("date", ""),
                    "Риск": entry.get("risk", ""),
                    "Зависимости": entry.get("dependencies", ""),
                }
            )
        st.table(deadline_rows)
    else:
        st.info("Нет критичных сроков.")

    st.subheader("Блокеры")
    if blockers:
        for blocker in blockers:
            st.markdown(
                f"- **{blocker.get('description', 'Без описания')}** "
                f"(владелец: {blocker.get('owner', '—')})"
            )
            st.write(f"Влияние: {blocker.get('impact', '—')}")
            if blocker.get("proposed_action"):
                st.caption(f"Рекомендация: {blocker['proposed_action']}")
    else:
        st.info("Блокеров не обнаружено.")

    st.subheader("Декомпозиция задач")
    if task_breakdown:
        for epic in task_breakdown:
            with st.expander(f"{epic.get('parent_task', 'Инициатива')} · приоритет: {epic.get('priority', '—')}"):
                st.write(epic.get("description", ""))
                if epic.get("recommended_tools"):
                    st.caption("Рекомендованные инструменты: " + ", ".join(epic["recommended_tools"]))
                subtasks = epic.get("subtasks") or []
                for sub in subtasks:
                    st.markdown(
                        f"* {sub.get('title', 'Подзадача')} "
                        f"(ответственный: {sub.get('owner', '—')}, срок: {sub.get('due_date', '—')})"
                    )
                    if sub.get("handoff_notes"):
                        st.caption(f"Передача: {sub['handoff_notes']}")
    else:
        st.info("Нет декомпозиции задач.")

if team_snapshot:
    st.subheader("Состав команды (snapshot из TXT)")
    st.code(team_snapshot, language="markdown")

st.subheader("Задачи")
if action_items:
    for item in action_items:
        cols = st.columns([3, 2, 2, 1])
        cols[0].write(f"- {item.description}")
        cols[1].write(f"Ответственный: {item.owner or 'н/д'}")
        cols[2].write(f"Срок: {format_datetime(item.due_date)}")
        cols[3].write(item.status or "ожидает")
else:
    st.write("Задачи не обнаружены.")

st.subheader("Ключевые моменты спикеров")
if highlights:
    for highlight in highlights:
        st.write(
            f"*{highlight.speaker or 'Неизвестно'}* "
            f"({highlight.start_time:.1f}-{highlight.end_time:.1f}s): {highlight.text}"
        )
else:
    st.write("Ключевые моменты не извлечены.")
