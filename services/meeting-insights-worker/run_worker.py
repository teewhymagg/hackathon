"""
Entry point that runs both the worker loop and the RAG API server.
"""
import asyncio
import multiprocessing
import os
import sys
import uvicorn

from main import main as worker_main
from rag_api import app as rag_app


def run_worker():
    """Run the worker loop."""
    worker_main()


def run_api():
    """Run the RAG API server."""
    port = int(os.environ.get("RAG_API_PORT", "8002"))
    uvicorn.run(rag_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    # Run worker in a separate process
    worker_process = multiprocessing.Process(target=run_worker, daemon=True)
    worker_process.start()
    
    # Run API in main process
    run_api()

