from shared.voyage import embed_query
from shared.weaviate_client import ensure_schema, hybrid_search

from retrieval.types import RetrievedChunk

DEFAULT_TOP_K = 7
DEFAULT_ALPHA = 0.5


def retrieve(
    question: str, top_k: int = DEFAULT_TOP_K, alpha: float = DEFAULT_ALPHA
) -> list[RetrievedChunk]:
    # Keeps a query against a Weaviate that has never been written to from failing on a missing
    # collection.
    ensure_schema()
    hits = hybrid_search(
        query_text=question,
        query_vector=embed_query(question),
        top_k=top_k,
        alpha=alpha,
    )
    return [
        RetrievedChunk(
            text=hit["text"],
            source_url=hit["source_url"],
            title=hit["title"],
            chunk_index=hit["chunk_index"],
            score=hit["score"],
        )
        for hit in hits
    ]
