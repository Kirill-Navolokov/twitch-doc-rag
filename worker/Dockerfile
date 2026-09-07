FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt

COPY shared /app/shared
RUN pip install --no-cache-dir -e /app/shared

COPY ruff.toml /app/ruff.toml
COPY worker /app/worker
COPY docs /app/docs

WORKDIR /app/worker

# Gossip and mingle declare transient non-exclusive queues, which RabbitMQ 4 refuses (the matching
# remote-control mailbox is disabled in settings.py).
CMD ["sh", "-c", "python manage.py migrate && exec celery -A worker worker --loglevel=info --without-gossip --without-mingle"]
