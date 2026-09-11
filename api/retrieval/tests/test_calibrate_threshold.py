import json
from collections.abc import Callable, Iterator
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from pytest_django.fixtures import SettingsWrapper
from shared.weaviate_client import SearchHit

from retrieval.tests.test_service import make_hit

QUESTIONS = [
    {"question": "how do I authenticate a Twitch API request?", "expected": "in_scope"},
    {"question": "how do I subscribe to EventSub?", "expected": "in_scope"},
    {"question": "how do I bake sourdough?", "expected": "out_of_scope"},
]

HITS: dict[str, list[SearchHit]] = {
    "how do I authenticate a Twitch API request?": [
        make_hit("bearer token", 1, 0.42),
        make_hit("client id header", 0, 0.91),
    ],
    "how do I subscribe to EventSub?": [make_hit("webhooks", 0, 0.77, title="EventSub")],
    "how do I bake sourdough?": [],
}


@pytest.fixture
def question_file(
    tmp_path: Path, settings: SettingsWrapper
) -> Callable[[list[dict[str, str]]], Path]:
    def write(entries: list[dict[str, str]]) -> Path:
        path = tmp_path / "calibration_questions.json"
        path.write_text(json.dumps(entries))
        settings.CALIBRATION_QUESTIONS_PATH = path
        return path

    return write


@pytest.fixture
def close_client() -> Iterator[MagicMock]:
    with patch("retrieval.management.commands.calibrate_threshold.close_client") as mock:
        yield mock


@pytest.fixture
def calibrate_sleep() -> Iterator[MagicMock]:
    with patch("retrieval.management.commands.calibrate_threshold.time.sleep") as mock:
        yield mock


def test_the_top_score_of_every_question_is_grouped_under_its_expected_label(
    question_file: Callable[[list[dict[str, str]]], Path], search: MagicMock
) -> None:
    question_file(QUESTIONS)
    search.side_effect = lambda **kwargs: HITS[kwargs["query_text"]]
    out = StringIO()

    call_command("calibrate_threshold", stdout=out)

    assert out.getvalue() == (
        "in_scope\n"
        "  0.9100  how do I authenticate a Twitch API request?\n"
        "  0.7700  how do I subscribe to EventSub?\n"
        "out_of_scope\n"
        "    none  how do I bake sourdough?\n"
    )


def test_an_unpopulated_question_file_is_reported_instead_of_an_empty_table(
    question_file: Callable[[list[dict[str, str]]], Path], search: MagicMock
) -> None:
    path = question_file([])
    out = StringIO()

    call_command("calibrate_threshold", stdout=out)

    assert out.getvalue() == f"No calibration questions configured in {path}\n"
    search.assert_not_called()


def test_the_one_shot_command_closes_its_weaviate_connection(
    question_file: Callable[[list[dict[str, str]]], Path],
    search: MagicMock,
    close_client: MagicMock,
) -> None:
    question_file(QUESTIONS)
    search.side_effect = lambda **kwargs: HITS[kwargs["query_text"]]

    call_command("calibrate_threshold", stdout=StringIO())

    close_client.assert_called_once_with()


def test_the_shipped_question_file_is_a_readable_list(settings: SettingsWrapper) -> None:
    assert json.loads(settings.CALIBRATION_QUESTIONS_PATH.read_text()) == []


def test_consecutive_questions_are_paced_under_voyages_free_tier_rate_limit(
    question_file: Callable[[list[dict[str, str]]], Path],
    search: MagicMock,
    calibrate_sleep: MagicMock,
) -> None:
    question_file(QUESTIONS)
    search.side_effect = lambda **kwargs: HITS[kwargs["query_text"]]

    call_command("calibrate_threshold", stdout=StringIO())

    # 3 questions -> 2 gaps between them, never a delay before the first Voyage call.
    assert calibrate_sleep.call_args_list == [((20,),), ((20,),)]


def test_a_single_question_needs_no_pacing(
    question_file: Callable[[list[dict[str, str]]], Path],
    search: MagicMock,
    calibrate_sleep: MagicMock,
) -> None:
    question_file([QUESTIONS[0]])
    search.side_effect = lambda **kwargs: HITS[kwargs["query_text"]]

    call_command("calibrate_threshold", stdout=StringIO())

    calibrate_sleep.assert_not_called()
