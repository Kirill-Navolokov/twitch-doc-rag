import { afterEach, describe, expect, it, vi } from "vitest";

import { API_URL, askQuestion } from "@/lib/askQuestion";

import type { AskHandlers } from "@/lib/askQuestion";

const CITATIONS_EVENT =
  'event: citations\ndata: {"citations": [{"source_url": "https://dev.twitch.tv/docs/authentication/", "title": "Authentication", "chunk_index": 3, "score": 0.94}]}\n\n';

function handlers(): AskHandlers & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    onCitations: vi.fn(() => calls.push("citations")),
    onToken: vi.fn(() => calls.push("token")),
    onDone: vi.fn(() => calls.push("done")),
    onFallback: vi.fn(() => calls.push("fallback")),
    onError: vi.fn(() => calls.push("error")),
  };
}

function streamOf(chunks: Array<string | Uint8Array>, failWith?: Error): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  // Enqueued one pull at a time so a failure lands after the earlier chunks have been read, the way
  // a connection dropping mid-answer does.
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index === chunks.length) {
        if (failWith) controller.error(failWith);
        else controller.close();
        return;
      }
      const chunk = chunks[index];
      index += 1;
      controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
    },
  });
}

function stubFetch(
  respond: (input: string | URL | Request, init?: RequestInit) => Promise<Response>,
) {
  const spy = vi.fn(respond);
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("askQuestion", () => {
  it("posts the question as JSON to the configured API", async () => {
    const fetchSpy = stubFetch(async () => new Response(streamOf(["event: done\ndata: {}\n\n"])));

    await askQuestion("How do I get an app access token?", handlers(), new AbortController().signal);

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe(`${API_URL}/api/ask`);
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ question: "How do I get an app access token?" }));
    expect(API_URL).toBe("http://localhost:8000");
  });

  it("reports citations, then each token, then completion", async () => {
    stubFetch(async () =>
      new Response(
        streamOf([
          CITATIONS_EVENT,
          'event: token\ndata: {"text": "Use "}\n\nevent: token\ndata: {"text": "curl"}\n\n',
          "event: done\ndata: {}\n\n",
        ]),
      ),
    );
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.calls).toEqual(["citations", "token", "token", "done"]);
    expect(sink.onCitations).toHaveBeenCalledWith([
      {
        source_url: "https://dev.twitch.tv/docs/authentication/",
        title: "Authentication",
        chunk_index: 3,
        score: 0.94,
      },
    ]);
    expect(sink.onToken).toHaveBeenNthCalledWith(1, "Use ");
    expect(sink.onToken).toHaveBeenNthCalledWith(2, "curl");
  });

  it("decodes a multi-byte character split across two chunks", async () => {
    const frame = 'event: token\ndata: {"text": "a—b"}\n\n';
    const bytes = new TextEncoder().encode(frame);
    const boundary = bytes.indexOf(0xe2) + 1;
    stubFetch(async () =>
      new Response(streamOf([bytes.slice(0, boundary), bytes.slice(boundary)])),
    );
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.onToken).toHaveBeenCalledWith("a—b");
  });

  it("reports a fallback as the only event", async () => {
    stubFetch(async () =>
      new Response(
        streamOf([
          'event: fallback\ndata: {"text": "Sorry, we can\'t find any information related to your request"}\n\n',
        ]),
      ),
    );
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.calls).toEqual(["fallback"]);
    expect(sink.onFallback).toHaveBeenCalledWith(
      "Sorry, we can't find any information related to your request",
    );
  });

  it("reports an error that arrives as the first event", async () => {
    stubFetch(async () =>
      new Response(streamOf(['event: error\ndata: {"message": "groq is unavailable"}\n\n'])),
    );
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.calls).toEqual(["error"]);
    expect(sink.onError).toHaveBeenCalledWith(
      "The answer couldn't be completed: groq is unavailable",
    );
  });

  it("reports an error that interrupts an answer already streaming", async () => {
    stubFetch(async () =>
      new Response(
        streamOf([
          CITATIONS_EVENT,
          'event: token\ndata: {"text": "Request "}\n\n',
          'event: error\ndata: {"message": "stream closed"}\n\n',
        ]),
      ),
    );
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.calls).toEqual(["citations", "token", "error"]);
    expect(sink.onDone).not.toHaveBeenCalled();
  });

  it("reports a non-OK status through the same error path", async () => {
    stubFetch(async () => new Response('{"error": "question is required"}', { status: 400 }));
    const sink = handlers();

    await askQuestion("", sink, new AbortController().signal);

    expect(sink.calls).toEqual(["error"]);
    expect(sink.onError).toHaveBeenCalledWith(expect.stringContaining("status 400"));
  });

  it("reports an unreachable API through the same error path", async () => {
    stubFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.onError).toHaveBeenCalledWith(expect.stringContaining(API_URL));
  });

  it("reports a stream that breaks part-way through", async () => {
    stubFetch(async () =>
      new Response(
        streamOf(['event: token\ndata: {"text": "Use "}\n\n'], new Error("connection reset")),
      ),
    );
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.calls).toEqual(["token", "error"]);
    expect(sink.onError).toHaveBeenCalledWith(expect.stringContaining("stopped before it finished"));
  });

  it("stays silent when the request was cancelled on purpose", async () => {
    const controller = new AbortController();
    stubFetch(async () => {
      controller.abort();
      throw new DOMException("The operation was aborted.", "AbortError");
    });
    const sink = handlers();

    await askQuestion("q", sink, controller.signal);

    expect(sink.calls).toEqual([]);
  });

  it("rejects a citations payload that does not match the documented shape", async () => {
    stubFetch(async () =>
      new Response(streamOf(['event: citations\ndata: {"citations": [{"title": 7}]}\n\n'])),
    );
    const sink = handlers();

    await askQuestion("q", sink, new AbortController().signal);

    expect(sink.onCitations).not.toHaveBeenCalled();
    expect(sink.onError).toHaveBeenCalledWith(expect.stringContaining("does not understand"));
  });
});
