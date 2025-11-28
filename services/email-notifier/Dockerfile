FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/email-notifier/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/email-notifier/ .
COPY libs/shared-models/ /app/libs/shared-models/

# Set Python path
ENV PYTHONPATH=/app:/app/libs/shared-models

CMD ["python", "main.py"]

