"""HTTP API for triggering Jira sync"""
import logging
import os
import threading
from typing import Optional
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

from main import sync_meeting_by_id

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("jira_sync_api")

app = FastAPI(title="Jira Sync Worker API")


class JiraSyncTriggerRequest(BaseModel):
    meeting_id: int


@app.post("/trigger")
async def trigger_jira_sync(
    request: JiraSyncTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    HTTP endpoint to trigger Jira sync for a specific meeting.
    Called automatically by meeting-insights-worker after insights are generated.
    """
    logger.info(f"Received Jira sync trigger request for meeting {request.meeting_id}")
    
    # Run sync in background
    background_tasks.add_task(sync_meeting_to_jira_task, request.meeting_id)
    
    return {"status": "accepted", "message": f"Jira sync triggered for meeting {request.meeting_id}"}


def sync_meeting_to_jira_task(meeting_id: int):
    """Background task to sync a meeting to Jira"""
    try:
        success = sync_meeting_by_id(meeting_id)
        if success:
            logger.info(f"Successfully synced meeting {meeting_id} to Jira via trigger")
        else:
            logger.warning(f"Failed to sync meeting {meeting_id} to Jira via trigger")
    except Exception as e:
        logger.exception(f"Error syncing meeting {meeting_id} to Jira: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "jira-sync-worker"}

