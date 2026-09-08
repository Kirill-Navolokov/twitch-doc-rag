FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY worker/requirements.txt /app/worker/requirements.txt
RUN pip install --no-cache-dir -r /app/worker/requirements.txt

COPY shared /app/shared
RUN pip install --no-cache-dir -e /app/shared

# voyage-3.5's tokenizer (used for the chunk-size cap) is pulled from the HuggingFace hub on first
# use. Bake it into the image and pin the hub offline so chunking never makes a network call.
RUN python -c "import voyageai; voyageai.Client().tokenizer('voyage-3.5')"
ENV HF_HUB_OFFLINE=1

COPY ruff.toml /app/ruff.toml
COPY worker /app/worker
COPY docs /app/docs

WORKDIR /app/worker

# Gossip and mingle declare transient non-exclusive queues, which RabbitMQ 4 refuses (the matching
# remote-control mailbox is disabled in settings.py).
CMD ["sh", "-c", "python manage.py migrate && exec celery -A worker worker --loglevel=info --without-gossip --without-mingle"]
