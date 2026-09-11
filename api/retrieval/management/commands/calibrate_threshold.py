import json
import time
from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand
from shared.weaviate_client import close_client

from retrieval.service import retrieve

# Voyage's free tier drops to 3 requests/minute without a payment method on file (see
# shared/shared/voyage.py's retry budget, which can't absorb a wait that long). One embed_query()
# call per question means back-to-back calibration runs hit that ceiling past the 3rd question, so
# space calls at the safe boundary (60s / 3 = 20s) rather than let the retry loop take the hit.
EMBED_RATE_LIMIT_DELAY_SECONDS = 20


@dataclass(frozen=True)
class ScoredQuestion:
    question: str
    top_score: float | None


def _sort_key(scored: ScoredQuestion) -> float:
    # A question that retrieved nothing sorts below every real score, which is never negative.
    return -1.0 if scored.top_score is None else scored.top_score


class Command(BaseCommand):
    help = "Report the top retrieval score per calibration question, grouped by expected label."

    def handle(self, *args: str, **options: object) -> None:
        entries: list[dict[str, str]] = json.loads(
            settings.CALIBRATION_QUESTIONS_PATH.read_text()
        )
        if not entries:
            self.stdout.write(
                f"No calibration questions configured in {settings.CALIBRATION_QUESTIONS_PATH}"
            )
            return

        try:
            by_label: dict[str, list[ScoredQuestion]] = defaultdict(list)
            for index, entry in enumerate(entries):
                if index > 0:
                    time.sleep(EMBED_RATE_LIMIT_DELAY_SECONDS)
                chunks = retrieve(entry["question"])
                top_score = max((chunk.score for chunk in chunks), default=None)
                by_label[entry["expected"]].append(ScoredQuestion(entry["question"], top_score))

            for label in sorted(by_label):
                self.stdout.write(label)
                for scored in sorted(by_label[label], key=_sort_key, reverse=True):
                    score = "none" if scored.top_score is None else f"{scored.top_score:.4f}"
                    self.stdout.write(f"  {score:>6}  {scored.question}")
        finally:
            close_client()
