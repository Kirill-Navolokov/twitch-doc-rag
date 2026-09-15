import { createSseParser } from "./sse";

import type { SseEvent } from "./sse";

export interface Citation {
  source_url: string;
  title: string;
  chunk_index: number;
  score: number;
}

export interface AskHandlers {
  onCitations: (citations: Citation[]) => void;
  onToken: (text: string) => void;
  onDone: () => void;
  onFallback: (text: string) => void;
  onError: (message: string) => void;
}

// Read through Next.js's NEXT_PUBLIC_ inlining, so it must stay a literal property access. The
// default is the host-published port of the api container: this fetch runs in the browser, outside
// the compose network, so the internal hostname "api" would not resolve.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const MALFORMED = "The API sent an answer in a shape this app does not understand.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readText(data: unknown, field: "text" | "message"): string {
  if (!isRecord(data) || typeof data[field] !== "string") throw new Error(MALFORMED);
  return data[field];
}

function readCitation(value: unknown): Citation {
  if (
    !isRecord(value) ||
    typeof value.source_url !== "string" ||
    typeof value.title !== "string" ||
    typeof value.chunk_index !== "number" ||
    typeof value.score !== "number"
  ) {
    throw new Error(MALFORMED);
  }
  return {
    source_url: value.source_url,
    title: value.title,
    chunk_index: value.chunk_index,
    score: value.score,
  };
}

function readCitations(data: unknown): Citation[] {
  if (!isRecord(data) || !Array.isArray(data.citations)) throw new Error(MALFORMED);
  return data.citations.map(readCitation);
}

function deliver(event: SseEvent, handlers: AskHandlers): void {
  switch (event.event) {
    case "citations":
      handlers.onCitations(readCitations(event.data));
      return;
    case "token":
      handlers.onToken(readText(event.data, "text"));
      return;
    case "done":
      handlers.onDone();
      return;
    case "fallback":
      handlers.onFallback(readText(event.data, "text"));
      return;
    case "error":
      handlers.onError(`The answer couldn't be completed: ${readText(event.data, "message")}`);
      return;
  }
}

export async function askQuestion(
  question: string,
  handlers: AskHandlers,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch {
    if (signal.aborted) return;
    handlers.onError(`Couldn't reach the docs API at ${API_URL}. Check that it is running.`);
    return;
  }

  if (!response.ok || !response.body) {
    handlers.onError(`The docs API answered with status ${response.status}. Ask again in a moment.`);
    return;
  }

  const reader = response.body.getReader();
  // { stream: true } keeps a multi-byte character split across two chunks intact.
  const decoder = new TextDecoder();
  const parser = createSseParser((event) => deliver(event, handlers));

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      parser.push(decoder.decode(value, { stream: true }));
    }
  } catch (error) {
    if (signal.aborted) return;
    const detail = error instanceof Error ? error.message : String(error);
    handlers.onError(`The answer stopped before it finished: ${detail}`);
  }
}
