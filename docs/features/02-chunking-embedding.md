# Feature 02 — Chunking & Embedding

## Owning Project
`worker`. The Voyage AI client lives in `shared`, not here directly — this feature imports it, the same client `03-vector-store-retrieval.md` imports for embedding questions at query time.

## Goal
Split ingested documents into chunks and generate an embedding per chunk via Voyage AI, producing records ready for `03-vector-store-retrieval.md` to index into Weaviate.

## Functional Requirements
- FR-1: Read `Document` records where `content_hash` differs from `chunked_content_hash` (covers documents never chunked, and documents whose content changed since they were last chunked)
- FR-2: Split each document's text primarily at heading boundaries (`##`, falling back to `###` when a section still exceeds the max chunk size) — never splitting inside a fenced code block or table row
- FR-2a: For documents with no heading structure (or too few headings to bound chunk size), fall back to paragraph-boundary splitting up to the same max chunk size
- FR-2b: If a `###` subsection is itself still oversized: when it's a table (large field-description tables in the API reference run well past the cap on their own), split by rows into groups that fit the cap, repeating the header row in each group; otherwise (plain prose), fall back to paragraph-boundary splitting per FR-2a
- FR-3: Generate an embedding per chunk via the Voyage AI API
- FR-4: Store each chunk as a `Chunk` record (text, embedding, chunk index, source document reference)
- FR-5: Retry up to 3 times on Voyage AI rate-limit or timeout errors, waiting 2^attempt seconds between each (2s, 4s, 8s)
- FR-6: Run as a Celery task, chained after ingestion for each document
- FR-7: Append `chunk_duration_ms`, `chunk_count`, `embed_duration_ms`, and `total_duration_ms` to the `DocumentProcessingLog` row created during ingestion for that document

## Non-Functional Constraints
- No paid service beyond Voyage AI's free tier
- Idempotent: reprocessing a document replaces its existing `Chunk` records rather than duplicating them
- Runs fully inside Docker Compose
- Max chunk size: 1000 tokens. Measured against real Twitch reference-page endpoints — most single-endpoint sections run 800-1400 tokens, so an 800 cap would sub-split nearly everything for no benefit, while 1000 keeps simpler endpoints whole

## Interfaces

### Document record (Postgres) — field owned by this feature
`chunked_content_hash` is added to the `Document` record defined in `01-doc-ingestion.md`. This feature sets it to the document's `content_hash` once chunking and embedding succeed. When a document is reprocessed (FR-1), its existing `Chunk` records are deleted and regenerated from scratch — no partial/incremental re-chunking.

### Chunk record (Postgres, staging for vector store indexing)
```
Chunk
- id: UUID
- document_id: FK -> Document
- chunk_index: int
- text: text
- embedding: float[1024]     # voyage-3.5
- created_at: datetime
```

## Acceptance Criteria
- Each ingested document produces one or more `Chunk` records with a populated embedding
- No chunk boundary falls inside a fenced code block
- Re-running this stage on the same document replaces its chunks rather than duplicating them
- The document's `DocumentProcessingLog` row has `chunk_duration_ms`, `chunk_count`, `embed_duration_ms`, and `total_duration_ms` filled in

## Out of Scope
- Writing chunks into Weaviate (`03-vector-store-retrieval.md`)
- Embedding user questions at query time (`03-vector-store-retrieval.md`)
- Chunking strategies beyond fixed-size, code-block-aware splitting (e.g. semantic chunking) — candidate future improvement

## Open Questions
None currently.
