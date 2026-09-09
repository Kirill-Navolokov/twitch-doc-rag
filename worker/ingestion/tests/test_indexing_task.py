import hashlib
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from shared.models import Chunk, Document, FetchStatus
from shared.weaviate_client import BatchInsertError

from ingestion.tasks import chunk_document, index_chunks
from ingestion.tests.conftest import EMBEDDING_DIMENSIONS, FakeCollection, WeaviateIndexMocks

API_URL = "https://dev.twitch.tv/docs/api/"
EVENTSUB_URL = "https://dev.twitch.tv/docs/eventsub/"

pytestmark = pytest.mark.django_db

MARKDOWN = "# Twitch API\n\n## Get Streams\n\nReturns streams.\n\n## Get Users\n\nReturns users."


def make_document(url: str = API_URL, title: str = "API", text: str = MARKDOWN) -> Document:
    return Document.objects.create(
        source_url=url,
        title=title,
        raw_text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        fetched_at=timezone.now(),
        status=FetchStatus.SUCCESS,
    )


def make_chunks(document: Document, texts: list[str]) -> list[Chunk]:
    return Chunk.objects.bulk_create(
        Chunk(
            document=document,
            chunk_index=index,
            text=text,
            embedding=[float(index)] * EMBEDDING_DIMENSIONS,
        )
        for index, text in enumerate(texts)
    )


def test_indexes_unindexed_chunks_with_their_document_metadata(
    weaviate_index: WeaviateIndexMocks,
) -> None:
    document = make_document()
    make_chunks(document, ["client id header", "cursor pagination"])

    assert index_chunks(document_id=str(document.id)) == 2

    indexed = weaviate_index.insert_chunks.call_args.args[0]
    assert [chunk.text for chunk in indexed] == ["client id header", "cursor pagination"]
    assert [chunk.chunk_index for chunk in indexed] == [0, 1]
    assert {chunk.document_id for chunk in indexed} == {str(document.id)}
    assert {chunk.source_url for chunk in indexed} == {API_URL}
    assert {chunk.title for chunk in indexed} == {"API"}
    assert indexed[1].embedding == [1.0] * EMBEDDING_DIMENSIONS


def test_indexed_at_is_set_only_after_the_weaviate_write_succeeds(
    weaviate_index: WeaviateIndexMocks,
) -> None:
    document = make_document()
    make_chunks(document, ["client id header", "cursor pagination"])

    index_chunks(document_id=str(document.id))

    assert Chunk.objects.filter(indexed_at__isnull=True).count() == 0


def test_schema_is_ensured_before_anything_is_written(
    weaviate_index: WeaviateIndexMocks,
) -> None:
    document = make_document()
    make_chunks(document, ["client id header"])

    index_chunks(document_id=str(document.id))

    weaviate_index.ensure_schema.assert_called_once_with()


def test_previous_objects_are_deleted_by_document_id_before_the_new_set_is_inserted(
    weaviate_index: WeaviateIndexMocks,
) -> None:
    document = make_document()
    make_chunks(document, ["old one", "old two"])
    index_chunks(document_id=str(document.id))

    Chunk.objects.filter(document=document).delete()
    make_chunks(document, ["new one"])
    weaviate_index.delete_document.reset_mock()
    weaviate_index.insert_chunks.reset_mock()

    assert index_chunks(document_id=str(document.id)) == 1

    weaviate_index.delete_document.assert_called_once_with(str(document.id))
    assert [chunk.text for chunk in weaviate_index.insert_chunks.call_args.args[0]] == ["new one"]


def test_reindexing_leaves_no_object_from_the_previous_chunk_set(
    weaviate_store: FakeCollection,
) -> None:
    document = make_document()
    other = make_document(url=EVENTSUB_URL, title="EventSub")
    make_chunks(document, ["old one", "old two"])
    make_chunks(other, ["untouched"])
    index_chunks(document_id=str(document.id))
    index_chunks(document_id=str(other.id))

    Chunk.objects.filter(document=document).delete()
    make_chunks(document, ["new one"])
    index_chunks(document_id=str(document.id))

    assert sorted(obj.text for obj in weaviate_store.objects) == ["new one", "untouched"]


