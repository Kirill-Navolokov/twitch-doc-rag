import { describe, expect, it, vi } from "vitest";

import { createSseParser } from "@/lib/sse";

import type { SseEvent } from "@/lib/sse";

function collect(): { events: SseEvent[]; push: (text: string) => void } {
  const events: SseEvent[] = [];
  const parser = createSseParser((event) => events.push(event));
  return { events, push: (text) => parser.push(text) };
}

describe("createSseParser", () => {
  it("parses one complete event in one chunk", () => {
    const { events, push } = collect();

    push('event: token\ndata: {"text": "hello"}\n\n');

    expect(events).toEqual([{ event: "token", data: { text: "hello" } }]);
  });

  it("parses several complete events arriving in a single chunk", () => {
    const { events, push } = collect();

    push(
      'event: citations\ndata: {"citations": []}\n\n' +
        'event: token\ndata: {"text": "a"}\n\n' +
        'event: token\ndata: {"text": "b"}\n\n' +
        "event: done\ndata: {}\n\n",
    );

    expect(events.map((event) => event.event)).toEqual([
      "citations",
      "token",
      "token",
      "done",
    ]);
    expect(events[1].data).toEqual({ text: "a" });
  });

  it("reassembles one event split across three chunks", () => {
    const { events, push } = collect();

    push("event: to");
    push('ken\ndata: {"te');
    expect(events).toEqual([]);

    push('xt": "split"}\n\n');

    expect(events).toEqual([{ event: "token", data: { text: "split" } }]);
  });

  it("holds a trailing partial event until a later chunk completes it", () => {
    const { events, push } = collect();

    push('event: token\ndata: {"text": "first"}\n\nevent: token\ndata: {"text": "sec');
    expect(events).toEqual([{ event: "token", data: { text: "first" } }]);

    push('ond"}\n\n');

    expect(events).toEqual([
      { event: "token", data: { text: "first" } },
      { event: "token", data: { text: "second" } },
    ]);
  });

  it("keeps a CRLF pair intact when it straddles two chunks", () => {
    const { events, push } = collect();

    push('event: token\r\ndata: {"text": "crlf"}\r\n\r');
    expect(events).toEqual([]);

    push("\n");

    expect(events).toEqual([{ event: "token", data: { text: "crlf" } }]);
  });

  it("skips comment lines and blocks that carry no data field", () => {
    const { events, push } = collect();

    push(': keep-alive\n\nevent: ping\n\nevent: done\ndata: {}\n\n');

    expect(events).toEqual([{ event: "done", data: {} }]);
  });

  it("does not re-emit an event once its block has been consumed", () => {
    const onEvent = vi.fn();
    const parser = createSseParser(onEvent);

    parser.push("event: done\ndata: {}\n\n");
    parser.push('event: token\ndata: {"text": "x"}\n\n');

    expect(onEvent).toHaveBeenCalledTimes(2);
  });
});
