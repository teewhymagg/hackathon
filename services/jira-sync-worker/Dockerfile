FROM python:3.11-slim

WORKDIR /app

# Copy and install shared models library first
COPY ./libs/shared-models /app/libs/shared-models
RUN pip install --no-cache-dir /app/libs/shared-models

# Copy worker code
COPY ./services/jira-sync-worker/ /app/

# Install service-specific dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run API server with background worker (supports both HTTP triggers and polling)
CMD ["python", "run_api.py"]

