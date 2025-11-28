"""Jira Sync Worker - Syncs meeting insights to Jira issues"""
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from shared_models.database import sync_engine
from shared_models.models import ActionItem, Meeting, MeetingMetadata

from config import (
    BATCH_SIZE,
    POLL_INTERVAL,
    PRIORITY_MAPPING,
    JIRA_PROJECT_KEY,
    JIRA_ISSUE_TYPE_TASK,
    JIRA_ISSUE_TYPE_BLOCKER,
    JIRA_ISSUE_TYPE_DEADLINE,
    JIRA_ISSUE_TYPE_EPIC,
    JIRA_ISSUE_TYPE_FEATURE,
    JIRA_ISSUE_TYPE_BUG,
    JIRA_LABEL_BLOCKER,
    JIRA_LABEL_DEADLINE,
    JIRA_LABEL_ACTION_ITEM,
    JIRA_LABEL_MEETING,
    validate_config,
    openai_client,
    TASK_CLASSIFICATION_MODEL,
)
from jira_client import JiraClient
from team_mapper import get_jira_account_id

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("jira_sync_worker")

SessionLocal = sessionmaker(bind=sync_engine)


def format_jira_description(
    text: str, meeting: Meeting, context: Optional[str] = None
) -> str:
    """Format text as Jira description with meeting context"""
    meeting_url = meeting.constructed_meeting_url or "N/A"
    meeting_info = f"""
*Meeting Information:*
* Platform: {meeting.platform}
* Meeting ID: {meeting.platform_specific_id}
* Meeting URL: {meeting_url}
* Date: {meeting.start_time.strftime('%Y-%m-%d %H:%M') if meeting.start_time else 'N/A'}
"""
    if context:
        meeting_info += f"\n*Context:*\n{context}\n"

    return f"{meeting_info}\n---\n\n{text}"


def map_priority(priority: Optional[str]) -> Optional[str]:
    """Map Russian priority to Jira priority name"""
    if not priority:
        return None
    priority_lower = priority.lower()
    return PRIORITY_MAPPING.get(priority_lower)


def format_due_date(due_date: Optional[datetime]) -> Optional[str]:
    """Format datetime to Jira date string (YYYY-MM-DD)"""
    if not due_date:
        return None
    if isinstance(due_date, str):
        # Try to parse if it's a string
        try:
            due_date = datetime.fromisoformat(due_date.replace("Z", "+00:00"))
        except:
            return None
    return due_date.strftime("%Y-%m-%d")


