from argparse import ArgumentParser

from django.core.management.base import BaseCommand
from shared.weaviate_client import close_client

from retrieval.service import DEFAULT_ALPHA, DEFAULT_TOP_K, retrieve


class Command(BaseCommand):
    help = "Print the chunks a question retrieves, with their hybrid relevance scores."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("question")
        parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
        parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)

    def handle(self, *args: str, **options: str | int | float) -> None:
        try:
            chunks = retrieve(options["question"], top_k=options["top_k"], alpha=options["alpha"])
            for chunk in chunks:
                self.stdout.write(
                    f"{chunk.score:.4f}  {chunk.title} #{chunk.chunk_index}  {chunk.source_url}"
                )
                self.stdout.write(f"    {chunk.text[:300]}")
            self.stdout.write(f"Retrieved {len(chunks)} chunks")
        finally:
            close_client()
