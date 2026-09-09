from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

EMBEDDING_DIMENSIONS = 1024


# Autouse so no test can reach Voyage AI or Weaviate over the network.
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
