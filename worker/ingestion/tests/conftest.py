import json
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytest_django.fixtures import SettingsWrapper

from shared import voyage

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
