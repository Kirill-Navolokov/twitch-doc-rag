from unittest.mock import MagicMock

from shared.weaviate_client import SearchHit

from retrieval.service import retrieve
from retrieval.tests.conftest import EMBEDDING_DIMENSIONS

QUESTION = "how do I authenticate a Twitch API request?"


def make_hit(text: str, chunk_index: int, score: float, title: str = "API") -> SearchHit:
    return SearchHit(
        text=text,
        source_url=f"https://dev.twitch.tv/docs/{title.lower()}/",
        title=title,
        chunk_index=chunk_index,
        score=score,
    )


def test_the_question_is_embedded_with_the_ingestion_time_voyage_client(
    embed_question: MagicMock, search: MagicMock
) -> None:
    retrieve(QUESTION)

    embed_question.assert_called_once_with(QUESTION)
    assert search.call_args.kwargs["query_vector"] == [0.5] * EMBEDDING_DIMENSIONS
    assert search.call_args.kwargs["query_text"] == QUESTION


def test_top_k_and_alpha_default_to_seven_and_an_even_hybrid_split(search: MagicMock) -> None:
    retrieve(QUESTION)

    assert search.call_args.kwargs["top_k"] == 7
    assert search.call_args.kwargs["alpha"] == 0.5


def test_top_k_and_alpha_are_overridable_by_the_caller(search: MagicMock) -> None:
    retrieve(QUESTION, top_k=3, alpha=0.8)

    assert search.call_args.kwargs["top_k"] == 3
    assert search.call_args.kwargs["alpha"] == 0.8


def test_each_hit_is_returned_with_its_citation_metadata_and_score(search: MagicMock) -> None:
    search.return_value = [
        make_hit("client id header", 0, 1.0),
        make_hit("subscription webhooks", 2, 0.31, title="EventSub"),
    ]

    chunks = retrieve(QUESTION)

    assert [chunk.text for chunk in chunks] == ["client id header", "subscription webhooks"]
    assert [chunk.score for chunk in chunks] == [1.0, 0.31]
    assert [chunk.source_url for chunk in chunks] == [
        "https://dev.twitch.tv/docs/api/",
        "https://dev.twitch.tv/docs/eventsub/",
    ]
    assert [chunk.title for chunk in chunks] == ["API", "EventSub"]
    assert [chunk.chunk_index for chunk in chunks] == [0, 2]


def test_a_store_that_has_never_been_written_to_is_prepared_and_returns_nothing(
    ensure_schema: MagicMock,
) -> None:
    assert retrieve(QUESTION) == []

    ensure_schema.assert_called_once_with()
