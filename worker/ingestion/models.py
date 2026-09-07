import uuid

from django.db import models


class IngestionRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True)
    total_links = models.IntegerField(default=0)
    succeeded = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)

    def __str__(self) -> str:
        return f"IngestionRun {self.id}"
