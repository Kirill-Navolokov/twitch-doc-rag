# Feature 01 — Doc Ingestion

## Owning Project
`worker` (per `01-architecture.md`'s Project Structure)

## Goal
Fetch Twitch Developer documentation pages and store them as raw, structured text records in Postgres, forming the source corpus for chunking and embedding.

## Functional Requirements
- FR-1: Read the list of Twitch Developer doc URLs to ingest from a static config file (`docs/doc_urls.json`) — a flat array of plain URL strings, nothing nested — maintained manually by the user. Implementation creates this file with an empty array (`[]`) — content is filled in separately, not generated
- FR-1a: Wait at least 1 second between fetches, to avoid hammering Twitch's site with a rapid-fire batch of requests
- FR-2: Fetch the HTML content of each URL
- FR-3: Extract the page's main textual content using a general-purpose extractor (`trafilatura`, markdown output mode) — no site-specific selectors, so the same code would generalize to a different doc site without rewriting
- FR-4: Store each page as a document record: source URL, title, extracted text, fetched timestamp
- FR-4a: Compute `content_hash` from the extracted text (not raw HTML) on every fetch, so unrelated markup changes (ads, scripts, whitespace) don't trigger false re-chunking downstream
- FR-5: Re-fetching an already-ingested URL updates its existing record instead of duplicating it
- FR-6: Run as a Celery task, triggered manually via a management command, or on a schedule via Celery beat (cron-style)
- FR-7: Log the result per URL: success, failed, or skipped, with a reason
- FR-8: Log job-level start time, end time, and total/succeeded/failed link counts
- FR-9: Log, per link, the fetch duration — as one row in a shared per-document processing record that later stages (chunking, embedding) append their own timings to

## Non-Functional Constraints
- Runs fully inside Docker Compose; no dependency beyond network access to the doc source
- No paid service required
- Idempotent: running ingestion twice on unchanged docs produces no duplicate records

## Interfaces

### Doc URL list (static config)
```
docs/doc_urls.json
[]
```
User-maintained. Read directly by the ingestion task at run time.

### Document record (Postgres)
```
Document
- id: UUID
- source_url: string (unique)
- title: string
- raw_text: text
- content_hash: string       # hash of raw_text, updated on every fetch
- fetched_at: datetime
- status: enum (success, failed)
```

### Trigger
```
# Manual
python manage.py run_ingestion

# Scheduled
Celery beat entry running the same task on a configured interval (e.g. daily)
```

### Job log (Postgres)
```
IngestionRun
- id: UUID
- started_at: datetime
- ended_at: datetime
- total_links: int
- succeeded: int
- failed: int
```

### Per-link log (Postgres)
One row per URL per run. This feature populates the fetch fields; `02-chunking-embedding.md` appends the rest to the same row.
```
DocumentProcessingLog
- id: UUID
- ingestion_run_id: FK -> IngestionRun
- url: string
- fetch_duration_ms: int
- fetch_status: enum (success, failed)
- chunk_duration_ms: int       # populated by 02-chunking-embedding
- chunk_count: int             # populated by 02-chunking-embedding
- embed_duration_ms: int       # populated by 02-chunking-embedding
- total_duration_ms: int       # populated once all stages complete
```

## Acceptance Criteria
- Running ingestion against the configured URL list produces one `Document` record per successfully fetched page
- Re-running ingestion updates existing records rather than duplicating them
- A deliberately broken URL is recorded with status `failed` and does not stop the rest of the batch
- Each run produces one `IngestionRun` record with accurate start/end time and link counts
- Each processed URL has a `DocumentProcessingLog` row with fetch duration and status filled in

## Out of Scope
- Chunking or embedding, and their log fields on `DocumentProcessingLog` (`02-chunking-embedding.md`)
- Writing to the vector store (`03-vector-store-retrieval.md`)
- Scheduled or automatic re-ingestion (manual trigger only for MVP)
- Sources other than the fixed Twitch Developer doc URL list

## Open Questions
None currently.
