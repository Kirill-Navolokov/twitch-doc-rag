import functools
from dataclasses import dataclass
from typing import TypedDict
from urllib.parse import urlparse

import weaviate
from django.conf import settings
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter, HybridFusion, MetadataQuery

COLLECTION_NAME = "DocChunk"
# Weaviate serves the gRPC API the v4 client uses for batch writes and queries on a fixed second
# port alongside the HTTP one WEAVIATE_URL points at.
GRPC_PORT = 50051


@dataclass(frozen=True)
class ChunkForIndex:
    document_id: str
    chunk_index: int
    text: str
    source_url: str
    title: str
    embedding: list[float]


class SearchHit(TypedDict):
    text: str
    source_url: str
    title: str
    chunk_index: int
    score: float


class BatchInsertError(Exception):
    pass


@functools.cache
def _client() -> weaviate.WeaviateClient:
    url = urlparse(settings.WEAVIATE_URL)
    secure = url.scheme == "https"
    return weaviate.connect_to_custom(
        http_host=url.hostname,
        http_port=url.port,
        http_secure=secure,
        grpc_host=url.hostname,
        grpc_port=GRPC_PORT,
        grpc_secure=secure,
    )


# Only one-shot processes (management commands) call this, right before exiting — otherwise the
# cached client's connection is reported unclosed on teardown. Long-lived processes (the Celery
# worker, the API server) keep reusing their cached client for the life of the process.
def close_client() -> None:
    if _client.cache_info().currsize == 0:
        return
    _client().close()
    _client.cache_clear()


def ensure_schema() -> None:
    client = _client()
    if client.collections.exists(COLLECTION_NAME):
        return
    client.collections.create(
        COLLECTION_NAME,
        # Vectors are always supplied from Chunk.embedding — Weaviate must never embed anything.
        vector_config=Configure.Vectors.self_provided(),
        properties=[
            Property(name="text", data_type=DataType.TEXT),
            Property(name="source_url", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="chunk_index", data_type=DataType.INT),
            Property(name="document_id", data_type=DataType.TEXT),
        ],
    )


def delete_document(document_id: str) -> None:
    _client().collections.get(COLLECTION_NAME).data.delete_many(
        where=Filter.by_property("document_id").equal(document_id)
    )


def insert_chunks(chunks: list[ChunkForIndex]) -> None:
    result = (
        _client()
        .collections.get(COLLECTION_NAME)
        .data.insert_many(
            [
                DataObject(
                    properties={
                        "text": chunk.text,
                        "source_url": chunk.source_url,
                        "title": chunk.title,
                        "chunk_index": chunk.chunk_index,
                        "document_id": chunk.document_id,
                    },
                    vector=chunk.embedding,
                )
                for chunk in chunks
            ]
        )
    )
    # insert_many reports per-object rejections on the result instead of raising, so without this
    # check a partially written batch would look like a success and get marked indexed.
    if result.has_errors:
        raise BatchInsertError(
            f"{len(result.errors)} of {len(chunks)} objects rejected: {result.errors}"
        )


def hybrid_search(
    query_text: str, query_vector: list[float], top_k: int, alpha: float
) -> list[SearchHit]:
    response = (
        _client()
        .collections.get(COLLECTION_NAME)
        .query.hybrid(
            query=query_text,
            vector=query_vector,
            alpha=alpha,
            limit=top_k,
            fusion_type=HybridFusion.RELATIVE_SCORE,
            return_metadata=MetadataQuery(score=True),
        )
    )
    return [
        SearchHit(
            text=obj.properties["text"],
            source_url=obj.properties["source_url"],
            title=obj.properties["title"],
            chunk_index=obj.properties["chunk_index"],
            score=obj.metadata.score,
        )
        for obj in response.objects
    ]
