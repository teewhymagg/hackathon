"""Run Jira Sync Worker as FastAPI service with background polling"""
import logging
import os
import threading
import uvicorn
from api import app
from main import main as worker_main

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("jira_sync_runner")

# Start background worker thread
def start_worker():
    """Start the polling worker in a background thread"""
    logger.info("Starting background polling worker thread")
    worker_thread = threading.Thread(target=worker_main, daemon=True)
    worker_thread.start()
    return worker_thread

if __name__ == "__main__":
    # Start background worker
    start_worker()
    
    # Run FastAPI server
    port = int(os.environ.get("JIRA_SYNC_API_PORT", "8004"))
    logger.info(f"Starting Jira Sync Worker API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

