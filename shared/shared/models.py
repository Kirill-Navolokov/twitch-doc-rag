import uuid

from django.db import models


class FetchStatus(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_url = models.URLField(max_length=2048, unique=True)
    title = models.CharField(max_length=512, blank=True)
    raw_text = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    fetched_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=FetchStatus.choices)

    def __str__(self) -> str:
        return self.source_url


class DocumentProcessingLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Soft reference rather than a ForeignKey: IngestionRun is owned by the worker project, and a
    # cross-project FK would force `api` to install worker's app just to load shared's models.
    ingestion_run_id = models.UUIDField(db_index=True)
    url = models.URLField(max_length=2048)
    fetch_duration_ms = models.IntegerField()
    fetch_status = models.CharField(max_length=16, choices=FetchStatus.choices)
    chunk_duration_ms = models.IntegerField(null=True)
    chunk_count = models.IntegerField(null=True)
    embed_duration_ms = models.IntegerField(null=True)
    total_duration_ms = models.IntegerField(null=True)

    def __str__(self) -> str:
        return f"{self.url} ({self.fetch_status})"
