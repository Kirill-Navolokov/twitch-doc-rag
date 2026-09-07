import hashlib
import logging
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.core.management import call_command
from shared.models import Document, DocumentProcessingLog, FetchStatus

from ingestion.models import IngestionRun
from ingestion.tasks import (
    FETCH_TIMEOUT_SECONDS,
    SECONDS_BETWEEN_FETCHES,
    USER_AGENT,
    load_doc_urls,
    run_ingestion,
)
from ingestion.tests.conftest import page_html, responder

API_URL = "https://dev.twitch.tv/docs/api/"
EVENTSUB_URL = "https://dev.twitch.tv/docs/eventsub/"
BROKEN_URL = "https://dev.twitch.tv/docs/does-not-exist/"

pytestmark = pytest.mark.django_db

UrlList = Callable[[list[str]], Path]

TWO_PAGES: dict[str, str | Exception] = {
    API_URL: page_html("API"),
    EVENTSUB_URL: page_html("EventSub"),
}


def test_load_doc_urls_reads_static_config(url_list: UrlList) -> None:
    url_list([API_URL, EVENTSUB_URL])

    assert load_doc_urls() == [API_URL, EVENTSUB_URL]


def test_waits_at_least_one_second_between_fetches(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL, EVENTSUB_URL])
    http_get.side_effect = responder(TWO_PAGES)

    run_ingestion()

    assert sleep.call_args_list == [((SECONDS_BETWEEN_FETCHES,), {})]
    assert SECONDS_BETWEEN_FETCHES >= 1


def test_fetches_each_url_with_timeout_and_user_agent(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL])
    http_get.side_effect = responder({API_URL: page_html("API")})

    run_ingestion()

    http_get.assert_called_once_with(
        API_URL, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT_SECONDS
    )


def test_extracts_main_content_as_markdown(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL])
    http_get.side_effect = responder({API_URL: page_html("API Reference")})

    run_ingestion()

    raw_text = Document.objects.get(source_url=API_URL).raw_text
    assert raw_text.startswith("# API Reference")
    assert "<p>" not in raw_text
    assert "Helix API" in raw_text


def test_stores_document_record_per_fetched_page(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL, EVENTSUB_URL])
    http_get.side_effect = responder(TWO_PAGES)

    run_ingestion()

    assert Document.objects.count() == 2
    document = Document.objects.get(source_url=API_URL)
    assert document.title == "API"
    assert document.raw_text
    assert document.fetched_at is not None
    assert document.status == FetchStatus.SUCCESS


def test_content_hash_is_sha256_of_extracted_text_not_raw_html(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    html = page_html("API")
    url_list([API_URL])
    http_get.side_effect = responder({API_URL: html})

    run_ingestion()

    document = Document.objects.get(source_url=API_URL)
    assert document.content_hash == hashlib.sha256(document.raw_text.encode()).hexdigest()
    assert document.content_hash != hashlib.sha256(html.encode()).hexdigest()


def test_refetch_updates_existing_document_without_duplicating(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL])
    http_get.side_effect = responder({API_URL: page_html("API")})
    run_ingestion()
    first = Document.objects.get(source_url=API_URL)

    http_get.side_effect = responder({API_URL: page_html("API Reference v2")})
    run_ingestion()

    assert Document.objects.count() == 1
    updated = Document.objects.get(source_url=API_URL)
    assert updated.id == first.id
    assert updated.title == "API Reference v2"
    assert updated.content_hash != first.content_hash


def test_repeated_run_on_unchanged_docs_creates_no_duplicate_documents(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL, EVENTSUB_URL])
    http_get.side_effect = responder(TWO_PAGES)

    run_ingestion()
    run_ingestion()

    assert Document.objects.count() == 2
    assert IngestionRun.objects.count() == 2


def test_management_command_queues_celery_task() -> None:
    with patch("ingestion.tasks.run_ingestion.delay") as delay:
        call_command("run_ingestion")

    delay.assert_called_once_with()


