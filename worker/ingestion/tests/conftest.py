import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytest_django.fixtures import SettingsWrapper
from weaviate.classes.data import DataObject
from weaviate.collections.classes.filters import _FilterValue

from shared import voyage, weaviate_client

EMBEDDING_DIMENSIONS = 1024

PAGE_TEMPLATE = """<html><head><title>{title}</title></head><body><article>
<h1>{title}</h1>
<p>Authenticating a request against the Twitch Helix API requires a client id header as well
as a bearer token issued for the application making the call.</p>
<p>Responses are paginated, so a caller keeps sending the cursor from the previous response
until the API stops returning one for the requested resource.</p>
</article></body></html>"""


def page_html(title: str) -> str:
    return PAGE_TEMPLATE.format(title=title)


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def responder(pages: dict[str, str | Exception]) -> Callable[..., FakeResponse]:
    def get(url: str, **kwargs: object) -> FakeResponse:
        page = pages[url]
        if isinstance(page, Exception):
            raise page
        return FakeResponse(page)

    return get


@pytest.fixture
def url_list(tmp_path: Path, settings: SettingsWrapper) -> Callable[[list[str]], Path]:
    def write(urls: list[str]) -> Path:
        path = tmp_path / "doc_urls.json"
        path.write_text(json.dumps(urls))
        settings.DOC_URLS_PATH = path
        return path

    return write


@pytest.fixture
def sleep() -> Iterator[MagicMock]:
    with patch("ingestion.tasks.time.sleep") as mock:
        yield mock


@pytest.fixture
def http_get() -> Iterator[MagicMock]:
    with patch("ingestion.tasks.requests.get") as mock:
        yield mock


def fake_embeddings(texts: list[str]) -> list[list[float]]:
    return [[float(len(text))] * EMBEDDING_DIMENSIONS for text in texts]


@pytest.fixture
def embed() -> Iterator[MagicMock]:
    with patch("ingestion.tasks.embed_documents", side_effect=fake_embeddings) as mock:
        yield mock


# Autouse so no test can reach the Celery broker: run_ingestion() chains chunking per document.
@pytest.fixture(autouse=True)
def queue_chunking() -> Iterator[MagicMock]:
    with patch("ingestion.tasks.chunk_document.delay") as mock:
        yield mock


# Autouse for the same reason: chunk_document() chains indexing per document.
@pytest.fixture(autouse=True)
def queue_indexing() -> Iterator[MagicMock]:
    with patch("ingestion.tasks.index_chunks.delay") as mock:
        yield mock


@dataclass(frozen=True)
class WeaviateIndexMocks:
    ensure_schema: MagicMock
    delete_document: MagicMock
    insert_chunks: MagicMock


@pytest.fixture
def weaviate_index() -> Iterator[WeaviateIndexMocks]:
    with (
        patch("ingestion.tasks.ensure_schema") as ensure,
        patch("ingestion.tasks.delete_document") as delete,
        patch("ingestion.tasks.insert_chunks") as insert,
    ):
        yield WeaviateIndexMocks(ensure_schema=ensure, delete_document=delete, insert_chunks=insert)


@pytest.fixture
def weaviate_connection() -> Iterator[MagicMock]:
    weaviate_client._client.cache_clear()
    with patch("shared.weaviate_client.weaviate.connect_to_custom") as connect:
        yield connect.return_value
    weaviate_client._client.cache_clear()


@dataclass(frozen=True)
class IndexedObject:
    document_id: str
    chunk_index: int
    text: str
    source_url: str
    title: str
    vector: list[float]


@dataclass(frozen=True)
class FakeBatchReturn:
    has_errors: bool
    errors: dict[int, str]


class FakeCollection:
    """In-memory DocChunk stand-in, so tests can assert what indexing actually left behind."""

    def __init__(self) -> None:
        self.objects: list[IndexedObject] = []
        self.rejected_indexes: set[int] = set()

    def insert_many(self, objects: list[DataObject]) -> FakeBatchReturn:
        for index, obj in enumerate(objects):
            if index not in self.rejected_indexes:
                self.objects.append(IndexedObject(vector=obj.vector, **obj.properties))
        errors = dict.fromkeys(self.rejected_indexes, "rejected by weaviate")
        return FakeBatchReturn(has_errors=bool(errors), errors=errors)

    def delete_many(self, where: _FilterValue) -> None:
        self.objects = [obj for obj in self.objects if obj.document_id != where.value]


@pytest.fixture
def weaviate_store(weaviate_connection: MagicMock) -> FakeCollection:
    collection = FakeCollection()
    weaviate_connection.collections.exists.return_value = True
    data = weaviate_connection.collections.get.return_value.data
    data.insert_many.side_effect = collection.insert_many
    data.delete_many.side_effect = collection.delete_many
    return collection


@pytest.fixture
def voyage_client() -> Iterator[MagicMock]:
    voyage._client.cache_clear()
    with patch("shared.voyage.voyageai.Client") as client_class:
        yield client_class.return_value
    voyage._client.cache_clear()


@pytest.fixture
def voyage_sleep() -> Iterator[MagicMock]:
    with patch("shared.voyage.time.sleep") as mock:
        yield mock
