FROM python:3.11-slim

WORKDIR /app

# Copy service code
COPY ./services/jira-integration/ /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]