def test_logs_result_per_url(
    url_list: UrlList,
    http_get: MagicMock,
    sleep: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    url_list([API_URL, BROKEN_URL, "", API_URL])
    http_get.side_effect = responder(
        {API_URL: page_html("API"), BROKEN_URL: requests.ConnectionError("name resolution failed")}
    )

    with caplog.at_level(logging.INFO, logger="ingestion.tasks"):
        run_ingestion()

    messages = [record.getMessage() for record in caplog.records]
    assert any(f"url={API_URL} result=success" in message for message in messages)
    assert any(
        f"url={BROKEN_URL} result=failed" in message and "name resolution failed" in message
        for message in messages
    )
    assert any("result=skipped reason=blank entry" in message for message in messages)
    assert any("result=skipped reason=duplicate entry" in message for message in messages)


def test_ingestion_run_records_times_and_counts(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL, EVENTSUB_URL, BROKEN_URL])
    http_get.side_effect = responder(
        {
            API_URL: page_html("API"),
            EVENTSUB_URL: page_html("EventSub"),
            BROKEN_URL: requests.ConnectionError("boom"),
        }
    )

    run_ingestion()

    run = IngestionRun.objects.get()
    assert run.total_links == 3
    assert run.succeeded == 2
    assert run.failed == 1
    assert run.started_at <= run.ended_at


def test_processing_log_row_per_url_with_duration_and_status(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL, BROKEN_URL])
    http_get.side_effect = responder(
        {API_URL: page_html("API"), BROKEN_URL: requests.ConnectionError("boom")}
    )

    run_ingestion()

    run = IngestionRun.objects.get()
    logs = {log.url: log for log in DocumentProcessingLog.objects.all()}
    assert set(logs) == {API_URL, BROKEN_URL}
    assert logs[API_URL].fetch_status == FetchStatus.SUCCESS
    assert logs[BROKEN_URL].fetch_status == FetchStatus.FAILED
    for log in logs.values():
        assert log.ingestion_run_id == run.id
        assert log.fetch_duration_ms >= 0
        assert log.chunk_duration_ms is None
        assert log.total_duration_ms is None


def test_broken_url_does_not_stop_the_batch(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([BROKEN_URL, API_URL, EVENTSUB_URL])
    http_get.side_effect = responder(
        {
            BROKEN_URL: requests.HTTPError("404 Not Found"),
            API_URL: page_html("API"),
            EVENTSUB_URL: page_html("EventSub"),
        }
    )

    run_ingestion()

    assert Document.objects.get(source_url=BROKEN_URL).status == FetchStatus.FAILED
    assert Document.objects.get(source_url=API_URL).status == FetchStatus.SUCCESS
    assert Document.objects.get(source_url=EVENTSUB_URL).status == FetchStatus.SUCCESS


def test_blank_and_duplicate_entries_are_skipped_without_processing_log_rows(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL, "   ", API_URL])
    http_get.side_effect = responder({API_URL: page_html("API")})

    run_ingestion()

    assert http_get.call_count == 1
    assert DocumentProcessingLog.objects.count() == 1
    run = IngestionRun.objects.get()
    assert run.total_links == 3
    assert run.succeeded == 1
    assert run.failed == 0


def test_page_without_extractable_content_is_recorded_as_failed(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL])
    http_get.side_effect = responder({API_URL: "<html><body></body></html>"})

    run_ingestion()

    assert Document.objects.get(source_url=API_URL).status == FetchStatus.FAILED
    assert DocumentProcessingLog.objects.get().fetch_status == FetchStatus.FAILED


def test_failed_refetch_marks_document_failed_but_keeps_last_good_text(
    url_list: UrlList, http_get: MagicMock, sleep: MagicMock
) -> None:
    url_list([API_URL])
    http_get.side_effect = responder({API_URL: page_html("API")})
    run_ingestion()
    original_text = Document.objects.get(source_url=API_URL).raw_text

    http_get.side_effect = responder({API_URL: requests.ConnectionError("boom")})
    run_ingestion()

    document = Document.objects.get(source_url=API_URL)
    assert document.status == FetchStatus.FAILED
    assert document.raw_text == original_text