def test_reprocessed_document_chunks_start_unindexed_again(embed: MagicMock) -> None:
    document = make_document()
    chunk_document(document_id=str(document.id))
    Chunk.objects.update(indexed_at=timezone.now())

    document.raw_text = "# Twitch API\n\n## Get Streams\n\nReturns streams."
    document.content_hash = hashlib.sha256(document.raw_text.encode()).hexdigest()
    document.save(update_fields=["raw_text", "content_hash"])
    chunk_document(document_id=str(document.id))

    assert Chunk.objects.filter(document=document).count() == 2
    assert Chunk.objects.filter(document=document, indexed_at__isnull=True).count() == 2


def test_second_run_for_a_fully_indexed_document_touches_nothing(
    weaviate_index: WeaviateIndexMocks,
) -> None:
    document = make_document()
    make_chunks(document, ["client id header", "cursor pagination"])
    index_chunks(document_id=str(document.id))
    indexed_at = {chunk.id: chunk.indexed_at for chunk in Chunk.objects.all()}
    weaviate_index.delete_document.reset_mock()
    weaviate_index.insert_chunks.reset_mock()

    assert index_chunks(document_id=str(document.id)) == 0

    weaviate_index.delete_document.assert_not_called()
    weaviate_index.insert_chunks.assert_not_called()
    assert {chunk.id: chunk.indexed_at for chunk in Chunk.objects.all()} == indexed_at


def test_second_run_leaves_the_documents_objects_in_place(
    weaviate_store: FakeCollection,
) -> None:
    document = make_document()
    make_chunks(document, ["client id header", "cursor pagination"])
    index_chunks(document_id=str(document.id))
    indexed = list(weaviate_store.objects)

    assert index_chunks(document_id=str(document.id)) == 0

    assert weaviate_store.objects == indexed


def test_a_partially_rejected_batch_fails_the_task_and_leaves_every_chunk_unindexed(
    weaviate_store: FakeCollection,
) -> None:
    document = make_document()
    make_chunks(document, ["client id header", "cursor pagination"])
    weaviate_store.rejected_indexes = {1}

    with pytest.raises(BatchInsertError):
        index_chunks(document_id=str(document.id))

    assert [obj.text for obj in weaviate_store.objects] == ["client id header"]
    assert Chunk.objects.filter(indexed_at__isnull=True).count() == 2


def test_a_weaviate_connection_failure_leaves_every_chunk_unindexed(
    weaviate_index: WeaviateIndexMocks,
) -> None:
    document = make_document()
    make_chunks(document, ["client id header"])
    weaviate_index.insert_chunks.side_effect = ConnectionError("weaviate unreachable")

    with pytest.raises(ConnectionError):
        index_chunks(document_id=str(document.id))

    assert Chunk.objects.filter(indexed_at__isnull=True).count() == 1


def test_indexing_never_re_embeds_through_voyage(weaviate_index: WeaviateIndexMocks) -> None:
    document = make_document()
    make_chunks(document, ["client id header"])

    with patch("shared.voyage._client") as voyage_client:
        index_chunks(document_id=str(document.id))

    voyage_client.assert_not_called()


def test_chunking_chains_indexing_for_the_document(
    embed: MagicMock, queue_indexing: MagicMock
) -> None:
    document = make_document()

    chunk_document(document_id=str(document.id))

    queue_indexing.assert_called_once_with(document_id=str(document.id))


def test_run_indexing_command_queues_each_document_with_unindexed_chunks_once(
    queue_indexing: MagicMock,
) -> None:
    pending = make_document()
    make_chunks(pending, ["one", "two", "three"])
    done = make_document(url=EVENTSUB_URL, title="EventSub")
    make_chunks(done, ["four"])
    Chunk.objects.filter(document=done).update(indexed_at=timezone.now())

    call_command("run_indexing")

    queue_indexing.assert_called_once_with(document_id=str(pending.id))
