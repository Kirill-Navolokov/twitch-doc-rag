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
from django.db import transaction
from django.utils import timezone
from shared.models import Chunk, Document, DocumentProcessingLog, FetchStatus
from shared.voyage import embed_documents

from ingestion.chunker import chunk_markdown
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


@dataclass(frozen=True)
class ProcessedUrl:
    document_id: uuid.UUID
    log_id: uuid.UUID
    fetch_status: FetchStatus


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


def process_url(run_id: uuid.UUID, url: str) -> ProcessedUrl:
    started = time.monotonic()
    # Caught broadly: a single unreachable or unparseable page must never abort the rest of the
    # batch, and both requests and trafilatura surface arbitrary exception types on hostile HTML.
    try:
        page = fetch_page(url)
    except Exception as exc:
        document, _ = Document.objects.update_or_create(
            source_url=url,
            defaults={"status": FetchStatus.FAILED, "fetched_at": timezone.now()},
        )
        fetch_status = FetchStatus.FAILED
        logger.warning("ingest url=%s result=failed reason=%s", url, exc)
    else:
        document, _ = Document.objects.update_or_create(
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

    log = DocumentProcessingLog.objects.create(
        ingestion_run_id=run_id,
        url=url,
        fetch_duration_ms=round((time.monotonic() - started) * 1000),
        fetch_status=fetch_status,
    )
    return ProcessedUrl(document_id=document.id, log_id=log.id, fetch_status=fetch_status)


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

        processed_url = process_url(run.id, url)
        if processed_url.fetch_status is FetchStatus.SUCCESS:
            run.succeeded += 1
            chunk_document.delay(
                document_id=str(processed_url.document_id),
                document_processing_log_id=str(processed_url.log_id),
            )
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


def record_chunking_durations(
    log_id: str, chunk_duration_ms: int, chunk_count: int, embed_duration_ms: int
) -> None:
    log = DocumentProcessingLog.objects.get(id=log_id)
    log.chunk_duration_ms = chunk_duration_ms
    log.chunk_count = chunk_count
    log.embed_duration_ms = embed_duration_ms
    log.total_duration_ms = log.fetch_duration_ms + chunk_duration_ms + embed_duration_ms
    log.save(
        update_fields=[
            "chunk_duration_ms",
            "chunk_count",
            "embed_duration_ms",
            "total_duration_ms",
        ]
    )


@shared_task
def chunk_document(document_id: str, document_processing_log_id: str | None = None) -> int:
    document = Document.objects.get(id=document_id)
    if document.content_hash == document.chunked_content_hash:
        logger.info("chunk url=%s result=skipped reason=already chunked", document.source_url)
        return 0

    chunk_started = time.monotonic()
    texts = chunk_markdown(document.raw_text)
    chunk_duration_ms = round((time.monotonic() - chunk_started) * 1000)

    # Deliberately outside any transaction: this call retries with backoff for up to ~14s, which is
    # far too long to hold a row lock on the document being rewritten.
    embed_started = time.monotonic()
    embeddings = embed_documents(texts)
    embed_duration_ms = round((time.monotonic() - embed_started) * 1000)

    with transaction.atomic():
        Chunk.objects.filter(document=document).delete()
        Chunk.objects.bulk_create(
            Chunk(document=document, chunk_index=index, text=text, embedding=embedding)
            for index, (text, embedding) in enumerate(zip(texts, embeddings, strict=True))
        )
        document.chunked_content_hash = document.content_hash
        document.save(update_fields=["chunked_content_hash"])

    if document_processing_log_id is not None:
        record_chunking_durations(
            document_processing_log_id, chunk_duration_ms, len(texts), embed_duration_ms
        )

    logger.info("chunk url=%s result=success chunks=%d", document.source_url, len(texts))
    return len(texts)
