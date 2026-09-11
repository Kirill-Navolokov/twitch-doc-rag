import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from django.http import StreamingHttpResponse
from django.test import Client
from pytest_django.fixtures import SettingsWrapper

from retrieval.tests.test_generation import QUESTION, bad_key, delta, groq_stream, rate_limit
from retrieval.tests.test_service import make_hit
from retrieval.views import FALLBACK_TEXT

URL = "/api/ask"

RELEVANT = 0.9
IRRELEVANT = 0.1


@dataclass(frozen=True)
class SseEvent:
    name: str
    data: dict[str, object]


def sse_events(response: StreamingHttpResponse) -> list[SseEvent]:
    events = []
    for frame in response.streaming_content:
        name, _, payload = frame.decode().partition("\n")
        events.append(
            SseEvent(
                name=name.removeprefix("event: "),
                data=json.loads(payload.removeprefix("data: ").strip()),
            )
        )
    return events


def ask(client: Client, question: str = QUESTION, **extra: object) -> StreamingHttpResponse:
    return client.post(
        URL, data={"question": question}, content_type="application/json", **extra
    )


def rag_query_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("rag_query")
    ]


@pytest.fixture(autouse=True)
def threshold(settings: SettingsWrapper) -> None:
    settings.RELEVANCE_THRESHOLD = 0.5


@pytest.fixture
def relevant_chunk(search: MagicMock) -> MagicMock:
    search.return_value = [make_hit("client id header", 0, RELEVANT)]
    return search


@pytest.fixture
def close_client() -> Iterator[MagicMock]:
    with patch("shared.weaviate_client.close_client") as mock:
        yield mock


@pytest.fixture
def clock() -> Iterator[MagicMock]:
    with patch("retrieval.views.time") as mock:
        yield mock


@pytest.fixture
def generation() -> Iterator[tuple[MagicMock, MagicMock]]:
    with (
        patch("retrieval.views.select_model") as select_model,
        patch("retrieval.views.generate") as generate,
    ):
        yield select_model, generate


def test_a_question_with_relevant_docs_streams_its_citations_then_tokens_then_done(
    client: Client, search: MagicMock, groq_client: MagicMock
) -> None:
    search.return_value = [
        make_hit("client id header", 0, RELEVANT),
        make_hit("subscription webhooks", 2, 0.4, title="EventSub"),
    ]
    groq_client.chat.completions.create.return_value = groq_stream(
        delta("Send "), delta("a Client-Id header.")
    )

    events = sse_events(ask(client))

    assert [event.name for event in events] == ["citations", "token", "token", "done"]
    assert events[0].data == {
        "citations": [
            {
                "source_url": "https://dev.twitch.tv/docs/api/",
                "title": "API",
                "chunk_index": 0,
                "score": RELEVANT,
            },
            {
                "source_url": "https://dev.twitch.tv/docs/eventsub/",
                "title": "EventSub",
                "chunk_index": 2,
                "score": 0.4,
            },
        ]
    }
    assert [event.data for event in events[1:3]] == [
        {"text": "Send "},
        {"text": "a Client-Id header."},
    ]
    assert events[3].data == {}


def test_the_citations_reach_the_client_before_groq_is_asked_for_a_single_token(
    client: Client, relevant_chunk: MagicMock, groq_client: MagicMock
) -> None:
    create = groq_client.chat.completions.create
    create.return_value = groq_stream(delta("Send a Client-Id header."))

    frames = iter(ask(client).streaming_content)

    assert next(frames).startswith(b"event: citations")
    assert create.call_args_list == []

    assert list(frames)
    create.assert_called_once()


def test_the_stream_is_framed_as_unbuffered_server_sent_events_a_browser_may_read(
    client: Client, relevant_chunk: MagicMock, groq_client: MagicMock
) -> None:
    groq_client.chat.completions.create.return_value = groq_stream(delta("Send it."))

    response = ask(client)

    assert response["Content-Type"] == "text/event-stream"
    assert response["Cache-Control"] == "no-cache"
    assert response["X-Accel-Buffering"] == "no"
    assert response["Access-Control-Allow-Origin"] == "*"
    assert b"".join(response.streaming_content).endswith(b"\n\n")


def test_a_client_that_accepts_only_an_event_stream_is_served_rather_than_refused(
    client: Client, relevant_chunk: MagicMock, groq_client: MagicMock
) -> None:
    groq_client.chat.completions.create.return_value = groq_stream(delta("Send it."))

    response = ask(client, headers={"accept": "text/event-stream"})

    assert response.status_code == 200
    assert [event.name for event in sse_events(response)] == ["citations", "token", "done"]


def test_a_browser_preflight_is_answered_with_the_headers_the_real_post_needs(
    client: Client,
) -> None:
    response = client.options(URL, content_type="application/json")

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "*"
    assert response["Access-Control-Allow-Methods"] == "POST, OPTIONS"
    assert response["Access-Control-Allow-Headers"] == "Content-Type"


def test_a_question_no_retrieved_chunk_is_relevant_to_never_reaches_the_model(
    client: Client,
    search: MagicMock,
    groq_client: MagicMock,
    generation: tuple[MagicMock, MagicMock],
) -> None:
    select_model, generate = generation
    search.return_value = [make_hit("unrelated prose", 0, IRRELEVANT)]

    events = sse_events(ask(client, "what is the capital of France?"))

    assert [event.name for event in events] == ["fallback"]
    assert events[0].data == {"text": FALLBACK_TEXT}
    select_model.assert_not_called()
    generate.assert_not_called()
    assert groq_client.mock_calls == []


