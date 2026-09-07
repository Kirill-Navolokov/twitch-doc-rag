# Feature 04 — LLM Integration

## Owning Project
`api`. Not used by `worker` — Groq is only called at query time.

## Goal
Provide a single interface for requesting a generation from an LLM, shaped so multiple providers/models could be resolved by task type later, while the MVP always resolves to one configured Groq model.

## Functional Requirements
- FR-1: Define a `model-selector` interface: given a request descriptor, resolve a provider + model. MVP always returns the same Groq provider/model regardless of input — no actual routing logic is implemented, only the interface shape
- FR-2: Define a `generate` interface: given a resolved model, a question, and retrieved chunks, call the provider and return the generated answer
- FR-3: Support streaming the response back token-by-token
- FR-4: Retry up to 3 times on rate-limit or timeout errors from the provider, waiting 2^attempt seconds between each (2s, 4s, 8s)
- FR-5: On failure after retries are exhausted, surface a clear error (not a raw provider exception) so the caller (`05-rag-answer-api.md`) can degrade gracefully
- FR-6: Own the prompt template — the fixed instructions telling the model to answer only from the supplied chunks and to cite sources. The caller supplies only the question and retrieved chunks; this feature assembles the final prompt

## Non-Functional Constraints
- No paid service required (Groq free tier)
- Swappable providers without changing any caller code — `model-selector` is the seam
- Runs fully inside Docker Compose (an outbound API call, no local model to run)

## Interfaces

```
select_model(task: TaskDescriptor) -> ModelHandle
  # MVP: always returns the single configured Groq model, regardless of `task`

TaskDescriptor:
- kind: str = "answer_generation"   # placeholder; only value used in MVP

ModelHandle:
- provider: str   # "groq" for MVP
- model_id: str

generate(model: ModelHandle, question: str, chunks: list[RetrievedChunk], stream: bool = True) -> GenerationResult

GenerationResult:
- text: str
- citations: list[{source_url, title, chunk_index, score}]   # score and chunk_index carried through from RetrievedChunk, for display in the frontend
```

## Acceptance Criteria
- Calling `generate()` with a real question and retrieved chunks returns an answer plus a citations list matching the chunks used
- `select_model()` always returns the same Groq model in MVP, regardless of the `TaskDescriptor` passed
- A simulated provider timeout or rate-limit triggers the retry logic before surfacing a clean error to the caller

## Out of Scope
- Actual multi-model routing logic (interface shape only — see `01-architecture.md` non-goals)
- Embedding generation (Voyage AI, owned by `02-chunking-embedding.md` and `03-vector-store-retrieval.md`)
- Retrieval itself — chunks arrive already retrieved (`03-vector-store-retrieval.md`); this feature only turns them into a prompt and calls the model
- Orchestrating the end-to-end request/response cycle (`05-rag-answer-api.md`)

## Open Questions
None currently.

## Follow-up Validation
Once `05-rag-answer-api.md`'s endpoint exists and returns real answers over real retrieved chunks, test and iterate the exact prompt template wording against actual output quality — not decidable in the abstract, needs real generations to evaluate against.

## Configured Model
`openai/gpt-oss-120b` — best fit among Groq's free/developer-tier models. Both Llama models moved to Enterprise-only pricing, ruling them out. Groq's `compound`/`compound-mini` systems were also considered and ruled out: they run autonomous web search and code execution, which conflicts with FR-6's constraint that the model answers only from the chunks it's given. `openai/gpt-oss-120b` is the largest plain model still available, with reasoning capability suited to grounded QA; `openai/gpt-oss-20b` is the fallback if rate limits become an issue during development.
