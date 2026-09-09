FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

COPY shared /app/shared
RUN pip install --no-cache-dir -e /app/shared

COPY ruff.toml /app/ruff.toml
COPY api /app/api

WORKDIR /app/api

# No migrate step: worker is the sole owner of shared's migration history.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
