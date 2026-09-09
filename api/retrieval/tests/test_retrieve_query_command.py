from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from retrieval.tests.test_service import QUESTION, make_hit


@pytest.fixture
def close_client() -> Iterator[MagicMock]:
    with patch("retrieval.management.commands.retrieve_query.close_client") as mock:
        yield mock


def test_the_one_shot_command_closes_its_weaviate_connection(
    close_client: MagicMock, search: MagicMock
) -> None:
    search.return_value = [make_hit("client id header", 0, 1.0)]

    call_command("retrieve_query", QUESTION)

    close_client.assert_called_once_with()


def test_the_connection_is_closed_even_when_retrieval_fails(
    close_client: MagicMock, search: MagicMock
) -> None:
    search.side_effect = RuntimeError("weaviate unreachable")

    with pytest.raises(RuntimeError):
        call_command("retrieve_query", QUESTION)

    close_client.assert_called_once_with()
