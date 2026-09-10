from collections.abc import Iterator
from unittest.mock import MagicMock

import httpx
import pytest
from django.conf import settings
from groq import APITimeoutError, AuthenticationError, RateLimitError

from retrieval.generation import (
    MAX_RETRIES,
    SYSTEM_PROMPT,
    GenerationError,
    generate,
    select_model,
)
from retrieval.types import ModelHandle, RetrievedChunk, TaskDescriptor

QUESTION = "how do I authenticate a Twitch API request?"

MODEL = ModelHandle(provider="groq", model_id="test-model")

CHUNKS = [
    RetrievedChunk(
        text="Every request must send a Client-Id header.",
        source_url="https://dev.twitch.tv/docs/api/",
        title="API",
        chunk_index=0,
        score=0.91,
    ),
    RetrievedChunk(
        text="EventSub subscriptions need an app access token.",
        source_url="https://dev.twitch.tv/docs/eventsub/",
        title="EventSub",
        chunk_index=2,
        score=0.42,
    ),
]


def response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return httpx.Response(status_code, request=request)


def rate_limit() -> RateLimitError:
    return RateLimitError("429 rate limit", response=response(429), body=None)


def timeout() -> APITimeoutError:
    return APITimeoutError(request=httpx.Request("POST", "https://api.groq.com/openai/v1/"))


def bad_key() -> AuthenticationError:
    return AuthenticationError("401 bad key", response=response(401), body=None)


def completion(text: str) -> MagicMock:
    return MagicMock(choices=[MagicMock(message=MagicMock(content=text))])


def delta(content: str | None) -> MagicMock:
    return MagicMock(choices=[MagicMock(delta=MagicMock(content=content))])


def groq_stream(*deltas: MagicMock, then_raise: Exception | None = None) -> Iterator[MagicMock]:
    yield from deltas
    if then_raise is not None:
        raise then_raise


def test_every_task_kind_resolves_to_the_one_configured_groq_model() -> None:
    answering = select_model(TaskDescriptor())
    rewriting = select_model(TaskDescriptor(kind="query_rewriting"))

    assert answering == rewriting
    assert answering == ModelHandle(provider="groq", model_id=settings.GROQ_MODEL)


def test_a_non_streaming_generation_returns_the_whole_answer_as_text(
    groq_client: MagicMock,
) -> None:
    create = groq_client.chat.completions.create
    create.return_value = completion("Send a Client-Id header.")

    result = generate(MODEL, QUESTION, CHUNKS, stream=False)

    assert result.text == "Send a Client-Id header."
    assert result.token_stream is None
    assert create.call_args.kwargs["model"] == "test-model"
    assert create.call_args.kwargs["stream"] is False


def test_streaming_hands_back_the_provider_tokens_one_at_a_time(groq_client: MagicMock) -> None:
    create = groq_client.chat.completions.create
    create.return_value = groq_stream(delta(None), delta("Send "), delta("a Client-Id header."))

    result = generate(MODEL, QUESTION, CHUNKS)

    assert result.text is None
    assert list(result.token_stream) == ["Send ", "a Client-Id header."]
    assert create.call_args.kwargs["stream"] is True


def test_no_request_reaches_groq_until_the_token_stream_is_iterated(
    groq_client: MagicMock,
) -> None:
    create = groq_client.chat.completions.create
    create.return_value = groq_stream(delta("Send a Client-Id header."))

    result = generate(MODEL, QUESTION, CHUNKS)

    assert result.citations == CHUNKS
    assert groq_client.mock_calls == []

    assert next(result.token_stream) == "Send a Client-Id header."
    create.assert_called_once()


def test_citations_are_the_retrieved_chunks_whatever_the_answer_says(
    groq_client: MagicMock,
) -> None:
    groq_client.chat.completions.create.return_value = completion("The excerpts do not say.")

    result = generate(MODEL, QUESTION, CHUNKS, stream=False)

    assert result.citations == CHUNKS


def test_the_prompt_carries_the_fixed_instructions_and_every_chunk(groq_client: MagicMock) -> None:
    create = groq_client.chat.completions.create
    create.return_value = completion("Send a Client-Id header.")

    generate(MODEL, QUESTION, CHUNKS, stream=False)

    system, user = create.call_args.kwargs["messages"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user["role"] == "user"
    assert QUESTION in user["content"]
    for chunk in CHUNKS:
        assert chunk.text in user["content"]
        assert chunk.title in user["content"]
        assert chunk.source_url in user["content"]


def test_a_rate_limited_request_is_retried_and_recovers(
    groq_client: MagicMock, groq_sleep: MagicMock
) -> None:
    create = groq_client.chat.completions.create
    create.side_effect = [rate_limit(), completion("Send a Client-Id header.")]

    result = generate(MODEL, QUESTION, CHUNKS, stream=False)

    assert result.text == "Send a Client-Id header."
    assert create.call_count == 2
    assert [call.args[0] for call in groq_sleep.call_args_list] == [2]


def test_exhausted_retries_surface_as_a_generation_error_carrying_the_provider_failure(
    groq_client: MagicMock, groq_sleep: MagicMock
) -> None:
    create = groq_client.chat.completions.create
    create.side_effect = timeout()

    with pytest.raises(GenerationError) as raised:
        generate(MODEL, QUESTION, CHUNKS, stream=False)

    assert create.call_count == MAX_RETRIES + 1
    assert [call.args[0] for call in groq_sleep.call_args_list] == [2, 4, 8]
    assert isinstance(raised.value.__cause__, APITimeoutError)


def test_a_stream_failing_before_its_first_token_is_reopened_with_a_fresh_request(
    groq_client: MagicMock, groq_sleep: MagicMock
) -> None:
    create = groq_client.chat.completions.create
    create.side_effect = [
        groq_stream(delta(None), then_raise=rate_limit()),
        groq_stream(delta("Send "), delta("a Client-Id header.")),
    ]

    result = generate(MODEL, QUESTION, CHUNKS)

    assert list(result.token_stream) == ["Send ", "a Client-Id header."]
    assert create.call_count == 2
    assert [call.args[0] for call in groq_sleep.call_args_list] == [2]


def test_a_stream_failing_after_its_first_token_is_not_retried(
    groq_client: MagicMock, groq_sleep: MagicMock
) -> None:
    create = groq_client.chat.completions.create
    create.return_value = groq_stream(
        delta(None), delta("Send a Client-Id header."), then_raise=rate_limit()
    )
    tokens: list[str] = []

    with pytest.raises(GenerationError) as raised:
        for token in generate(MODEL, QUESTION, CHUNKS).token_stream:
            tokens.append(token)

    assert tokens == ["Send a Client-Id header."]
    assert create.call_count == 1
    assert groq_sleep.call_count == 0
    assert isinstance(raised.value.__cause__, RateLimitError)


def test_a_failure_that_is_not_a_rate_limit_or_timeout_is_wrapped_without_retrying(
    groq_client: MagicMock, groq_sleep: MagicMock
) -> None:
    create = groq_client.chat.completions.create
    create.side_effect = bad_key()

    with pytest.raises(GenerationError) as raised:
        generate(MODEL, QUESTION, CHUNKS, stream=False)

    assert create.call_count == 1
    assert groq_sleep.call_count == 0
    assert isinstance(raised.value.__cause__, AuthenticationError)
