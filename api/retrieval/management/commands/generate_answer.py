from argparse import ArgumentParser

from django.core.management.base import BaseCommand
from shared.weaviate_client import close_client

from retrieval.generation import generate, select_model
from retrieval.service import retrieve
from retrieval.types import TaskDescriptor


class Command(BaseCommand):
    help = "Answer a question from the indexed docs, printing the chunks it was grounded in."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("question")
        parser.add_argument("--stream", action="store_true")

    def handle(self, *args: str, **options: str | bool) -> None:
        try:
            question = options["question"]
            chunks = retrieve(question)
            result = generate(
                select_model(TaskDescriptor()), question, chunks, stream=options["stream"]
            )
            for citation in result.citations:
                self.stdout.write(
                    f"{citation.score:.4f}  {citation.title} "
                    f"#{citation.chunk_index}  {citation.source_url}"
                )
            if result.token_stream is None:
                self.stdout.write(result.text)
            else:
                for token in result.token_stream:
                    # Unbuffered, so the terminal shows the answer building up token by token.
                    self.stdout.write(token, ending="")
                    self.stdout.flush()
                self.stdout.write("")
        finally:
            close_client()
