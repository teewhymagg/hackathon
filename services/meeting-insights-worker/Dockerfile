FROM python:3.11-slim

WORKDIR /app

# Copy and install shared models library first (ensures pgvector + SQLAlchemy stack)
COPY ./libs/shared-models /app/libs/shared-models
RUN pip install --no-cache-dir /app/libs/shared-models

# Copy worker code
COPY ./services/meeting-insights-worker/ /app/

# Install service-specific dependencies
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "run_worker.py"]

