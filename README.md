# Twitch Docs RAG

An "Ask AI" assistant over the [Twitch Developer documentation](https://dev.twitch.tv/docs/api/) — a
retrieval-augmented generation system built to demonstrate the architecture kapa.ai runs in
production, and to fill a gap Twitch's own docs don't currently cover.

Ask a natural-language question, get an answer grounded in the actual documentation, with the source
passages it was drawn from. The whole stack runs locally on one `docker compose up`, on free API
tiers only.

## How it works

**Ingestion** (offline, `worker`) — fetch each configured doc URL → extract the page's main content
as markdown → split it at heading boundaries, never through a code block or table row → embed each
chunk via Voyage AI → index into Weaviate. Every stage is idempotent and re-runnable: unchanged
pages are skipped by content hash, reprocessing replaces rather than duplicates.

**Query** (online, `api` → `frontend`) — embed the question with the same model used at ingestion →
hybrid search (BM25 + vector, `relativeScoreFusion`) for the top 7 passages → if nothing clears the
relevance threshold, return a fixed "not in the docs" answer instead of guessing → otherwise send
the question plus those passages to Groq with instructions to answer only from them → stream the
answer back token by token over SSE, with citations sent first.

```
Twitch docs → worker (fetch → chunk → embed → index) → Weaviate
                                                          ↓
              browser → frontend → api (retrieve → generate) → Groq
```

## Status: MVP complete

| Feature | What it does |
|---|---|
| [Doc Ingestion](docs/features/01-doc-ingestion.md) | Fetches and extracts doc pages into Postgres, rate-limited and idempotent |
| [Chunking & Embedding](docs/features/02-chunking-embedding.md) | Heading-aware splitting (code blocks and table rows stay intact) + Voyage AI embeddings |
| [Vector Store & Retrieval](docs/features/03-vector-store-retrieval.md) | Weaviate indexing and hybrid BM25+vector search |
| [LLM Integration](docs/features/04-llm-integration.md) | Groq generation behind a provider-swappable seam, with streaming and retries |
| [RAG Answer API](docs/features/05-rag-answer-api.md) | `POST /api/ask` over Server-Sent Events, with a calibrated relevance gate |
| [Chat Frontend](docs/features/06-chat-frontend.md) | Next.js chat UI — citations first, then the answer streaming in |

**Corpus**: 13 Twitch API reference pages → 75 indexed chunks. EventSub and Extensions pages are
left out for now to stay inside Voyage AI's free tier (3 requests/minute without a payment method on
file) — widening the corpus is just adding URLs to `docs/doc_urls.json` and re-running ingestion.

**Relevance threshold**: `0.90`, picked from real data rather than guessed. A 20-question labeled
set (10 in-scope, 10 out-of-scope) run through `calibrate_threshold` showed in-scope questions
scoring 0.94–1.00 and out-of-scope ones topping out at 0.89 — see
[`docs/calibration_questions.json`](docs/calibration_questions.json).

## Stack

- **`worker`** — Django + Celery, no HTTP server. Owns ingestion, chunking, embedding, and vector
  indexing. Sole owner of database migrations.
- **`api`** — Django + DRF. Owns retrieval, model selection, generation, and the SSE answer endpoint.
- **`shared`** — plain Python package (Postgres models, Voyage AI client, Weaviate client), installed
  as an editable dependency by both, so ingestion-time and query-time embedding are the same code.
- **`frontend`** — Next.js 16 / React 19 / TypeScript / Tailwind, with a hand-rolled SSE parser
  (the browser's `EventSource` can't POST).
- **Weaviate** vector store · **Postgres** doc + chunk records · **RabbitMQ** Celery broker.
- **Voyage AI** `voyage-3.5` embeddings (1024-dim) · **Groq** `openai/gpt-oss-120b` generation.

## Docs

- [`docs/00-overview.md`](docs/00-overview.md) — purpose, goals, non-goals, success criteria
- [`docs/01-architecture.md`](docs/01-architecture.md) — stack decisions, components, data flow
- [`docs/02-definition-of-done.md`](docs/02-definition-of-done.md) — the bar every feature was held to
- [`docs/features/`](docs/features) — per-feature requirements, written before each was built

## Running locally

```
cp .env.example .env      # optional — compose falls back to local-development defaults
docker compose up
```

Brings up `postgres`, `rabbitmq`, `weaviate`, the Celery `worker` (which applies migrations on
start), `api` on port 8000 serving `POST /api/ask`, and the `frontend` chat UI on port 3000.

Chunking and embedding need a Voyage AI key (free tier), and answering needs a Groq key (free
tier), both in `.env`:

```
VOYAGE_API_KEY=your-key
GROQ_API_KEY=your-key
```

`GROQ_MODEL` defaults to `openai/gpt-oss-120b`; set it in `.env` to switch models.

Trigger a doc ingestion run over the URLs listed in `docs/doc_urls.json` — each successfully
fetched page is chunked and embedded straight after:

```
docker compose exec worker python manage.py run_ingestion
```

Re-chunk every document whose text changed since it was last chunked (also useful after a change
to the chunking algorithm):

```
docker compose exec worker python manage.py run_chunking
```

Index every chunk that isn't in Weaviate yet (chunking chains this automatically; the command is
the catch-up pass for chunks whose indexing attempt failed):

```
docker compose exec worker python manage.py run_indexing
```

Check what a question retrieves, with hybrid relevance scores and source URLs:

```
docker compose exec api python manage.py retrieve_query "How do I get an app access token?"
```

Answer a question from those chunks, printing the citations first (add `--stream` to watch the
answer arrive token by token):

```
docker compose exec api python manage.py generate_answer "How do I get an app access token?"
```

Ask in the browser at <http://localhost:3000> — the retrieved passages appear first, each with its
source and match score, then the answer streams in under them. History lives in the page for the
session only and is gone on reload.

The page calls `api` straight from the browser, at `NEXT_PUBLIC_API_URL` (default
`http://localhost:8000`). Set it in `.env` only if `api` is published somewhere else; it has to be
an address the browser can reach, so never the compose-internal `http://api:8000`.

Ask over HTTP — the answer streams back as Server-Sent Events (`citations`, then one `token` per
token, then `done`; a question nothing relevant was retrieved for gets a single `fallback` event):

```
curl -N -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" -H "Accept: text/event-stream" \
  -d '{"question": "How do I get an app access token?"}'
```

That fallback fires when no retrieved chunk scores above `RELEVANCE_THRESHOLD` (default `0.90`, set
it in `.env`). Re-derive the number from real data whenever the corpus or retrieval config changes:
label questions in `docs/calibration_questions.json`
(`{"question": ..., "expected": "in_scope" | "out_of_scope"}`), then read the top score each one
retrieves, grouped by label, and pick a value in the gap between the two groups:

```
docker compose exec api python manage.py calibrate_threshold
```

The command paces itself at one question per 20s to stay under Voyage AI's free-tier rate limit, so
a 20-question set takes about 6 minutes.
