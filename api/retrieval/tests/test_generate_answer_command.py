from collections.abc import Iterator
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from retrieval.tests.test_generation import QUESTION, completion, delta, groq_stream
from retrieval.tests.test_service import make_hit


@pytest.fixture
def close_client() -> Iterator[MagicMock]:
    with patch("retrieval.management.commands.generate_answer.close_client") as mock:
        yield mock


def test_the_answer_is_printed_in_full_after_the_chunks_it_was_grounded_in(
    groq_client: MagicMock, search: MagicMock
) -> None:
    search.return_value = [make_hit("client id header", 0, 1.0)]
    groq_client.chat.completions.create.return_value = completion("Send a Client-Id header.")
    out = StringIO()

    call_command("generate_answer", QUESTION, stdout=out)

    assert out.getvalue() == (
        "1.0000  API #0  https://dev.twitch.tv/docs/api/\nSend a Client-Id header.\n"
    )


def test_the_streamed_answer_is_printed_token_by_token(
    groq_client: MagicMock, search: MagicMock
) -> None:
    search.return_value = [make_hit("client id header", 0, 1.0)]
    groq_client.chat.completions.create.return_value = groq_stream(
        delta("Send "), delta("a Client-Id header.")
    )
    out = StringIO()

    call_command("generate_answer", QUESTION, "--stream", stdout=out)

    assert out.getvalue().endswith("Send a Client-Id header.\n")


def test_the_one_shot_command_closes_its_weaviate_connection(
    close_client: MagicMock, groq_client: MagicMock
) -> None:
    groq_client.chat.completions.create.return_value = completion("The excerpts do not say.")

    call_command("generate_answer", QUESTION, stdout=StringIO())

    close_client.assert_called_once_with()
