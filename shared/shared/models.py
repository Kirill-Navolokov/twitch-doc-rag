import uuid

from django.contrib.postgres.fields import ArrayField
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
    # Equal to content_hash once the current text has been chunked and embedded; any difference
    # (including the empty initial value) marks the document as pending chunking.
    chunked_content_hash = models.CharField(max_length=64, blank=True, default="")
    fetched_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=FetchStatus.choices)

    def __str__(self) -> str:
        return self.source_url


class Chunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField()
    text = models.TextField()
    # Plain Postgres array rather than pgvector: similarity search happens in Weaviate, so this
    # table only stages embeddings on their way there.
    embedding = ArrayField(models.FloatField(), size=1024)
    created_at = models.DateTimeField(auto_now_add=True)
    # Null until this chunk has been confirmed written to Weaviate; chunking recreates every chunk
    # row on reprocess, so a reprocessed document's chunks are automatically eligible again.
    indexed_at = models.DateTimeField(null=True, blank=True, default=None)

    class Meta:
        ordering = ["chunk_index"]

    def __str__(self) -> str:
        return f"{self.document_id}#{self.chunk_index}"


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
