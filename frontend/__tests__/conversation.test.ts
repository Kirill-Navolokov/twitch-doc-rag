import { describe, expect, it } from "vitest";

import { conversationReducer } from "@/lib/conversation";

import type { Citation } from "@/lib/askQuestion";
import type { Exchange } from "@/lib/conversation";

const CITATION: Citation = {
  source_url: "https://dev.twitch.tv/docs/authentication/",
  title: "Authentication",
  chunk_index: 3,
  score: 0.94,
};

function started(question = "How do I get an app access token?"): Exchange[] {
  return conversationReducer([], { type: "ask", id: 0, question });
}

describe("conversationReducer", () => {
  it("appends a streaming exchange for a new question", () => {
    expect(started()).toEqual([
      {
        id: 0,
        question: "How do I get an app access token?",
        citations: [],
        answer: "",
        status: "streaming",
      },
    ]);
  });

  it("appends every token rather than replacing the answer", () => {
    const withTokens = ["Use ", "the ", "token"].reduce(
      (state, text) => conversationReducer(state, { type: "token", id: 0, text }),
      started(),
    );

    expect(withTokens[0].answer).toBe("Use the token");
  });

  it("attaches citations without touching the answer", () => {
    const state = conversationReducer(started(), {
      type: "citations",
      id: 0,
      citations: [CITATION],
    });

    expect(state[0].citations).toEqual([CITATION]);
    expect(state[0].answer).toBe("");
  });

  it("replaces the answer with the fallback text", () => {
    const state = conversationReducer(started(), {
      type: "fallback",
      id: 0,
      text: "Sorry, we can't find any information related to your request",
    });

    expect(state[0]).toMatchObject({
      status: "fallback",
      answer: "Sorry, we can't find any information related to your request",
    });
  });

  it("keeps the part-rendered answer and citations when an error interrupts the stream", () => {
    const streaming = conversationReducer(
      conversationReducer(started(), { type: "citations", id: 0, citations: [CITATION] }),
      { type: "token", id: 0, text: "Request a token" },
    );

    const state = conversationReducer(streaming, {
      type: "error",
      id: 0,
      message: "generation failed",
    });

    expect(state[0]).toMatchObject({
      status: "error",
      error: "generation failed",
      answer: "Request a token",
      citations: [CITATION],
    });
  });

  it("ignores an event addressed to an exchange that is no longer in the history", () => {
    const state = started();

    expect(conversationReducer(state, { type: "token", id: 99, text: "stray" })).toEqual(state);
  });

  it("routes an event to its own exchange, not the newest one", () => {
    const two = conversationReducer(
      conversationReducer(started("first"), { type: "done", id: 0 }),
      { type: "ask", id: 1, question: "second" },
    );

    const state = conversationReducer(two, { type: "token", id: 0, text: "late" });

    expect(state[0].answer).toBe("late");
    expect(state[1].answer).toBe("");
  });
});
