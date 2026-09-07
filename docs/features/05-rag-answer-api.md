# Feature 05 — RAG Answer API

## Owning Project
`api`

## Goal
Expose the endpoint the frontend calls to ask a question, orchestrating retrieval and generation into one grounded, cited answer.

## Functional Requirements
- FR-1: Expose an HTTP endpoint accepting a user question and returning an answer with citations
- FR-2: Call `03-vector-store-retrieval.md`'s `retrieve()` to get the top-k chunks for the question
- FR-3: If no retrieved chunk meets a minimum relevance threshold, skip generation entirely and return a fixed "not found in the docs" response — prevents the model from answering outside the supplied context
- FR-4: Otherwise, call `04-llm-integration.md`'s `select_model()` then `generate()` with the question and retrieved chunks
- FR-5: Stream the generated answer back to the frontend token-by-token as it's produced
- FR-6: Send the citations list as soon as retrieval completes, before generation begins — not after
- FR-7: On a generation failure surfaced by `04-llm-integration.md`, return a clean error response rather than a raw exception
- FR-8: Log each query at INFO level via the application logger (runtime log, not persisted to the database): question, timestamp, retrieved chunk ids and scores, whether the no-relevant-docs fallback was triggered, and total response time
- FR-9: Provide a calibration command that determines the FR-3 threshold empirically, rather than leaving it a guess

  **Context:** FR-3's threshold can't be reasoned about in the abstract — it depends on the actual score distribution `relativeScoreFusion` (per `03-vector-store-retrieval.md`) produces on real embedded data, which varies with the corpus itself. Set it too low and the system risks confidently hallucinating answers to unrelated questions — a worse failure mode for this project than occasionally being overly cautious. Set it too high and it refuses questions it could have answered. Neither is discoverable by reasoning alone; both need to be observed against real retrieval scores. This command makes that observation repeatable, and rerunnable whenever the corpus or retrieval config changes — not just a one-time manual guess.

  The command reads a labeled test-question file (`docs/calibration_questions.json`, user-maintained, same pattern as `doc_urls.json`), runs each question through `03-vector-store-retrieval.md`'s `retrieve()`, and reports the top score per question grouped by its expected label. The developer reads that report and picks the threshold by hand — the command surfaces the data, it doesn't choose the number itself.

## Non-Functional Constraints
- Runs fully inside Docker Compose
- No paid service beyond what `03` and `04` already depend on
- Streaming works end-to-end (backend to frontend), not buffered until the full answer is ready

## Interfaces

### Endpoint
```
POST /api/ask
Request: { "question": string }

Response: Server-Sent Events (text/event-stream) over one open connection —
not a single object returned at the end. Events, in order:

  event: citations
  data: { "citations": [{source_url, title, chunk_index, score}] }
  # sent once, right after retrieval — known before generation starts

  event: token
  data: { "text": string }
  # sent repeatedly, once per token, as the model streams its answer

  event: done
  data: {}
  # closes the stream

If FR-3's fallback triggers, the citations/token/done sequence is skipped
entirely in favor of a single event:

  event: fallback
  data: { "text": "Sorry, we can't find any information related to your request" }

If generation fails after retries (FR-7):

  event: error
  data: { "message": string }
```

### Query log (runtime, INFO level)
Emitted via the standard application logger — not a database table, not queryable after the fact except through log aggregation/search on the log stream itself.
```
logger.info(
    "rag_query",
    question=question,
    retrieved_chunks=[{"chunk_id": ..., "score": ...}, ...],
    fallback_triggered=bool,
    response_time_ms=int,
)
```

### Calibration test set (static config)
```
docs/calibration_questions.json
[]
```
User-maintained. Each entry: `{ "question": string, "expected": "in_scope" | "out_of_scope" }`

### Calibration command
```
python manage.py calibrate_threshold
  -> runs retrieve() for every question in the test set
  -> reports the top score per question, grouped by expected label
```

## Acceptance Criteria
- A question with clearly relevant docs returns a streamed, cited answer grounded in the retrieved chunks
- A question unrelated to Twitch returns the fixed fallback response, not a hallucinated answer
- Every request produces one `rag_query` INFO-level log entry, regardless of outcome (success, fallback, or error)
- A simulated generation failure returns a clean error, not a raw exception or a hung stream
- Running the calibration command against a populated test-question file reports a score for every question, clearly grouped by in-scope vs. out-of-scope, readable enough for a human to pick a threshold from it

## Out of Scope
- The chat UI itself (`06-chat-frontend.md`)
- Retrieval and generation logic themselves (`03-vector-store-retrieval.md`, `04-llm-integration.md`)
- Authentication or per-user rate limiting (no accounts in MVP scope, per `00-overview.md`)

## Open Questions
None currently.

## Fallback Response
"Sorry, we can't find any information related to your request"
