from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from retrieval import generation

EMBEDDING_DIMENSIONS = 1024


# Autouse so no test can reach Voyage AI, Weaviate or Groq over the network.
@pytest.fixture(autouse=True)
def embed_question() -> Iterator[MagicMock]:
    with patch("retrieval.service.embed_query", return_value=[0.5] * EMBEDDING_DIMENSIONS) as mock:
        yield mock


@pytest.fixture(autouse=True)
def ensure_schema() -> Iterator[MagicMock]:
    with patch("retrieval.service.ensure_schema") as mock:
        yield mock


@pytest.fixture(autouse=True)
def search() -> Iterator[MagicMock]:
    with patch("retrieval.service.hybrid_search", return_value=[]) as mock:
        yield mock


@pytest.fixture(autouse=True)
def groq_client() -> Iterator[MagicMock]:
    generation._client.cache_clear()
    with patch("retrieval.generation.Groq") as client_class:
        yield client_class.return_value
    generation._client.cache_clear()


@pytest.fixture(autouse=True)
def groq_sleep() -> Iterator[MagicMock]:
    with patch("retrieval.generation.time.sleep") as mock:
        yield mock
