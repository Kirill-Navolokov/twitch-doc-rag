from django.core.management.base import BaseCommand
from django.db.models import F
from shared.models import Document

from ingestion.tasks import chunk_document


class Command(BaseCommand):
    help = "Queue chunking and embedding for every document whose text changed since last chunked."

    def handle(self, *args: str, **options: object) -> None:
        pending = list(
            Document.objects.exclude(content_hash=F("chunked_content_hash")).values_list(
                "id", flat=True
            )
        )
        for document_id in pending:
            chunk_document.delay(document_id=str(document_id))
        self.stdout.write(f"Queued chunking for {len(pending)} documents")
