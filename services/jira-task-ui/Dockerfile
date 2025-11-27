FROM python:3.11-slim

WORKDIR /app

# Copy service code
COPY ./services/jira-task-ui/ /app/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8502

CMD ["streamlit", "run", "app.py", "--server.port=8502", "--server.address=0.0.0.0"]

