# 00 — Project Overview

## Name
Twitch Docs RAG (working title)

## Purpose
Two audiences:
1. Portfolio piece demonstrating the same architecture kapa.ai builds in production (RAG over technical documentation), for a job application.
2. Standalone tool: an "Ask AI" assistant over Twitch Developer documentation, which Twitch does not currently offer.

## Problem
Twitch developers search scattered docs (API reference, EventSub, Extensions, IRC) manually across multiple pages, with no natural-language interface — unlike Docker, Stripe, or Grafana, who already ship this via kapa or similar tools.

## Goals
- Ingest Twitch Developer documentation into a searchable knowledge base
- Answer natural-language questions with citations drawn from that documentation
- Run entirely locally via `docker-compose up`, no paid APIs required for the MVP
- Demonstrate the same building blocks kapa.ai uses: RAG engine, client integration surface, data ingestion pipeline

## Non-goals (MVP)
- Multi-tenant / multi-customer support
- Authentication or user accounts
- Production-grade scaling or high availability
- Documentation sources beyond Twitch Developer docs
- Fine-tuning or training custom models
- Analytics dashboard (stretch — separate feature doc)
- Embeddable widget SDK (stretch — separate feature doc)

## Success Criteria (MVP done when)
- A user can ask a question about the Twitch API, EventSub, or Extensions in a chat UI
- The system returns an answer grounded in retrieved doc chunks, with source links
- The full stack starts with one `docker-compose up`, no manual setup steps
- A fixed test set of ~15 known Q&A pairs is manually reviewed as accurate and grounded

## Architecture
- `01-architecture.md` — stack decisions and data flow

## Definition of Done
- `02-definition-of-done.md` — the completion bar every feature is held to, on top of its own Acceptance Criteria

## Features (MVP)
- Doc Ingestion — `features/01-doc-ingestion.md`
- Chunking & Embedding — `features/02-chunking-embedding.md`
- Vector Store & Retrieval — `features/03-vector-store-retrieval.md`
- LLM Integration — `features/04-llm-integration.md`
- RAG Answer API — `features/05-rag-answer-api.md`
- Chat Frontend — `features/06-chat-frontend.md`

## Features (Stretch)
- Analytics Tracking — `features/07-analytics-tracking.md`
- Embeddable Widget SDK — `features/08-embeddable-widget-sdk.md`
