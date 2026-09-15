import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Page from "@/app/page";
import { askQuestion } from "@/lib/askQuestion";

import type { AskHandlers, Citation } from "@/lib/askQuestion";

vi.mock("@/lib/askQuestion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/askQuestion")>();
  return { ...actual, askQuestion: vi.fn() };
});

const CITATIONS: Citation[] = [
  {
    source_url: "https://dev.twitch.tv/docs/authentication/",
    title: "Authentication",
    chunk_index: 3,
    score: 0.94,
  },
  {
    source_url: "https://dev.twitch.tv/docs/api/get-started/",
    title: "Get Started",
    chunk_index: 0,
    score: 0.91,
  },
];

interface Stream {
  handlers: AskHandlers;
  finish: () => void;
}

let streams: Stream[] = [];

function latestStream(): Stream {
  const stream = streams.at(-1);
  if (!stream) throw new Error("askQuestion has not been called yet");
  return stream;
}

/** Drives the in-flight stream and lets React flush, without resolving askQuestion itself. */
async function emit(drive: (handlers: AskHandlers) => void): Promise<void> {
  await act(async () => {
    drive(latestStream().handlers);
  });
}

/** Ends the in-flight request the way askQuestion's promise resolving ends it in the browser. */
async function settle(): Promise<void> {
  await act(async () => {
    latestStream().finish();
  });
}

beforeEach(() => {
  streams = [];
  vi.mocked(askQuestion).mockImplementation(
    (_question, handlers) =>
      new Promise<void>((resolve) => {
        streams.push({ handlers, finish: resolve });
      }),
  );
});

async function ask(question: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByRole("textbox", { name: "Your question" }), question);
  await user.click(screen.getByRole("button", { name: /^ask/i }));
}

function questionInput(): HTMLElement {
  return screen.getByRole("textbox", { name: "Your question" });
}

describe("chat page", () => {
  it("FR-1: submits the typed question and shows it in the transcript", async () => {
    render(<Page />);

    await ask("How do I get an app access token?");

    expect(askQuestion).toHaveBeenCalledWith(
      "How do I get an app access token?",
      expect.anything(),
      expect.any(AbortSignal),
    );
    expect(screen.getByRole("heading", { name: "How do I get an app access token?" })).toBeVisible();
  });

  it("FR-2: opens one request per submitted question and clears the input", async () => {
    render(<Page />);

    await ask("How do I get an app access token?");

    expect(askQuestion).toHaveBeenCalledOnce();
    expect(questionInput()).toHaveValue("");
  });

  it("FR-3: shows each citation's source, title and score before any answer text", async () => {
    render(<Page />);
    await ask("How do I get an app access token?");

    await emit((handlers) => handlers.onCitations(CITATIONS));

    const passages = screen.getByRole("region", { name: "Retrieved passages" });
    expect(within(passages).getByRole("link", { name: "Authentication" })).toHaveAttribute(
      "href",
      "https://dev.twitch.tv/docs/authentication/",
    );
    expect(within(passages).getByText("dev.twitch.tv/docs/authentication")).toBeVisible();
    expect(within(passages).getByText("0.94")).toBeVisible();
    expect(within(passages).getByText("passage 3")).toBeVisible();
    expect(screen.getByText("Writing the answer")).toBeVisible();
  });

  it("FR-4: appends each token to the visible answer", async () => {
    render(<Page />);
    await ask("How do I get an app access token?");
    await emit((handlers) => handlers.onCitations(CITATIONS));

    await emit((handlers) => handlers.onToken("Request "));
    expect(screen.getByText("Request", { exact: false })).toBeVisible();

    await emit((handlers) => handlers.onToken("an app access token."));

    expect(screen.getByText("Request an app access token.")).toBeVisible();
  });

  it("FR-4: keeps every token when a burst of them arrives in one synchronous run", async () => {
    render(<Page />);
    await ask("How do I get an app access token?");

    const tokens = Array.from({ length: 200 }, (_, index) => `${index} `);
    await emit((handlers) => {
      for (const token of tokens) handlers.onToken(token);
    });

    expect(screen.getByText(tokens.join("").trim())).toBeVisible();
  });

  it("FR-5: renders the fallback as a complete answer", async () => {
    render(<Page />);
    await ask("What is the weather today?");

    await emit((handlers) =>
      handlers.onFallback("Sorry, we can't find any information related to your request"),
    );
    await settle();

    expect(
      screen.getByText("Sorry, we can't find any information related to your request"),
    ).toBeVisible();
    expect(screen.queryByRole("region", { name: "Retrieved passages" })).not.toBeInTheDocument();
    expect(questionInput()).toBeEnabled();
  });

  it("FR-6: shows an error that arrives before any answer text", async () => {
    render(<Page />);
    await ask("How do I get an app access token?");

    await emit((handlers) => handlers.onError("The answer couldn't be completed: groq failed"));
    await settle();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "The answer couldn't be completed: groq failed",
    );
    expect(questionInput()).toBeEnabled();
  });

  it("FR-6: shows an error that interrupts an answer, keeping what already rendered", async () => {
    render(<Page />);
    await ask("How do I get an app access token?");
    await emit((handlers) => handlers.onCitations(CITATIONS));
    await emit((handlers) => handlers.onToken("Request an app "));

    await emit((handlers) => handlers.onError("The answer stopped before it finished: reset"));
    await settle();

    expect(screen.getByText("Request an app")).toBeVisible();
    expect(screen.getByRole("region", { name: "Retrieved passages" })).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("stopped before it finished");
    expect(questionInput()).toBeEnabled();
  });

  it("FR-7: keeps every question of the session in the history", async () => {
    render(<Page />);

    await ask("How do I get an app access token?");
    await emit((handlers) => handlers.onToken("First answer."));
    await emit((handlers) => handlers.onDone());
    await settle();

    await ask("How does cursor pagination work?");
    await emit((handlers) => handlers.onToken("Second answer."));
    await emit((handlers) => handlers.onDone());
    await settle();

    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("First answer.")).toBeVisible();
    expect(screen.getByText("Second answer.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "How does cursor pagination work?" })).toBeVisible();
  });

  it("FR-8: disables the input while the request is in flight and re-enables it on done", async () => {
    render(<Page />);
    await ask("How do I get an app access token?");

    expect(questionInput()).toBeDisabled();
    expect(screen.getByRole("button", { name: /^asking/i })).toBeDisabled();

    await emit((handlers) => handlers.onDone());
    await settle();

    await waitFor(() => expect(questionInput()).toBeEnabled());
  });

  it("offers example questions until the first one is asked", async () => {
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getByRole("button", { name: "How does cursor pagination work?" }));

    expect(askQuestion).toHaveBeenCalledWith(
      "How does cursor pagination work?",
      expect.anything(),
      expect.any(AbortSignal),
    );
    expect(
      screen.queryByRole("button", { name: "How do I get an app access token?" }),
    ).not.toBeInTheDocument();
  });

  it("aborts the in-flight request when the page unmounts", async () => {
    const view = render(<Page />);
    await ask("How do I get an app access token?");
    const signal = vi.mocked(askQuestion).mock.calls[0][2];

    view.unmount();

    expect(signal.aborted).toBe(true);
  });
});
