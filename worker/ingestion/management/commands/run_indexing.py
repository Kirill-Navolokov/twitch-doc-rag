from django.core.management.base import BaseCommand
from shared.models import Chunk

from ingestion.tasks import index_chunks


class Command(BaseCommand):
    help = "Queue Weaviate indexing for every document that still has unindexed chunks."

    def handle(self, *args: str, **options: object) -> None:
        # order_by() clears Chunk's default chunk_index ordering, which would otherwise join the
        # DISTINCT key and yield one row per chunk instead of one per document.
        pending = list(
            Chunk.objects.filter(indexed_at__isnull=True)
            .order_by()
            .values_list("document_id", flat=True)
            .distinct()
        )
        for document_id in pending:
            index_chunks.delay(document_id=str(document_id))
        self.stdout.write(f"Queued indexing for {len(pending)} documents")
