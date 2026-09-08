import functools
import logging
import time

import voyageai
from django.conf import settings
from voyageai.error import RateLimitError, Timeout

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "voyage-3.5"
MAX_BATCH_SIZE = voyageai.VOYAGE_EMBED_BATCH_SIZE
MAX_RETRIES = 3


@functools.cache
def _client() -> voyageai.Client:
    return voyageai.Client(api_key=settings.VOYAGE_API_KEY)


def _call_voyage(texts: list[str], input_type: str) -> list[list[float]]:
    return _client().embed(texts, model=EMBEDDING_MODEL, input_type=input_type).embeddings


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    for attempt in range(MAX_RETRIES):
        try:
            return _call_voyage(texts, input_type)
        except (RateLimitError, Timeout) as exc:
            delay = 2 ** (attempt + 1)
            logger.warning(
                "voyage embed input_type=%s attempt=%d retrying_in=%ds reason=%s",
                input_type,
                attempt + 1,
                delay,
                exc,
            )
            time.sleep(delay)
    return _call_voyage(texts, input_type)


def embed_documents(texts: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), MAX_BATCH_SIZE):
        embeddings.extend(_embed(texts[start : start + MAX_BATCH_SIZE], "document"))
    return embeddings


def embed_query(text: str) -> list[float]:
    return _embed([text], "query")[0]


def count_tokens(text: str) -> int:
    return _client().count_tokens([text], model=EMBEDDING_MODEL)