def test_a_question_that_retrieves_nothing_at_all_falls_back_instead_of_failing(
    client: Client, generation: tuple[MagicMock, MagicMock]
) -> None:
    select_model, generate = generation

    events = sse_events(ask(client))

    assert [event.name for event in events] == ["fallback"]
    generate.assert_not_called()


def test_a_chunk_scoring_exactly_at_the_threshold_is_relevant_enough_to_answer_from(
    client: Client, search: MagicMock, groq_client: MagicMock, settings: SettingsWrapper
) -> None:
    search.return_value = [make_hit("client id header", 0, settings.RELEVANCE_THRESHOLD)]
    groq_client.chat.completions.create.return_value = groq_stream(delta("Send it."))

    assert [event.name for event in sse_events(ask(client))] == ["citations", "token", "done"]


def test_the_top_score_decides_relevance_whatever_order_retrieval_returned(
    client: Client, search: MagicMock, groq_client: MagicMock
) -> None:
    search.return_value = [make_hit("weak match", 0, IRRELEVANT), make_hit("strong", 1, RELEVANT)]
    groq_client.chat.completions.create.return_value = groq_stream(delta("Send it."))

    assert [event.name for event in sse_events(ask(client))] == ["citations", "token", "done"]


def test_a_generation_failure_before_the_first_token_replaces_the_answer_with_an_error(
    client: Client, relevant_chunk: MagicMock, groq_client: MagicMock
) -> None:
    groq_client.chat.completions.create.side_effect = bad_key()

    events = sse_events(ask(client))

    assert [event.name for event in events] == ["citations", "error"]
    assert "groq generation failed" in events[1].data["message"]


def test_a_generation_failure_after_real_tokens_ends_the_partial_answer_with_an_error(
    client: Client, relevant_chunk: MagicMock, groq_client: MagicMock, groq_sleep: MagicMock
) -> None:
    groq_client.chat.completions.create.return_value = groq_stream(
        delta("Send "), delta("a Client-Id header."), then_raise=rate_limit()
    )

    events = sse_events(ask(client))

    assert [event.name for event in events] == ["citations", "token", "token", "error"]
    assert "mid-stream" in events[3].data["message"]
    assert groq_sleep.call_count == 0


@pytest.mark.parametrize(
    "body",
    [{}, {"question": ""}, {"question": "   "}, {"question": 7}, {"question": None}, ["question"]],
)
def test_a_request_without_a_usable_question_is_refused_before_any_stream_opens(
    client: Client, search: MagicMock, body: dict[str, object] | list[str]
) -> None:
    response = client.post(URL, data=body, content_type="application/json")

    assert response.status_code == 400
    assert json.loads(response.content) == {"error": "question is required"}
    assert response["Content-Type"] == "application/json"
    assert not isinstance(response, StreamingHttpResponse)
    assert not response.has_header("X-Accel-Buffering")
    search.assert_not_called()


def test_a_streamed_answer_logs_one_query_line_carrying_the_chunks_it_used(
    client: Client,
    relevant_chunk: MagicMock,
    groq_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    groq_client.chat.completions.create.return_value = groq_stream(delta("Send it."))

    sse_events(ask(client))

    line = rag_query_lines(caplog)
    assert len(line) == 1
    assert f"question={QUESTION!r}" in line[0]
    assert "fallback_triggered=False" in line[0]
    assert "'source_url': 'https://dev.twitch.tv/docs/api/'" in line[0]
    assert "'chunk_index': 0" in line[0]
    assert f"'score': {RELEVANT}" in line[0]


def test_a_fallback_logs_its_own_query_line_flagged_as_such(
    client: Client, search: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    search.return_value = [make_hit("unrelated prose", 0, IRRELEVANT)]

    sse_events(ask(client))

    line = rag_query_lines(caplog)
    assert len(line) == 1
    assert "fallback_triggered=True" in line[0]


def test_a_failed_generation_still_logs_exactly_one_query_line(
    client: Client,
    relevant_chunk: MagicMock,
    groq_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    groq_client.chat.completions.create.side_effect = bad_key()

    sse_events(ask(client))

    assert len(rag_query_lines(caplog)) == 1


def test_the_logged_response_time_spans_the_whole_stream_not_the_view_call(
    client: Client,
    relevant_chunk: MagicMock,
    groq_client: MagicMock,
    clock: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    groq_client.chat.completions.create.return_value = groq_stream(delta("Send it."))
    clock.monotonic.side_effect = [10.0, 12.5]

    response = ask(client)
    assert rag_query_lines(caplog) == []

    sse_events(response)

    assert "response_time_ms=2500" in rag_query_lines(caplog)[0]


def test_a_request_never_closes_the_servers_cached_weaviate_client(
    client: Client, relevant_chunk: MagicMock, groq_client: MagicMock, close_client: MagicMock
) -> None:
    groq_client.chat.completions.create.return_value = groq_stream(delta("Send it."))

    sse_events(ask(client))

    close_client.assert_not_called()
