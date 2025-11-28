"""Configuration for Jira Sync Worker"""
import os
from typing import Optional
from openai import OpenAI

# Jira Connection
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "")

# Jira Issue Type Configuration
JIRA_ISSUE_TYPE_TASK = os.environ.get("JIRA_ISSUE_TYPE_TASK", "Task")
JIRA_ISSUE_TYPE_BLOCKER = os.environ.get("JIRA_ISSUE_TYPE_BLOCKER", "Task")
JIRA_ISSUE_TYPE_DEADLINE = os.environ.get("JIRA_ISSUE_TYPE_DEADLINE", "Task")
JIRA_ISSUE_TYPE_EPIC = os.environ.get("JIRA_ISSUE_TYPE_EPIC", "Epic")
JIRA_ISSUE_TYPE_FEATURE = os.environ.get("JIRA_ISSUE_TYPE_FEATURE", "Story")
JIRA_ISSUE_TYPE_BUG = os.environ.get("JIRA_ISSUE_TYPE_BUG", "Bug")

# Jira Labels
JIRA_LABEL_BLOCKER = os.environ.get("JIRA_LABEL_BLOCKER", "blocker")
JIRA_LABEL_DEADLINE = os.environ.get("JIRA_LABEL_DEADLINE", "deadline")
JIRA_LABEL_ACTION_ITEM = os.environ.get("JIRA_LABEL_ACTION_ITEM", "action-item")
JIRA_LABEL_MEETING = os.environ.get("JIRA_LABEL_MEETING", "meeting-generated")

# Priority Mapping (Russian -> Jira priority names)
PRIORITY_MAPPING = {
    "высокий": os.environ.get("JIRA_PRIORITY_HIGH", "High"),
    "средний": os.environ.get("JIRA_PRIORITY_MEDIUM", "Medium"),
    "низкий": os.environ.get("JIRA_PRIORITY_LOW", "Low"),
}

# Worker Configuration
POLL_INTERVAL = int(os.environ.get("JIRA_SYNC_POLL_INTERVAL", "60"))  # seconds
BATCH_SIZE = int(os.environ.get("JIRA_SYNC_BATCH_SIZE", "1"))
DRY_RUN = os.environ.get("JIRA_DRY_RUN", "false").lower() == "true"

# Team Roster Path (for name mapping)
TEAM_ROSTER_PATH = os.environ.get("TEAM_ROSTER_PATH", "/app/team_roster.txt")

# Database Configuration
DB_HOST = os.environ.get("DB_HOST", "postgres")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "hackathon_bot")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")

# Rate Limiting (Jira free tier: 500 requests per 10 minutes)
JIRA_RATE_LIMIT_REQUESTS = int(os.environ.get("JIRA_RATE_LIMIT_REQUESTS", "500"))
JIRA_RATE_LIMIT_WINDOW = int(os.environ.get("JIRA_RATE_LIMIT_WINDOW", "600"))  # 10 minutes
JIRA_RETRY_MAX_ATTEMPTS = int(os.environ.get("JIRA_RETRY_MAX_ATTEMPTS", "3"))
JIRA_RETRY_BACKOFF_BASE = float(os.environ.get("JIRA_RETRY_BACKOFF_BASE", "2.0"))

# OpenAI Configuration for Task Type Classification
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TASK_CLASSIFICATION_MODEL = os.environ.get("TASK_CLASSIFICATION_MODEL", "gpt-4o-mini")

# Initialize OpenAI client if API key is provided
openai_client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Validation
def validate_config() -> tuple[bool, Optional[str]]:
    """Validate required configuration"""
    if not JIRA_BASE_URL:
        return False, "JIRA_BASE_URL is required"
    if not JIRA_USER_EMAIL:
        return False, "JIRA_USER_EMAIL is required"
    if not JIRA_API_TOKEN:
        return False, "JIRA_API_TOKEN is required"
    if not JIRA_PROJECT_KEY:
        return False, "JIRA_PROJECT_KEY is required"
    return True, None

