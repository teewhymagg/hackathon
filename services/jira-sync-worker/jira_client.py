"""Jira API Client with rate limiting and error handling"""
import logging
import time
from typing import Dict, Any, Optional, List
from jira import JIRA, JIRAError
from config import (
    JIRA_BASE_URL,
    JIRA_USER_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT_KEY,
    JIRA_RETRY_MAX_ATTEMPTS,
    JIRA_RETRY_BACKOFF_BASE,
    DRY_RUN,
)

logger = logging.getLogger(__name__)


class JiraClient:
    """Wrapper around Jira API client with retry logic and rate limiting"""

    def __init__(self):
        if DRY_RUN:
            logger.info("DRY_RUN mode enabled - Jira API calls will be logged but not executed")
            self.jira = None
        else:
            self.jira = JIRA(
                server=JIRA_BASE_URL,
                basic_auth=(JIRA_USER_EMAIL, JIRA_API_TOKEN),
                options={"verify": True, "timeout": 30},
                max_retries=0,  # We handle retries ourselves
            )
        self._user_cache: Dict[str, Optional[str]] = {}  # name -> accountId

    def _retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry"""
        for attempt in range(JIRA_RETRY_MAX_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except JIRAError as e:
                if e.status_code >= 500 and attempt < JIRA_RETRY_MAX_ATTEMPTS - 1:
                    wait_time = JIRA_RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"Jira server error {e.status_code}, retrying in {wait_time}s... (attempt {attempt + 1}/{JIRA_RETRY_MAX_ATTEMPTS})"
                    )
                    time.sleep(wait_time)
                else:
                    raise
        raise JIRAError("Failed after retries")

    def find_user_by_name(self, name: str) -> Optional[str]:
        """
        Find Jira user accountId by display name.
        Uses caching to avoid repeated API calls.
        """
        if name in self._user_cache:
            return self._user_cache[name]

        if DRY_RUN:
            logger.info(f"[DRY_RUN] Would search for user: {name}")
            self._user_cache[name] = None
            return None

        try:
            users = self.jira.search_users(query=name, maxResults=1)
            if users:
                account_id = users[0].accountId
                self._user_cache[name] = account_id
                logger.debug(f"Found Jira user '{name}' -> accountId: {account_id}")
                return account_id
            else:
                logger.warning(f"User '{name}' not found in Jira")
                self._user_cache[name] = None
                return None
        except JIRAError as e:
            logger.error(f"Error searching for user '{name}': {e}")
            self._user_cache[name] = None
            return None

    def create_issue(
        self,
        summary: str,
        description: str,
        issue_type: str,
        assignee_account_id: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a Jira issue.
        Returns dict with 'key' and 'id' on success, None on failure.
        """
        fields = {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }

        if assignee_account_id:
            fields["assignee"] = {"accountId": assignee_account_id}

        if due_date:
            fields["duedate"] = due_date

        if priority:
            fields["priority"] = {"name": priority}

        if labels:
            fields["labels"] = labels

        if DRY_RUN:
            logger.info(f"[DRY_RUN] Would create issue: {fields}")
            return {"key": "DRY-RUN-1", "id": "dry-run-1"}

        try:
            issue = self._retry_with_backoff(
                self.jira.create_issue, fields=fields, prefetch=False
            )
            logger.info(f"Created Jira issue: {issue.key}")
            return {"key": issue.key, "id": issue.id}
        except JIRAError as e:
            logger.error(f"Failed to create Jira issue: {e.status_code} - {e.text}")
            return None

    def create_issues_bulk(self, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Bulk create multiple issues.
        Returns list of results, each with 'issue' (key/id) or 'errors'.
        """
        if DRY_RUN:
            logger.info(f"[DRY_RUN] Would bulk create {len(issues)} issues")
            return [
                {"issue": {"key": f"DRY-RUN-{i+1}", "id": f"dry-run-{i+1}"}}
                for i in range(len(issues))
            ]

        try:
            results = self._retry_with_backoff(
                self.jira.create_issues, field_list=issues
            )
            for i, result in enumerate(results):
                if "issue" in result:
                    logger.info(f"Created issue: {result['issue']['key']}")
                elif "errors" in result:
                    logger.error(f"Failed to create issue {i+1}: {result['errors']}")
            return results
        except JIRAError as e:
            logger.error(f"Bulk create failed: {e.status_code} - {e.text}")
            return [{"errors": str(e)} for _ in issues]

    def add_comment(self, issue_key: str, comment: str) -> bool:
        """Add a comment to a Jira issue"""
        if DRY_RUN:
            logger.info(f"[DRY_RUN] Would add comment to {issue_key}: {comment[:50]}...")
            return True

        try:
            issue = self.jira.issue(issue_key)
            self.jira.add_comment(issue, comment)
            logger.debug(f"Added comment to {issue_key}")
            return True
        except JIRAError as e:
            logger.error(f"Failed to add comment to {issue_key}: {e}")
            return False

