from unittest.mock import MagicMock

import pytest
from shared.weaviate_client import (
    COLLECTION_NAME,
    BatchInsertError,
    ChunkForIndex,
    close_client,
    delete_document,
    ensure_schema,
    hybrid_search,
    insert_chunks,
)
from weaviate.classes.config import DataType
from weaviate.classes.query import HybridFusion

DOCUMENT_ID = "0f6f9d0c-6f2d-4c65-9f0e-4b1f0a6d9d11"


def make_chunk(chunk_index: int = 0, text: str = "client id header") -> ChunkForIndex:
    return ChunkForIndex(
        document_id=DOCUMENT_ID,
        chunk_index=chunk_index,
        text=text,
        source_url="https://dev.twitch.tv/docs/api/",
        title="API",
        embedding=[0.25] * 1024,
    )


def make_hit(text: str, chunk_index: int, score: float) -> MagicMock:
    hit = MagicMock()
    hit.properties = {
        "text": text,
        "source_url": "https://dev.twitch.tv/docs/api/",
        "title": "API",
        "chunk_index": chunk_index,
    }
    hit.metadata.score = score
    return hit


def test_missing_collection_is_created_without_a_vectorizer(
    weaviate_connection: MagicMock,
) -> None:
    weaviate_connection.collections.exists.return_value = False

    ensure_schema()

    name, kwargs = (
        weaviate_connection.collections.create.call_args.args[0],
        weaviate_connection.collections.create.call_args.kwargs,
    )
    assert name == COLLECTION_NAME
    assert kwargs["vector_config"].vectorizer.vectorizer.value == "none"
    properties = {prop.name: prop.dataType for prop in kwargs["properties"]}
    assert properties == {
        "text": DataType.TEXT,
        "source_url": DataType.TEXT,
        "title": DataType.TEXT,
        "chunk_index": DataType.INT,
        "document_id": DataType.TEXT,
    }


def test_ensure_schema_is_idempotent(weaviate_connection: MagicMock) -> None:
    weaviate_connection.collections.exists.return_value = True

    ensure_schema()
    ensure_schema()

    weaviate_connection.collections.create.assert_not_called()


def test_closing_disconnects_the_cached_client(weaviate_connection: MagicMock) -> None:
    ensure_schema()

    close_client()

    weaviate_connection.close.assert_called_once_with()


def test_closing_is_a_no_op_when_nothing_ever_connected(weaviate_connection: MagicMock) -> None:
    close_client()

    weaviate_connection.close.assert_not_called()


def test_insert_sends_every_chunk_with_its_metadata_and_supplied_vector(
    weaviate_connection: MagicMock,
) -> None:
    collection = weaviate_connection.collections.get.return_value
    collection.data.insert_many.return_value.has_errors = False

    insert_chunks([make_chunk(0, "client id header"), make_chunk(1, "cursor pagination")])

    objects = collection.data.insert_many.call_args.args[0]
    assert [obj.properties["text"] for obj in objects] == ["client id header", "cursor pagination"]
    assert [obj.properties["chunk_index"] for obj in objects] == [0, 1]
    assert {obj.properties["document_id"] for obj in objects} == {DOCUMENT_ID}
    assert objects[0].vector == [0.25] * 1024


def test_a_batch_reporting_per_object_errors_raises_even_though_the_call_returned(
    weaviate_connection: MagicMock,
) -> None:
    result = weaviate_connection.collections.get.return_value.data.insert_many.return_value
    result.has_errors = True
    result.errors = {1: "invalid integer property 'chunk_index'"}

    with pytest.raises(BatchInsertError):
        insert_chunks([make_chunk(0), make_chunk(1)])


def test_delete_targets_every_object_carrying_the_document_id(
    weaviate_connection: MagicMock,
) -> None:
    delete_document(DOCUMENT_ID)

    where = weaviate_connection.collections.get.return_value.data.delete_many.call_args.kwargs[
        "where"
    ]
    assert where.target == "document_id"
    assert where.value == DOCUMENT_ID


def test_hybrid_search_uses_relative_score_fusion_and_returns_scored_properties(
    weaviate_connection: MagicMock,
) -> None:
    query = weaviate_connection.collections.get.return_value.query
    query.hybrid.return_value.objects = [
        make_hit("client id header", 0, 1.0),
        make_hit("cursor pagination", 1, 0.42),
    ]

    hits = hybrid_search(
        query_text="how do I authenticate?", query_vector=[0.5] * 1024, top_k=7, alpha=0.5
    )

    kwargs = query.hybrid.call_args.kwargs
    assert kwargs["query"] == "how do I authenticate?"
    assert kwargs["vector"] == [0.5] * 1024
    assert kwargs["limit"] == 7
    assert kwargs["alpha"] == 0.5
    assert kwargs["fusion_type"] is HybridFusion.RELATIVE_SCORE
    assert [hit["text"] for hit in hits] == ["client id header", "cursor pagination"]
    assert [hit["score"] for hit in hits] == [1.0, 0.42]
    assert hits[0]["source_url"] == "https://dev.twitch.tv/docs/api/"
    assert hits[0]["title"] == "API"
    assert hits[1]["chunk_index"] == 1
