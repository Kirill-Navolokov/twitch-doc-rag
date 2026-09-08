import hashlib
import uuid
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from django.core.management import call_command
from django.utils import timezone
from shared.models import Chunk, Document, DocumentProcessingLog, FetchStatus
from voyageai.error import RateLimitError

from ingestion.tasks import chunk_document, run_ingestion
from ingestion.tests.conftest import EMBEDDING_DIMENSIONS, page_html, responder

API_URL = "https://dev.twitch.tv/docs/api/"
EVENTSUB_URL = "https://dev.twitch.tv/docs/eventsub/"
BROKEN_URL = "https://dev.twitch.tv/docs/does-not-exist/"

pytestmark = pytest.mark.django_db

UrlList = Callable[[list[str]], Path]

MARKDOWN = "# Twitch API\n\n## Get Streams\n\nReturns streams.\n\n## Get Users\n\nReturns users."


def make_document(text: str = MARKDOWN, url: str = API_URL) -> Document:
    return Document.objects.create(
        source_url=url,
        title="API",
        raw_text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        fetched_at=timezone.now(),
        status=FetchStatus.SUCCESS,
    )


def make_log(document: Document, fetch_duration_ms: int = 120) -> DocumentProcessingLog:
    return DocumentProcessingLog.objects.create(
        ingestion_run_id=uuid.uuid4(),
        url=document.source_url,
        fetch_duration_ms=fetch_duration_ms,
        fetch_status=FetchStatus.SUCCESS,
    )


def test_stores_one_chunk_record_per_chunk_with_an_embedding(embed: MagicMock) -> None:
    document = make_document()

    assert chunk_document(document_id=str(document.id)) == 3

    chunks = list(Chunk.objects.filter(document=document))
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert chunks[0].text.startswith("# Twitch API")
    assert chunks[1].text.startswith("## Get Streams")
    for chunk in chunks:
        assert len(chunk.embedding) == EMBEDDING_DIMENSIONS
        assert chunk.created_at is not None


def test_embeds_every_chunk_in_one_batched_call(embed: MagicMock) -> None:
    document = make_document()

    chunk_document(document_id=str(document.id))

    embed.assert_called_once()
    assert len(embed.call_args.args[0]) == 3


def test_document_already_chunked_at_this_hash_is_skipped(embed: MagicMock) -> None:
    document = make_document()
    chunk_document(document_id=str(document.id))
    embed.reset_mock()

    assert chunk_document(document_id=str(document.id)) == 0
    assert embed.call_count == 0


def test_chunked_content_hash_is_set_once_chunking_and_embedding_succeed(
    embed: MagicMock,
) -> None:
    document = make_document()

    chunk_document(document_id=str(document.id))

    document.refresh_from_db()
    assert document.chunked_content_hash == document.content_hash


def test_embedding_failure_leaves_chunked_content_hash_stale(embed: MagicMock) -> None:
    document = make_document()
    embed.side_effect = RateLimitError("rate limited")

    with pytest.raises(RateLimitError):
        chunk_document(document_id=str(document.id))

    document.refresh_from_db()
    assert document.chunked_content_hash == ""
    assert Chunk.objects.count() == 0


def test_reprocessing_replaces_chunks_instead_of_duplicating(embed: MagicMock) -> None:
    document = make_document()
    chunk_document(document_id=str(document.id))
    original_ids = set(Chunk.objects.values_list("id", flat=True))

    document.raw_text = "# Twitch API\n\n## Get Streams\n\nReturns streams."
    document.content_hash = hashlib.sha256(document.raw_text.encode()).hexdigest()
    document.save(update_fields=["raw_text", "content_hash"])
    chunk_document(document_id=str(document.id))

    chunks = list(Chunk.objects.filter(document=document))
    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert original_ids.isdisjoint({chunk.id for chunk in chunks})


def test_fills_in_processing_log_durations_and_chunk_count(embed: MagicMock) -> None:
    document = make_document()
    log = make_log(document, fetch_duration_ms=120)

    chunk_document(document_id=str(document.id), document_processing_log_id=str(log.id))

    log.refresh_from_db()
    assert log.chunk_count == 3
    assert log.chunk_duration_ms >= 0
    assert log.embed_duration_ms >= 0
    assert log.total_duration_ms == 120 + log.chunk_duration_ms + log.embed_duration_ms


def test_processing_log_is_untouched_when_no_log_id_is_given(embed: MagicMock) -> None:
    document = make_document()
    log = make_log(document)

    chunk_document(document_id=str(document.id))

    log.refresh_from_db()
    assert log.chunk_count is None
    assert log.chunk_duration_ms is None
    assert log.total_duration_ms is None


def test_run_ingestion_chains_chunking_for_each_successful_url(
    url_list: UrlList,
    http_get: MagicMock,
    sleep: MagicMock,
    queue_chunking: MagicMock,
) -> None:
    url_list([API_URL, BROKEN_URL, EVENTSUB_URL])
    http_get.side_effect = responder(
        {
            API_URL: page_html("API"),
            BROKEN_URL: requests.ConnectionError("boom"),
            EVENTSUB_URL: page_html("EventSub"),
        }
    )

    run_ingestion()

    chained = {call.kwargs["document_id"] for call in queue_chunking.call_args_list}
    assert chained == {
        str(Document.objects.get(source_url=API_URL).id),
        str(Document.objects.get(source_url=EVENTSUB_URL).id),
    }
    logs = {log.url: log for log in DocumentProcessingLog.objects.all()}
    for call in queue_chunking.call_args_list:
        assert call.kwargs["document_processing_log_id"] in {str(log.id) for log in logs.values()}


def test_run_chunking_command_queues_only_documents_needing_work(
    queue_chunking: MagicMock,
) -> None:
    pending = make_document(url=API_URL)
    chunked = make_document(url=EVENTSUB_URL)
    chunked.chunked_content_hash = chunked.content_hash
    chunked.save(update_fields=["chunked_content_hash"])

    call_command("run_chunking")

    queue_chunking.assert_called_once_with(document_id=str(pending.id))