def classify_task_type(
    description: str,
    context: Optional[str] = None,
    insights: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Classify task type using LLM based on description and context.
    Returns: 'epic', 'feature', 'task', or 'bug'
    
    Falls back to 'task' if LLM is unavailable or classification fails.
    """
    # Fallback to Task if OpenAI client is not available
    if not openai_client:
        logger.warning("OpenAI client not available, defaulting to Task type")
        return JIRA_ISSUE_TYPE_TASK
    
    try:
        # Build context for classification
        context_parts = []
        if context:
            context_parts.append(f"Meeting context: {context}")
        if insights:
            summary = insights.get("summary", "")
            if summary:
                context_parts.append(f"Meeting summary: {summary}")
        
        full_context = "\n".join(context_parts) if context_parts else "No additional context available."
        
        # Build prompt for LLM
        prompt = f"""You are a task classification assistant. Classify the following task into one of these types: Epic, Feature, Task, or Bug.

Task Description: {description}

Additional Context:
{full_context}

Classification Guidelines:
- **Epic**: Large, complex tasks that require multiple steps/phases, involve multiple components or integrations, or are explicitly described as "большая задача" (large task)
- **Feature**: New functionality being added, UI/UX work, new capabilities, new components or modules
- **Bug**: Fixing defects, errors, problems, or issues with existing functionality
- **Task**: General work items like documentation, testing, optimization, setup, configuration, decision-making, or selection work

Respond with ONLY one word: Epic, Feature, Task, or Bug. Do not include any explanation or additional text."""

        # Check if this is a newer model that requires max_completion_tokens
        is_new_model = "gpt-5" in TASK_CLASSIFICATION_MODEL.lower() or "o1" in TASK_CLASSIFICATION_MODEL.lower()
        
        # Build request parameters
        request_params = {
            "model": TASK_CLASSIFICATION_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a task classification assistant. Respond with only one word: Epic, Feature, Task, or Bug."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        }
        
        # Newer models (gpt-5-nano, o1) don't support custom temperature and use max_completion_tokens
        if is_new_model:
            request_params["max_completion_tokens"] = 10  # Only need one word
        else:
            request_params["temperature"] = 0.3  # Lower temperature for more consistent classification
            request_params["max_tokens"] = 10  # Only need one word
        
        # Call OpenAI API
        response = openai_client.chat.completions.create(**request_params)
        
        # Extract classification from response
        classification = response.choices[0].message.content.strip().lower()
        
        # Map LLM response to Jira issue types
        if "epic" in classification:
            return JIRA_ISSUE_TYPE_EPIC
        elif "feature" in classification or "story" in classification:
            return JIRA_ISSUE_TYPE_FEATURE
        elif "bug" in classification:
            return JIRA_ISSUE_TYPE_BUG
        else:
            # Default to Task for any other response
            return JIRA_ISSUE_TYPE_TASK
            
    except Exception as e:
        logger.error(f"Failed to classify task type using LLM: {e}", exc_info=True)
        # Fallback to Task on error
        return JIRA_ISSUE_TYPE_TASK


def select_next_meeting(session: Session) -> Optional[Meeting]:
    """
    Select next meeting that needs Jira sync.
    Criteria:
    - summary_state = 'completed' (insights generated)
    - data->'insights_ru' exists
    - data->>'jira_sync_state' IS NULL or = 'failed'
    """
    stmt = (
        select(Meeting)
        .where(
            Meeting.summary_state == "completed",
            Meeting.data.isnot(None),
        )
        .order_by(Meeting.processed_at.desc())  # Process newest meetings first
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    meeting = session.execute(stmt).scalars().first()
    if not meeting:
        return None

    # Check if insights exist and sync hasn't been completed
    insights = meeting.data.get("insights_ru") if meeting.data else None
    sync_state = meeting.data.get("jira_sync_state") if meeting.data else None

    if not insights:
        logger.debug(f"Meeting {meeting.id} has no insights_ru")
        return None

    if sync_state == "success":
        logger.debug(f"Meeting {meeting.id} already synced to Jira")
        return None

    # Mark as processing
    meeting.data = meeting.data or {}
    meeting.data["jira_sync_state"] = "processing"
    session.commit()
    session.refresh(meeting)
    return meeting


def sync_action_items(
    jira_client: JiraClient,
    meeting: Meeting,
    action_items: List[ActionItem],
    insights: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Create Jira issues for action items"""
    created_issues = []

    for action_item in action_items:
        # Resolve assignee
        assignee_account_id = None
        if action_item.owner:
            # First try team roster mapping
            assignee_account_id = get_jira_account_id(action_item.owner)
            # If not found, try Jira user search
            if not assignee_account_id:
                assignee_account_id = jira_client.find_user_by_name(action_item.owner)

        # Build description
        description_parts = [action_item.description]
        if action_item.reference_url:
            description_parts.append(f"\n*Reference:* {action_item.reference_url}")

        description = format_jira_description(
            "\n".join(description_parts), meeting
        )

        # Classify task type based on description and context
        # Get meeting summary/context from insights for better classification
        meeting_summary = insights.get("summary", "") if insights else ""
        task_type = classify_task_type(
            description=action_item.description,
            context=meeting_summary,
            insights=insights,
        )

        # Create issue
        issue = jira_client.create_issue(
            summary=f"{action_item.owner or 'Unassigned'}: {action_item.description[:100]}",
            description=description,
            issue_type=task_type,
            assignee_account_id=assignee_account_id,
            due_date=format_due_date(action_item.due_date),
            priority=map_priority(action_item.priority),
            labels=[JIRA_LABEL_ACTION_ITEM, JIRA_LABEL_MEETING],
        )

        if issue:
            created_issues.append(
                {
                    "local_id": action_item.id,
                    "jira_key": issue["key"],
                    "jira_id": issue["id"],
                    "type": "action_item",
                }
            )
            logger.info(
                f"Created Jira issue {issue['key']} for action item {action_item.id}"
            )

    return created_issues


def sync_blockers(
    jira_client: JiraClient,
    meeting: Meeting,
    blockers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Create Jira issues for blockers"""
    created_issues = []

    for blocker in blockers:
        description = blocker.get("description", "")
        owner = blocker.get("owner")
        impact = blocker.get("impact", "")
        proposed_action = blocker.get("proposed_action", "")

        # Build full description
        description_parts = [description]
        if impact:
            description_parts.append(f"\n*Impact:* {impact}")
        if proposed_action:
            description_parts.append(f"\n*Proposed Action:* {proposed_action}")

        full_description = format_jira_description(
            "\n".join(description_parts), meeting
        )

        # Resolve assignee
        assignee_account_id = None
        if owner:
            assignee_account_id = get_jira_account_id(owner)
            if not assignee_account_id:
                assignee_account_id = jira_client.find_user_by_name(owner)

        # Create issue
        issue = jira_client.create_issue(
            summary=f"Blocker: {description[:100]}",
            description=full_description,
            issue_type=JIRA_ISSUE_TYPE_BLOCKER,
            assignee_account_id=assignee_account_id,
            priority="High",  # Blockers are always high priority
            labels=[JIRA_LABEL_BLOCKER, JIRA_LABEL_MEETING],
        )

        if issue:
            created_issues.append(
                {
                    "jira_key": issue["key"],
                    "jira_id": issue["id"],
                    "type": "blocker",
                    "description": description,
                }
            )
            logger.info(f"Created Jira issue {issue['key']} for blocker")

    return created_issues


def sync_deadlines(
    jira_client: JiraClient,
    meeting: Meeting,
    deadlines: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Create Jira issues for critical deadlines"""
    created_issues = []

    for deadline in deadlines:
        name = deadline.get("name", "")
        owner = deadline.get("owner")
        date_str = deadline.get("date", "")
        risk = deadline.get("risk", "")
        dependencies = deadline.get("dependencies", "")

        # Parse date
        due_date = None
        if date_str:
            try:
                # Try ISO format
                due_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except:
                try:
                    # Try other common formats
                    due_date = datetime.strptime(date_str, "%Y-%m-%d")
                except:
                    logger.warning(f"Could not parse deadline date: {date_str}")

        # Build description
        description_parts = [f"*Deadline:* {name}"]
        if risk:
            description_parts.append(f"\n*Risk if missed:* {risk}")
        if dependencies:
            description_parts.append(f"\n*Dependencies:* {dependencies}")

        full_description = format_jira_description(
            "\n".join(description_parts), meeting
        )

        # Resolve assignee
        assignee_account_id = None
        if owner:
            assignee_account_id = get_jira_account_id(owner)
            if not assignee_account_id:
                assignee_account_id = jira_client.find_user_by_name(owner)

        # Create issue
        issue = jira_client.create_issue(
            summary=f"Deadline: {name}",
            description=full_description,
            issue_type=JIRA_ISSUE_TYPE_DEADLINE,
            assignee_account_id=assignee_account_id,
            due_date=format_due_date(due_date),
            priority="High",  # Deadlines are high priority
            labels=[JIRA_LABEL_DEADLINE, JIRA_LABEL_MEETING],
        )

        if issue:
            created_issues.append(
                {
                    "jira_key": issue["key"],
                    "jira_id": issue["id"],
                    "type": "deadline",
                    "name": name,
                }
            )
            logger.info(f"Created Jira issue {issue['key']} for deadline: {name}")

    return created_issues


def sync_meeting_to_jira(session: Session, meeting: Meeting) -> bool:
    """Sync a single meeting's insights to Jira"""
    insights = meeting.data.get("insights_ru") if meeting.data else None
    if not insights:
        logger.warning(f"Meeting {meeting.id} has no insights_ru")
        return False

    jira_client = JiraClient()
    all_created_issues = []

    try:
        # Sync action items
        action_items = (
            session.query(ActionItem)
            .filter(ActionItem.meeting_id == meeting.id)
            .all()
        )
        if action_items:
            created = sync_action_items(jira_client, meeting, action_items, insights)
            all_created_issues.extend(created)

        # Sync blockers
        blockers = insights.get("blockers", [])
        if blockers:
            created = sync_blockers(jira_client, meeting, blockers)
            all_created_issues.extend(created)

        # Sync deadlines
        deadlines = insights.get("critical_deadlines", [])
        if deadlines:
            created = sync_deadlines(jira_client, meeting, deadlines)
            all_created_issues.extend(created)

        # Update meeting data with sync results
        meeting.data = meeting.data or {}
        meeting.data["jira_sync_state"] = "success"
        meeting.data["jira_issues"] = all_created_issues
        meeting.data["jira_synced_at"] = datetime.utcnow().isoformat()

        session.commit()
        logger.info(
            f"Successfully synced meeting {meeting.id} to Jira: {len(all_created_issues)} issues created"
        )
        return True

    except Exception as e:
        logger.exception(f"Failed to sync meeting {meeting.id} to Jira: {e}")
        meeting.data = meeting.data or {}
        meeting.data["jira_sync_state"] = "failed"
        meeting.data["jira_error"] = str(e)
        session.commit()
        return False


def process_batch() -> bool:
    """Process a batch of meetings"""
    processed_any = False
    with SessionLocal() as session:
        for _ in range(BATCH_SIZE):
            meeting = select_next_meeting(session)
            if not meeting:
                break
            try:
                success = sync_meeting_to_jira(session, meeting)
                processed_any = True
                if not success:
                    logger.warning(f"Failed to sync meeting {meeting.id}")
            except Exception as exc:
                logger.exception(f"Error processing meeting {meeting.id}: {exc}")
                # Reset sync state on error
                meeting.data = meeting.data or {}
                meeting.data["jira_sync_state"] = None
                session.commit()
    return processed_any


def sync_meeting_by_id(meeting_id: int) -> bool:
    """Sync a specific meeting by ID (for HTTP trigger)"""
    with SessionLocal() as session:
        meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            logger.error(f"Meeting {meeting_id} not found")
            return False
        
        # Check if already synced
        sync_state = meeting.data.get("jira_sync_state") if meeting.data else None
        if sync_state == "success":
            logger.info(f"Meeting {meeting_id} already synced to Jira, skipping")
            return True
        
        return sync_meeting_to_jira(session, meeting)


def main():
    """Main worker loop"""
    # Validate configuration
    is_valid, error = validate_config()
    if not is_valid:
        logger.error(f"Configuration error: {error}")
        logger.error("Please set JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY")
        return

    logger.info("Starting Jira sync worker")
    logger.info(f"Jira project: {JIRA_PROJECT_KEY}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info(f"Batch size: {BATCH_SIZE}")

    while True:
        had_work = process_batch()
        sleep_for = 2 if had_work else POLL_INTERVAL
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()

