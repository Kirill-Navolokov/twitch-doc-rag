from django.core.management.base import BaseCommand

from ingestion.tasks import run_ingestion


class Command(BaseCommand):
    help = "Queue the doc ingestion Celery task for the URLs in docs/doc_urls.json."

    def handle(self, *args: str, **options: object) -> None:
        result = run_ingestion.delay()
        self.stdout.write(f"Queued ingestion task {result.id}")
