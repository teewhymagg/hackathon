"""
Jira Integration Service

This service receives LLM responses containing task breakdowns and creates
corresponding Jira tasks and subtasks via the Jira API.
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
from requests.auth import HTTPBasicAuth
from openai import OpenAI

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("jira_integration")

app = FastAPI(title="Jira Integration Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jira Configuration
JIRA_URL = os.environ.get("JIRA_URL")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "PROJ")
JIRA_ISSUE_TYPE = os.environ.get("JIRA_ISSUE_TYPE", "Task")
JIRA_SUBTASK_ISSUE_TYPE = os.environ.get("JIRA_SUBTASK_ISSUE_TYPE", "Sub-task")
JIRA_EPIC_ISSUE_TYPE = os.environ.get("JIRA_EPIC_ISSUE_TYPE", "Epic")

# OpenAI Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_JIRA_MODEL", "gpt-5-nano")


class TaskBreakdownItem(BaseModel):
    """Represents a task breakdown item from LLM response."""
    parent_task: str = Field(..., description="Parent task name")
    description: str = Field(..., description="Task description")
    priority: Optional[str] = Field(None, description="Priority: высокий|средний|низкий")
    recommended_tools: Optional[List[str]] = Field(default_factory=list)
    subtasks: Optional[List[Dict[str, Any]]] = Field(default_factory=list)


class ActionItem(BaseModel):
    """Represents an action item from LLM response."""
    description: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    reference: Optional[str] = None


class LLMResponse(BaseModel):
    """LLM response containing task breakdown and action items."""
    task_breakdown: Optional[List[TaskBreakdownItem]] = Field(default_factory=list)
    action_items: Optional[List[ActionItem]] = Field(default_factory=list)


class CreateJiraTasksRequest(BaseModel):
    """Request to create Jira tasks from LLM response."""
    llm_response: Dict[str, Any] = Field(..., description="LLM response JSON")
    meeting_id: Optional[int] = Field(None, description="Optional meeting ID for reference")
    meeting_summary: Optional[str] = Field(None, description="Optional meeting summary")
    create_subtasks: bool = Field(True, description="Whether to create subtasks")


class JiraTaskResponse(BaseModel):
    """Response containing created Jira task information."""
    issue_type: str = Field(..., description="Type: Epic, Task, or Sub-task")
    issue_key: str
    issue_url: str
    parent_key: Optional[str] = Field(None, description="Parent issue key if this is a subtask")
    child_keys: List[str] = Field(default_factory=list, description="Child issue keys if this is an epic/task")
    child_urls: List[str] = Field(default_factory=list)


class CreateJiraTasksResponse(BaseModel):
    """Response from creating Jira tasks."""
    success: bool
    created_tasks: List[JiraTaskResponse] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    llm_response: Optional[Dict[str, Any]] = Field(None, description="LLM response if generated")


class ProcessMeetingRequest(BaseModel):
    """Request to process meeting data and create Jira tasks."""
    meeting_transcript: Optional[str] = Field(None, description="Meeting transcript text")
    meeting_summary: Optional[str] = Field(None, description="Meeting summary or notes")
    meeting_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional meeting metadata")
    create_epics: bool = Field(True, description="Whether to create Epics for major initiatives")
    create_subtasks: bool = Field(True, description="Whether to create subtasks")


class JiraClient:
    """Client for interacting with Jira API."""
    
    def __init__(self, base_url: str, email: str, api_token: str):
        if not all([base_url, email, api_token]):
            raise ValueError("JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN must be set")
        
        self.base_url = base_url.rstrip("/")
        self.auth = HTTPBasicAuth(email, api_token)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
    
    def get_epic_name_field(self) -> Optional[str]:
        """Get the custom field ID for Epic Name. This varies by Jira instance."""
        # Try common field names
        url = f"{self.base_url}/rest/api/3/field"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            fields = response.json()
            for field in fields:
                field_name = field.get("name", "").lower()
                field_id = field.get("id", "")
                # Check for Epic Name field
                if "epic name" in field_name or field_id == "customfield_10011":
                    logger.info(f"Found Epic Name field: {field_id} ({field.get('name')})")
                    return field_id
        except Exception as e:
            logger.warning(f"Could not determine Epic Name field: {e}")
        
        # Try common field IDs
        common_epic_fields = ["customfield_10011", "customfield_10014"]
        for field_id in common_epic_fields:
            logger.info(f"Trying default Epic Name field: {field_id}")
            return field_id
        
        return "customfield_10011"  # Default common field ID
    
    def get_project_issue_types(self, project_key: str) -> List[Dict[str, Any]]:
        """Get available issue types for a project."""
        url = f"{self.base_url}/rest/api/3/project/{project_key}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            project_data = response.json()
            issue_types = project_data.get("issueTypes", [])
            return issue_types
        except Exception as e:
            logger.warning(f"Could not get issue types for project {project_key}: {e}")
            return []
    
    def get_issue_creation_metadata(self, project_key: str, issue_type: str) -> Optional[Dict[str, Any]]:
        """Get metadata for creating an issue, including required fields."""
        url = f"{self.base_url}/rest/api/3/issue/createmeta"
        params = {
            "projectKeys": project_key,
            "issuetypeNames": issue_type,
            "expand": "projects.issuetypes.fields"
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            metadata = response.json()
            projects = metadata.get("projects", [])
            if projects:
                project = projects[0]
                issue_types = project.get("issuetypes", [])
                if issue_types:
                    return issue_types[0]
            return None
        except Exception as e:
            logger.warning(f"Could not get creation metadata: {e}")
            return None
    
    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        due_date: Optional[str] = None,
        parent_key: Optional[str] = None,
        epic_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a Jira issue."""
        url = f"{self.base_url}/rest/api/3/issue"
        
        # Get available issue types to validate
        available_types = self.get_project_issue_types(project_key)
        issue_type_names = [it.get("name", "").lower() for it in available_types]
        
        # Try to find matching issue type (case-insensitive)
        matched_type = None
        for it in available_types:
            if it.get("name", "").lower() == issue_type.lower():
                matched_type = it.get("name")  # Use exact name from Jira
                break
        
        if not matched_type and available_types:
            # If exact match not found, log available types
            logger.warning(f"Issue type '{issue_type}' not found. Available types: {[it.get('name') for it in available_types]}")
            # Use the provided type anyway, Jira will return a clear error if invalid
            matched_type = issue_type
        elif not matched_type:
            matched_type = issue_type
        
        # Map priority from Russian to Jira priority names
        priority_map = {
            "высокий": "High",
            "средний": "Medium",
            "низкий": "Low",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        }
        jira_priority = priority_map.get(priority.lower() if priority else "medium", "Medium")
        
        # Clean summary: remove newlines and extra whitespace (Jira doesn't allow newlines in summary)
        summary = " ".join(summary.split())
        
        # Validate and truncate summary (Jira limit is 255 characters)
        if len(summary) > 255:
            logger.warning(f"Summary too long ({len(summary)} chars), truncating to 255")
            summary = summary[:252] + "..."
        
        # Ensure description is not empty
        if not description or not description.strip():
            description = "No description provided."
        
        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": matched_type},
                "priority": {"name": jira_priority},
            }
        }
        
        # Add description (Jira API v3 uses ADF format)
        if description:
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": description
                            }
                        ]
                    }
                ]
            }
        
        # Add Epic Name field if creating an Epic
        if issue_type.lower() == "epic" and epic_name:
            epic_field = self.get_epic_name_field()
            # Try to set Epic Name field, but don't fail if it doesn't exist
            # Some Jira instances don't require it or use different field IDs
            try:
                # First, try to get the actual field ID from the project's issue type metadata
                metadata = self.get_issue_creation_metadata(project_key, matched_type)
                if metadata:
                    fields = metadata.get("fields", {})
                    # Look for Epic Name field in the metadata
                    for field_id, field_info in fields.items():
                        field_name = field_info.get("name", "").lower()
                        if "epic name" in field_name:
                            epic_field = field_id
                            logger.info(f"Found Epic Name field from metadata: {epic_field}")
                            break
                
                # Only add Epic Name if we found a valid field
                if epic_field:
                    payload["fields"][epic_field] = epic_name
            except Exception as e:
                logger.warning(f"Could not set Epic Name field ({epic_field}): {e}. Creating Epic without Epic Name field.")
                # Continue without Epic Name - some Jira setups don't require it
        
        if assignee:
            # Try different assignee formats
            # First try as accountId (if it looks like an ID)
            if assignee.startswith("557058:") or len(assignee) > 20:
                payload["fields"]["assignee"] = {"accountId": assignee}
            else:
                # Try as email or username
                if "@" in assignee:
                    payload["fields"]["assignee"] = {"emailAddress": assignee}
                else:
                    payload["fields"]["assignee"] = {"name": assignee}
        
        if due_date:
            try:
                # Parse ISO date and format for Jira (YYYY-MM-DD)
                if "T" in due_date:
                    due_date = due_date.split("T")[0]
                payload["fields"]["duedate"] = due_date
            except Exception as e:
                logger.warning(f"Failed to parse due_date {due_date}: {e}")
        
        if parent_key:
            # For subtasks, parent is required
            # For tasks under epics, we use Epic Link field instead of parent
            if issue_type.lower() in ["sub-task", "subtask"]:
                payload["fields"]["parent"] = {"key": parent_key}
            elif issue_type.lower() == "epic":
                # Epics can't have parents
                pass
            else:
                # For regular tasks under epics, use Epic Link field
                # Try to find Epic Link field
                epic_link_field = None
                try:
                    url = f"{self.base_url}/rest/api/3/field"
                    response = self.session.get(url)
                    response.raise_for_status()
                    fields = response.json()
                    for field in fields:
                        if "epic link" in field.get("name", "").lower() or field.get("id") == "customfield_10014":
                            epic_link_field = field.get("id")
                            break
                    if epic_link_field:
                        payload["fields"][epic_link_field] = parent_key
                    else:
                        # Fallback: try to link via parent (may not work for all Jira setups)
                        payload["fields"]["parent"] = {"key": parent_key}
                except:
                    # If we can't find Epic Link, try parent
                    payload["fields"]["parent"] = {"key": parent_key}
        
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Created Jira issue: {result.get('key')} ({issue_type})")
            return result
        except requests.exceptions.HTTPError as e:
            error_detail = "Unknown error"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_detail = error_data.get('errors', {})
                    if not error_detail:
                        error_detail = error_data.get('errorMessages', [])
                    if not error_detail:
                        error_detail = e.response.text
                except:
                    error_detail = e.response.text
            logger.error(f"Failed to create Jira issue ({issue_type}): {error_detail}")
            logger.error(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            raise Exception(f"Jira API error: {error_detail}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create Jira issue: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise
    
    def get_issue_url(self, issue_key: str) -> str:
        """Get the URL for a Jira issue."""
        return f"{self.base_url}/browse/{issue_key}"


def parse_priority(priority: Optional[str]) -> Optional[str]:
    """Normalize priority value."""
    if not priority:
        return None
    priority_lower = priority.lower()
    if priority_lower in ["высокий", "high"]:
        return "высокий"
    elif priority_lower in ["средний", "medium"]:
        return "средний"
    elif priority_lower in ["низкий", "low"]:
        return "низкий"
    return priority


def call_openai_for_jira_structure(
    meeting_transcript: Optional[str],
    meeting_summary: Optional[str],
    create_epics: bool = True,
) -> Dict[str, Any]:
    """Call OpenAI API to generate structured Jira tasks, epics, and subtasks."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY must be set to generate Jira tasks from meeting data")
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    system_prompt = """Ты — AI помощник для создания структурированных задач в Jira.
Анализируй встречи и создавай иерархию задач: Epics (крупные инициативы), Tasks (задачи), и Sub-tasks (подзадачи).
Используй Epics для крупных проектов/инициатив, Tasks для конкретных задач, и Sub-tasks для детальных шагов."""
    
    schema_prompt = """
Верни JSON строго в следующей структуре:
{
  "epics": [
    {
      "name": "Название Epic (короткое, для Epic Name поля)",
      "summary": "Полное название Epic",
      "description": "Описание Epic и его цели",
      "priority": "высокий|средний|низкий",
      "tasks": [
        {
          "summary": "Название задачи",
          "description": "Описание задачи",
          "priority": "высокий|средний|низкий",
          "assignee": "email или имя ответственного (опционально)",
          "due_date": "ISO8601 дата (опционально)",
          "subtasks": [
            {
              "title": "Название подзадачи",
              "description": "Описание подзадачи",
              "assignee": "email или имя (опционально)",
              "due_date": "ISO8601 (опционально)",
              "dependencies": "Зависимости или требования"
            }
          ]
        }
      ]
    }
  ],
  "standalone_tasks": [
    {
      "summary": "Название задачи",
      "description": "Описание",
      "priority": "высокий|средний|низкий",
      "assignee": "email или имя (опционально)",
      "due_date": "ISO8601 (опционально)"
    }
  ],
  "action_items": [
    {
      "description": "Конкретное действие",
      "owner": "Ответственный",
      "due_date": "ISO8601 или пусто",
      "priority": "высокий|средний|низкий"
    }
  ]
}
"""
    
    # Build user content parts
    content_parts = ["Проанализируй следующую информацию о встрече и создай структурированные задачи для Jira."]
    content_parts.append("")
    
    if meeting_summary:
        content_parts.append(f"Краткое резюме встречи: {meeting_summary}")
        content_parts.append("")
    
    if meeting_transcript:
        content_parts.append("Транскрипт встречи:")
        content_parts.append(meeting_transcript)
    else:
        content_parts.append("Только резюме доступно.")
    
    content_parts.append("")
    
    if create_epics:
        content_parts.append("Создай Epics для крупных инициатив, если они есть.")
    else:
        content_parts.append("Создавай только Tasks, без Epics.")
    
    content_parts.append("")
    content_parts.append("Верни JSON строго по схеме выше, без дополнительных пояснений.")
    
    user_content = "\n".join(content_parts)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": schema_prompt},
        {"role": "user", "content": user_content}
    ]
    
    try:
        response = client.responses.create(model=OPENAI_MODEL, input=messages)
        
        text_payload = getattr(response, "output_text", None)
        if not text_payload:
            chunks = []
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
    except Exception as e:
        logger.error(f"Failed to call OpenAI API: {e}", exc_info=True)
        raise


def create_jira_tasks_from_llm_response(
    jira_client: JiraClient,
    llm_response: Dict[str, Any],
    meeting_summary: Optional[str] = None,
    create_epics: bool = True,
    create_subtasks: bool = True,
) -> CreateJiraTasksResponse:
    """Create Jira tasks from LLM response. Supports Epics, Tasks, and Sub-tasks."""
    result = CreateJiraTasksResponse(success=True, llm_response=llm_response)
    
    try:
        # Process Epics with their tasks
        epics = llm_response.get("epics", [])
        for epic_data in epics:
            try:
                epic_name = epic_data.get("name", epic_data.get("summary", "Untitled Epic"))
                epic_summary = epic_data.get("summary", epic_name)
                epic_description = epic_data.get("description", "")
                epic_priority = parse_priority(epic_data.get("priority"))
                
                if meeting_summary:
                    epic_description = f"Контекст встречи: {meeting_summary}\n\n{epic_description}"
                
                # Create Epic
                epic_issue = jira_client.create_issue(
                    project_key=JIRA_PROJECT_KEY,
                    summary=epic_summary,
                    description=epic_description,
                    issue_type=JIRA_EPIC_ISSUE_TYPE,
                    priority=epic_priority,
                    epic_name=epic_name,
                )
                
                epic_key = epic_issue["key"]
                epic_url = jira_client.get_issue_url(epic_key)
                
                epic_response = JiraTaskResponse(
                    issue_type="Epic",
                    issue_key=epic_key,
                    issue_url=epic_url,
                )
                
                # Create Tasks under this Epic
                tasks = epic_data.get("tasks", [])
                for task_data in tasks:
                    try:
                        task_summary = task_data.get("summary", "Untitled Task")
                        task_description = task_data.get("description", "")
                        task_priority = parse_priority(task_data.get("priority"))
                        task_assignee = task_data.get("assignee")
                        task_due_date = task_data.get("due_date")
                        subtasks = task_data.get("subtasks", [])
                        
                        # Create Task linked to Epic (using parent relationship)
                        task_issue = jira_client.create_issue(
                            project_key=JIRA_PROJECT_KEY,
                            summary=task_summary,
                            description=task_description,
                            issue_type=JIRA_ISSUE_TYPE,
                            priority=task_priority,
                            assignee=task_assignee,
                            due_date=task_due_date,
                            parent_key=epic_key,  # Link to epic
                        )
                        
                        task_key = task_issue["key"]
                        task_url = jira_client.get_issue_url(task_key)
                        
                        task_response = JiraTaskResponse(
                            issue_type="Task",
                            issue_key=task_key,
                            issue_url=task_url,
                            parent_key=epic_key,
                        )
                        
                        # Create Subtasks if requested
                        if create_subtasks and subtasks:
                            for subtask_data in subtasks:
                                try:
                                    subtask_title = subtask_data.get("title", "Untitled Subtask")
                                    subtask_description = subtask_data.get("description", subtask_data.get("dependencies", ""))
                                    subtask_owner = subtask_data.get("assignee")
                                    subtask_due_date = subtask_data.get("due_date")
                                    
                                    subtask_issue = jira_client.create_issue(
                                        project_key=JIRA_PROJECT_KEY,
                                        summary=subtask_title,
                                        description=subtask_description or "No description",
                                        issue_type=JIRA_SUBTASK_ISSUE_TYPE,
                                        priority=task_priority,
                                        assignee=subtask_owner,
                                        due_date=subtask_due_date,
                                        parent_key=task_key,
                                    )
                                    
                                    subtask_key = subtask_issue["key"]
                                    subtask_url = jira_client.get_issue_url(subtask_key)
                                    
                                    task_response.child_keys.append(subtask_key)
                                    task_response.child_urls.append(subtask_url)
                                    
                                except Exception as e:
                                    error_msg = f"Failed to create subtask '{subtask_data.get('title', 'unknown')}': {str(e)}"
                                    logger.error(error_msg)
                                    result.errors.append(error_msg)
                        
                        epic_response.child_keys.append(task_key)
                        epic_response.child_urls.append(task_url)
                        result.created_tasks.append(task_response)
                        
                    except Exception as e:
                        error_msg = f"Failed to create task '{task_data.get('summary', 'unknown')}': {str(e)}"
                        logger.error(error_msg)
                        result.errors.append(error_msg)
                
                result.created_tasks.append(epic_response)
                
            except Exception as e:
                error_msg = f"Failed to create epic '{epic_data.get('name', 'unknown')}': {str(e)}"
                logger.error(error_msg)
                result.errors.append(error_msg)
        
        # Process standalone tasks (from task_breakdown for backward compatibility or standalone_tasks)
        task_breakdown = llm_response.get("task_breakdown", [])
        standalone_tasks = llm_response.get("standalone_tasks", [])
        
        for task_item in task_breakdown + standalone_tasks:
            try:
                if isinstance(task_item, dict):
                    task_summary = task_item.get("parent_task") or task_item.get("summary", "Untitled Task")
                    task_description = task_item.get("description", "")
                    task_priority = parse_priority(task_item.get("priority"))
                    task_assignee = task_item.get("assignee") or task_item.get("owner")
                    task_due_date = task_item.get("due_date")
                    subtasks = task_item.get("subtasks", [])
                else:
                    continue
                
                if meeting_summary:
                    task_description = f"Контекст встречи: {meeting_summary}\n\n{task_description}"
                
                if task_item.get("recommended_tools"):
                    task_description += f"\n\nРекомендуемые инструменты: {', '.join(task_item.get('recommended_tools', []))}"
                
                # Create Task
                task_issue = jira_client.create_issue(
                    project_key=JIRA_PROJECT_KEY,
                    summary=task_summary,
                    description=task_description,
                    issue_type=JIRA_ISSUE_TYPE,
                    priority=task_priority,
                    assignee=task_assignee,
                    due_date=task_due_date,
                )
                
                task_key = task_issue["key"]
                task_url = jira_client.get_issue_url(task_key)
                
                task_response = JiraTaskResponse(
                    issue_type="Task",
                    issue_key=task_key,
                    issue_url=task_url,
                )
                
                # Create subtasks if requested
                if create_subtasks and subtasks:
                    for subtask in subtasks:
                        try:
                            subtask_title = subtask.get("title", "Untitled Subtask")
                            subtask_description = subtask.get("description", subtask.get("dependencies", ""))
                            subtask_owner = subtask.get("assignee") or subtask.get("owner")
                            subtask_due_date = subtask.get("due_date")
                            
                            if subtask.get("handoff_notes"):
                                subtask_description = f"{subtask_description}\n\nПримечания для передачи: {subtask.get('handoff_notes')}"
                            
                            subtask_issue = jira_client.create_issue(
                                project_key=JIRA_PROJECT_KEY,
                                summary=subtask_title,
                                description=subtask_description or "No description",
                                issue_type=JIRA_SUBTASK_ISSUE_TYPE,
                                priority=task_priority,
                                assignee=subtask_owner,
                                due_date=subtask_due_date,
                                parent_key=task_key,
                            )
                            
                            subtask_key = subtask_issue["key"]
                            subtask_url = jira_client.get_issue_url(subtask_key)
                            
                            task_response.child_keys.append(subtask_key)
                            task_response.child_urls.append(subtask_url)
                            
                        except Exception as e:
                            error_msg = f"Failed to create subtask '{subtask.get('title', 'unknown')}': {str(e)}"
                            logger.error(error_msg)
                            result.errors.append(error_msg)
                
                result.created_tasks.append(task_response)
                
            except Exception as e:
                error_msg = f"Failed to create task '{task_item.get('parent_task') or task_item.get('summary', 'unknown')}': {str(e)}"
                logger.error(error_msg)
                result.errors.append(error_msg)
        
        # Process action items (create as standalone tasks)
        action_items = llm_response.get("action_items", [])
        for action_item in action_items:
            try:
                description = action_item.get("description", "")
                owner = action_item.get("owner") or action_item.get("assignee")
                due_date = action_item.get("due_date")
                priority = parse_priority(action_item.get("priority"))
                
                # Use description as summary, but clean it (remove newlines, truncate)
                action_summary = " ".join(description.split())  # Remove newlines and extra spaces
                if len(action_summary) > 255:
                    action_summary = action_summary[:252] + "..."
                
                if meeting_summary:
                    description = f"Контекст встречи: {meeting_summary}\n\n{description}"
                
                if action_item.get("reference"):
                    description += f"\n\nСсылка: {action_item.get('reference')}"
                
                action_issue = jira_client.create_issue(
                    project_key=JIRA_PROJECT_KEY,
                    summary=action_summary,
                    description=description,
                    issue_type=JIRA_ISSUE_TYPE,
                    priority=priority,
                    assignee=owner,
                    due_date=due_date,
                )
                
                action_key = action_issue["key"]
                action_url = jira_client.get_issue_url(action_key)
                
                result.created_tasks.append(JiraTaskResponse(
                    issue_type="Task",
                    issue_key=action_key,
                    issue_url=action_url,
                ))
                
            except Exception as e:
                error_msg = f"Failed to create action item '{action_item.get('description', 'unknown')[:50]}': {str(e)}"
                logger.error(error_msg)
                result.errors.append(error_msg)
        
        if result.errors and not result.created_tasks:
            result.success = False
        
    except Exception as e:
        logger.exception("Failed to process LLM response")
        result.success = False
        result.errors.append(f"Failed to process LLM response: {str(e)}")
    
    return result


# Initialize Jira client
jira_client: Optional[JiraClient] = None
if JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN:
    try:
        jira_client = JiraClient(JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN)
        logger.info(f"Jira client initialized for {JIRA_URL}")
    except Exception as e:
        logger.error(f"Failed to initialize Jira client: {e}")
        jira_client = None
else:
    logger.warning("Jira credentials not configured. Service will not be able to create issues.")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    jira_configured = jira_client is not None
    openai_configured = OPENAI_API_KEY is not None
    
    # Try to get project info if Jira is configured
    project_info = None
    if jira_client:
        try:
            project_info = jira_client.get_project_issue_types(JIRA_PROJECT_KEY)
        except Exception as e:
            project_info = {"error": str(e)}
    
    return {
        "status": "healthy",
        "jira_configured": jira_configured,
        "jira_url": JIRA_URL if jira_configured else None,
        "openai_configured": openai_configured,
        "project_key": JIRA_PROJECT_KEY if jira_configured else None,
        "project_issue_types": [it.get("name") for it in project_info] if isinstance(project_info, list) else None,
        "project_error": project_info.get("error") if isinstance(project_info, dict) and "error" in project_info else None,
    }


@app.get("/jira/projects")
async def list_projects():
    """List all accessible Jira projects."""
    if not jira_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira client not configured"
        )
    
    try:
        url = f"{jira_client.base_url}/rest/api/3/project"
        response = jira_client.session.get(url)
        response.raise_for_status()
        projects = response.json()
        
        # Format response
        project_list = []
        for project in projects:
            project_list.append({
                "key": project.get("key"),
                "name": project.get("name"),
                "id": project.get("id"),
                "projectTypeKey": project.get("projectTypeKey"),
            })
        
        return {
            "projects": project_list,
            "count": len(project_list)
        }
    except Exception as e:
        logger.exception("Failed to list projects")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list projects: {str(e)}"
        )


@app.get("/jira/project/{project_key}/issue-types")
async def get_project_issue_types(project_key: str):
    """Get available issue types for a project."""
    if not jira_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira client not configured"
        )
    
    try:
        issue_types = jira_client.get_project_issue_types(project_key)
        return {
            "project_key": project_key,
            "issue_types": [
                {
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "description": it.get("description"),
                    "subtask": it.get("subtask", False),
                }
                for it in issue_types
            ]
        }
    except Exception as e:
        logger.exception(f"Failed to get issue types for project {project_key}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get issue types: {str(e)}"
        )


@app.post("/jira/create-tasks", response_model=CreateJiraTasksResponse)
async def create_jira_tasks(request: CreateJiraTasksRequest):
    """
    Create Jira tasks and subtasks from LLM response.
    
    The LLM response should contain:
    - epics: List of epics with tasks and subtasks
    - task_breakdown: List of parent tasks with subtasks (backward compatibility)
    - standalone_tasks: List of standalone tasks
    - action_items: List of standalone action items
    """
    if not jira_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira client not configured. Please set JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
        )
    
    try:
        result = create_jira_tasks_from_llm_response(
            jira_client=jira_client,
            llm_response=request.llm_response,
            meeting_summary=request.meeting_summary,
            create_epics=True,
            create_subtasks=request.create_subtasks,
        )
        return result
    except Exception as e:
        logger.exception("Error creating Jira tasks")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Jira tasks: {str(e)}"
        )


@app.post("/jira/process-meeting", response_model=CreateJiraTasksResponse)
async def process_meeting_and_create_tasks(request: ProcessMeetingRequest):
    """
    Process meeting data using OpenAI API and create Jira tasks, epics, and subtasks.
    
    This endpoint:
    1. Sends meeting transcript/summary to OpenAI API
    2. Gets structured response with epics, tasks, and subtasks
    3. Creates corresponding Jira issues
    """
    if not jira_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Jira client not configured. Please set JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
        )
    
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key not configured. Please set OPENAI_API_KEY."
        )
    
    if not request.meeting_transcript and not request.meeting_summary:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either meeting_transcript or meeting_summary must be provided."
        )
    
    try:
        # Call OpenAI to generate structured Jira tasks
        logger.info("Calling OpenAI API to generate Jira task structure...")
        llm_response = call_openai_for_jira_structure(
            meeting_transcript=request.meeting_transcript,
            meeting_summary=request.meeting_summary,
            create_epics=request.create_epics,
        )
        
        logger.info(f"Received LLM response with {len(llm_response.get('epics', []))} epics, "
                   f"{len(llm_response.get('standalone_tasks', []))} standalone tasks")
        
        # Create Jira tasks from LLM response
        result = create_jira_tasks_from_llm_response(
            jira_client=jira_client,
            llm_response=llm_response,
            meeting_summary=request.meeting_summary,
            create_epics=request.create_epics,
            create_subtasks=request.create_subtasks,
        )
        
        return result
        
    except json.JSONDecodeError as e:
        logger.exception("Failed to parse LLM response as JSON")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse LLM response: {str(e)}"
        )
    except Exception as e:
        logger.exception("Error processing meeting and creating Jira tasks")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process meeting: {str(e)}"
        )




if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("JIRA_SERVICE_PORT", "8003"))
    uvicorn.run(app, host="0.0.0.0", port=port)

