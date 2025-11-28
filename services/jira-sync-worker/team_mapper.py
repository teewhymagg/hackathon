"""Team member name to Jira accountId mapping"""
import logging
import re
from typing import Dict, Optional
from config import TEAM_ROSTER_PATH

logger = logging.getLogger(__name__)

# Simple in-memory mapping: name -> jira_account_id
# Format: Name — Role — Responsibilities | jira_account_id:xxxxx
# Example: Анна Ким — Продакт-оунер — ... | jira_account_id:5d1234567890abcdef123456

_team_mapping: Dict[str, Optional[str]] = {}


def load_team_mapping() -> Dict[str, Optional[str]]:
    """
    Load team roster and extract Jira account IDs if present.
    Format: Name — Role — ... | jira_account_id:xxxxx
    Returns dict mapping name -> accountId (or None if not found)
    """
    global _team_mapping
    if _team_mapping:
        return _team_mapping

    try:
        with open(TEAM_ROSTER_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse: Name — Role — ... | jira_account_id:xxxxx
            # Or just: Name — Role — ...
            parts = line.split("|")
            name_part = parts[0].strip()
            name_match = re.match(r"^([^—]+)", name_part)
            if name_match:
                name = name_match.group(1).strip()

                # Check for jira_account_id in second part
                jira_account_id = None
                if len(parts) > 1:
                    jira_part = parts[1].strip()
                    account_id_match = re.search(r"jira_account_id:(\S+)", jira_part)
                    if account_id_match:
                        jira_account_id = account_id_match.group(1)

                _team_mapping[name] = jira_account_id
                if jira_account_id:
                    logger.debug(f"Loaded team member: {name} -> {jira_account_id}")
                else:
                    logger.debug(f"Loaded team member: {name} -> (no Jira ID)")

        logger.info(f"Loaded {len(_team_mapping)} team members from roster")
        return _team_mapping
    except FileNotFoundError:
        logger.warning(f"Team roster file not found: {TEAM_ROSTER_PATH}")
        return {}
    except Exception as e:
        logger.error(f"Error loading team roster: {e}")
        return {}


def get_jira_account_id(name: str) -> Optional[str]:
    """Get Jira accountId for a team member name"""
    mapping = load_team_mapping()
    return mapping.get(name)

