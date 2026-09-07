# Feature 06 — Chat Frontend

## Owning Project
`frontend` (Next.js) — separate from the three Python projects (`worker`, `api`, `shared`), calls `api` over HTTP

## Goal
A single-page chat UI where a user asks a question and sees the streamed, cited answer from `05-rag-answer-api.md`.

## Functional Requirements
- FR-1: Provide a text input and submit action for asking a question
- FR-2: On submit, call `POST /api/ask` and open the SSE connection
- FR-3: Render the citations as soon as the `citations` event arrives — before any answer text appears. For each citation, show which chunk matched (source and title) and its retrieval score
- FR-4: Render the answer incrementally as `token` events arrive, appending each to the visible message
- FR-5: On a `fallback` event, render it as the complete answer (no streaming — it's a single fixed message)
- FR-6: On an `error` event, render a clear error message rather than a blank or hung state
- FR-7: Show a scrollable history of question/answer pairs for the current session (no persistence across reloads, no accounts per `00-overview.md`)
- FR-8: Disable the input while a request is in flight, to prevent overlapping queries

## Non-Functional Constraints
- No paid service required
- Runs fully inside Docker Compose
- No browser storage (localStorage/sessionStorage) — session state lives in React state only, and is expected to be lost on reload

## Interfaces

### Pages / Components
- Single page (`/`)
- `MessageList` — renders the session's question/answer history
- `MessageInput` — text field and submit action
- `CitationsList` — rendered per-answer, above the streamed text; shows each matched chunk's source, title, and retrieval score

### Consumes
`POST /api/ask` (SSE), as defined in `05-rag-answer-api.md` — `citations` → `token`* → `done`, or `fallback`, or `error`

## Acceptance Criteria
- Submitting a question shows citations first — including each matched chunk's score — then the answer streaming in token by token
- An out-of-scope question shows the fixed fallback message
- A simulated backend error shows a clear message, and the input re-enables afterward
- Multiple questions in one session appear as a scrollable history

## Out of Scope
- Backend API logic (`05-rag-answer-api.md`)
- Authentication, accounts, multi-user support
- Frontend analytics/telemetry (`07-analytics-tracking.md`, stretch)
- Persisting chat history across page reloads

## Open Questions
None currently.
