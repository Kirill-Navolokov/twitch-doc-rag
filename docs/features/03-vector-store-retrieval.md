# Feature 03 — Vector Store & Retrieval

## Owning Project
Split across both, unlike the other features:
- **`worker`**: FR-1, FR-2, FR-3 (indexing — the write side)
- **`api`**: FR-4, FR-5, FR-6, FR-7 (`retrieve()` — the read side, called by `05-rag-answer-api.md`)

Both the Voyage AI client and the Weaviate client live in `shared`, not duplicated in each project — `worker` uses them to write, `api` uses them to read.

## Goal
Index chunks into Weaviate, and serve retrieval at query time: given a user's question, return the most relevant chunks with enough metadata to cite their source.

## Functional Requirements
- FR-1: Read `Chunk` records not yet indexed in Weaviate (or belonging to a document that was just reprocessed by `02-chunking-embedding.md`)
- FR-2: Write each chunk's text, embedding, and metadata (source URL, title, chunk index) into Weaviate
- FR-3: When a document is reprocessed, delete its previous Weaviate objects before inserting the new set — no partial reindex, mirroring the full-resync behavior in `02-chunking-embedding.md`
- FR-4: Given a user question, embed it via the same Voyage AI model used during ingestion
- FR-5: Query Weaviate using hybrid search (BM25 + vector) for the top-k most relevant chunks, using `relativeScoreFusion` (normalizes both scores to a comparable 0-1 range, which is what makes the FR-3 fallback threshold in `05-rag-answer-api.md` a meaningful, stable number rather than an arbitrary one)
- FR-6: Return each retrieved chunk with its source URL, title, and relevance score, for use in citations
- FR-7: Top-k defaults to 7. Hybrid weighting (alpha) defaults to 0.5 — Weaviate's own default, an even split between BM25 and vector — kept configurable but not tuned away from that default without real usage data
- FR-8: Run as a Celery task, chained after `02-chunking-embedding.md` completes for a document. The FR-1 "not yet indexed" condition is the actual trigger logic either way, so if a chained indexing attempt fails (e.g. Weaviate briefly unreachable), the chunk simply stays flagged unindexed and gets picked up by the next run — no separate retry system needed

## Non-Functional Constraints
- Runs fully inside Docker Compose (Weaviate as a service)
- No paid service required
- Idempotent indexing: reindexing a document produces no duplicate or stale objects

## Interfaces

### Weaviate schema
```
DocChunk
- text: text
- source_url: text
- title: text
- chunk_index: int
- document_id: text     # cross-reference to Postgres Document.id
- vector: float[1024]    # supplied directly (voyage-3.5 output) — vectorizer: none.
                         # Weaviate must NOT be configured with its own embedding module;
                         # it only stores and searches vectors computed in 02-chunking-embedding.md
```

### Retrieval
```
retrieve(question: str, top_k: int = 5) -> list[RetrievedChunk]

RetrievedChunk:
- text: str
- source_url: str
- title: str
- chunk_index: int
- score: float
```

## Acceptance Criteria
- A query for a known question returns chunks from the expected source document among the top results
- Reindexing a changed document leaves no stale or duplicate objects from its previous chunk set
- `retrieve()` results are ranked by hybrid relevance and each includes a usable `source_url`

## Out of Scope
- Generating the final answer or calling the LLM (`05-rag-answer-api.md`)
- Embedding generation logic itself (reuses the Voyage AI client from `02-chunking-embedding.md`, not reimplemented here)
- Chunking (`02-chunking-embedding.md`)

## Open Questions
None currently.
