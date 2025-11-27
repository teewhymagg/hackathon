FROM python:3.11-slim

WORKDIR /app

COPY ./libs/shared-models /app/libs/shared-models
RUN pip install --no-cache-dir /app/libs/shared-models

COPY ./services/meeting-insights-ui/ /app/

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

