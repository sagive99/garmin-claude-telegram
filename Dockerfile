FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .

# Cloud Run sends traffic to $PORT. concurrency=1 is set on the service, so a
# single worker is enough and keeps the daily Garmin pull from overlapping.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 120 app:app
