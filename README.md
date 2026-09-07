# Twitch Docs RAG

An "Ask AI" assistant over the Twitch Developer documentation (API reference, EventSub, Extensions) — a RAG system built to demonstrate the same architecture kapa.ai builds in production, and to fill a gap Twitch's own docs don't currently cover.

Ask a natural-language question, get an answer grounded in the actual docs, with source citations. Runs entirely locally via `docker-compose up`, no paid APIs required.

## Docs

- [`docs/00-overview.md`](docs/00-overview.md) — purpose, goals, non-goals, success criteria
- [`docs/01-architecture.md`](docs/01-architecture.md) — stack, components, data flow
- [`docs/02-definition-of-done.md`](docs/02-definition-of-done.md) — completion bar for every feature
- [`docs/features/`](docs/features) — per-feature requirements (doc ingestion, chunking & embedding, vector store & retrieval, LLM integration, RAG answer API, chat frontend)

## Architecture (at a glance)

- **`worker`** — Django, Celery-only. Ingests Twitch docs, chunks and embeds them, writes to the vector store.
- **`api`** — Django + DRF. Retrieves relevant chunks, calls the LLM, serves the answer endpoint.
- **`shared`** — plain Python package (Postgres models, Voyage AI client, Weaviate client) imported by both `worker` and `api`.
- **`frontend`** — Next.js chat UI.
- **Weaviate** — vector store. **Postgres** — doc/chunk metadata. **RabbitMQ** — Celery broker.

See [`docs/01-architecture.md`](docs/01-architecture.md) for the full data flow.

## Status

Project scaffolding in progress. This section will be updated as each feature lands.

- [ ] Doc Ingestion
- [ ] Chunking & Embedding
- [ ] Vector Store & Retrieval
- [ ] LLM Integration
- [ ] RAG Answer API
- [ ] Chat Frontend

## Running locally

```
docker-compose up
```

(Compose setup lands with the first service implementation.)
