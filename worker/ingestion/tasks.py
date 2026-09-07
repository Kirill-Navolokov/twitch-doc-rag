import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass

import requests
import trafilatura
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from shared.models import Document, DocumentProcessingLog, FetchStatus

from ingestion.models import IngestionRun

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 15
SECONDS_BETWEEN_FETCHES = 1
USER_AGENT = "twitch-doc-rag/0.1 (documentation ingestion bot)"


class ExtractionError(Exception):
    pass


@dataclass(frozen=True)
class ExtractedPage:
    title: str
    text: str


def load_doc_urls() -> list[str]:
    return json.loads(settings.DOC_URLS_PATH.read_text())


def fetch_page(url: str) -> ExtractedPage:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    tree = trafilatura.load_html(response.text)
    text = trafilatura.extract(tree, output_format="markdown")
    if not text:
        raise ExtractionError("no main content extracted")

    metadata = trafilatura.extract_metadata(tree)
    return ExtractedPage(title=metadata.title or url, text=text)


def process_url(run_id: uuid.UUID, url: str) -> FetchStatus:
    started = time.monotonic()
    # Caught broadly: a single unreachable or unparseable page must never abort the rest of the
    # batch, and both requests and trafilatura surface arbitrary exception types on hostile HTML.
    try:
        page = fetch_page(url)
    except Exception as exc:
        Document.objects.update_or_create(
            source_url=url,
            defaults={"status": FetchStatus.FAILED, "fetched_at": timezone.now()},
        )
        fetch_status = FetchStatus.FAILED
        logger.warning("ingest url=%s result=failed reason=%s", url, exc)
    else:
        Document.objects.update_or_create(
            source_url=url,
            defaults={
                "title": page.title,
                "raw_text": page.text,
                "content_hash": hashlib.sha256(page.text.encode()).hexdigest(),
                "fetched_at": timezone.now(),
                "status": FetchStatus.SUCCESS,
            },
        )
        fetch_status = FetchStatus.SUCCESS
        logger.info("ingest url=%s result=success", url)

    DocumentProcessingLog.objects.create(
        ingestion_run_id=run_id,
        url=url,
        fetch_duration_ms=round((time.monotonic() - started) * 1000),
        fetch_status=fetch_status,
    )
    return fetch_status


@shared_task
def run_ingestion() -> str:
    urls = load_doc_urls()
    run = IngestionRun.objects.create(started_at=timezone.now(), total_links=len(urls))
    logger.info("ingestion run %s started total_links=%d", run.id, run.total_links)

    processed: set[str] = set()
    for raw_url in urls:
        url = raw_url.strip()
        if not url:
            logger.info("ingest url=%r result=skipped reason=blank entry", raw_url)
            continue
        if url in processed:
            logger.info("ingest url=%s result=skipped reason=duplicate entry in this run", url)
            continue

        if processed:
            time.sleep(SECONDS_BETWEEN_FETCHES)
        processed.add(url)

        if process_url(run.id, url) is FetchStatus.SUCCESS:
            run.succeeded += 1
        else:
            run.failed += 1

    run.ended_at = timezone.now()
    run.save(update_fields=["ended_at", "succeeded", "failed"])
    logger.info(
        "ingestion run %s finished total_links=%d succeeded=%d failed=%d",
        run.id,
        run.total_links,
        run.succeeded,
        run.failed,
    )
    return str(run.id)
