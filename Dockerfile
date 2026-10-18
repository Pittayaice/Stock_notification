FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run tells the app which port to listen on through $PORT
CMD exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}
