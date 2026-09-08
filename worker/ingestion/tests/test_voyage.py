from unittest.mock import MagicMock

import pytest
from shared.voyage import (
    EMBEDDING_MODEL,
    MAX_BATCH_SIZE,
    count_tokens,
    embed_documents,
    embed_query,
)
from voyageai.error import AuthenticationError, RateLimitError, Timeout


def responses(texts: list[str], **kwargs: object) -> MagicMock:
    response = MagicMock()
    response.embeddings = [[0.5] * 1024 for _ in texts]
    return response


def test_embed_documents_sends_one_request_with_the_document_input_type(
    voyage_client: MagicMock,
) -> None:
    voyage_client.embed.side_effect = responses

    embeddings = embed_documents(["chunk one", "chunk two"])

    assert len(embeddings) == 2
    voyage_client.embed.assert_called_once_with(
        ["chunk one", "chunk two"], model=EMBEDDING_MODEL, input_type="document"
    )


def test_embed_documents_splits_batches_at_the_sdk_limit(voyage_client: MagicMock) -> None:
    voyage_client.embed.side_effect = responses
    texts = [f"chunk {index}" for index in range(MAX_BATCH_SIZE + 20)]

    embeddings = embed_documents(texts)

    assert len(embeddings) == len(texts)
    assert [len(call.args[0]) for call in voyage_client.embed.call_args_list] == [
        MAX_BATCH_SIZE,
        20,
    ]


def test_embed_query_returns_a_single_vector_with_the_query_input_type(
    voyage_client: MagicMock,
) -> None:
    voyage_client.embed.side_effect = responses

    embedding = embed_query("how do I refresh a token?")

    assert len(embedding) == 1024
    voyage_client.embed.assert_called_once_with(
        ["how do I refresh a token?"], model=EMBEDDING_MODEL, input_type="query"
    )


def test_rate_limit_is_retried_three_times_with_doubling_backoff(
    voyage_client: MagicMock, voyage_sleep: MagicMock
) -> None:
    voyage_client.embed.side_effect = RateLimitError("429 too many requests")

    with pytest.raises(RateLimitError):
        embed_documents(["chunk"])

    assert voyage_client.embed.call_count == 4
    assert [call.args[0] for call in voyage_sleep.call_args_list] == [2, 4, 8]


def test_timeout_is_retried_and_recovers_when_a_later_attempt_succeeds(
    voyage_client: MagicMock, voyage_sleep: MagicMock
) -> None:
    voyage_client.embed.side_effect = [Timeout("read timed out"), responses(["chunk"])]

    embeddings = embed_documents(["chunk"])

    assert len(embeddings) == 1
    assert voyage_client.embed.call_count == 2
    assert [call.args[0] for call in voyage_sleep.call_args_list] == [2]


def test_errors_other_than_rate_limit_and_timeout_are_not_retried(
    voyage_client: MagicMock, voyage_sleep: MagicMock
) -> None:
    voyage_client.embed.side_effect = AuthenticationError("bad key")

    with pytest.raises(AuthenticationError):
        embed_documents(["chunk"])

    assert voyage_client.embed.call_count == 1
    assert voyage_sleep.call_count == 0


def test_token_counting_runs_locally_against_the_voyage_tokenizer() -> None:
    short = count_tokens("Get Streams returns a list of live channels.")
    long = count_tokens("Get Streams returns a list of live channels. " * 20)

    assert 0 < short < long
