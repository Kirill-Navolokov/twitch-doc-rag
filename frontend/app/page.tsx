"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { MessageInput } from "@/components/MessageInput";
import { MessageList } from "@/components/MessageList";
import { askQuestion } from "@/lib/askQuestion";
import { conversationReducer } from "@/lib/conversation";

const EXAMPLE_QUESTIONS = [
  "How do I get an app access token?",
  "Which scope does Get User Subscriptions need?",
  "How does cursor pagination work?",
];

export default function Page() {
  const [exchanges, dispatch] = useReducer(conversationReducer, []);
  const [pending, setPending] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const nextId = useRef(0);
  const transcriptRef = useRef<HTMLElement>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  // Only when an exchange is added, so scrolling back through history is not fought token by token.
  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) transcript.scrollTop = transcript.scrollHeight;
  }, [exchanges.length]);

  const ask = useCallback(async (question: string) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    const id = nextId.current;
    nextId.current += 1;
    dispatch({ type: "ask", id, question });
    setPending(true);

    // Every handler dispatches rather than writing captured state: they fire synchronously and
    // repeatedly while one stream chunk is parsed, so a closed-over snapshot would lose tokens.
    await askQuestion(
      question,
      {
        onCitations: (citations) => dispatch({ type: "citations", id, citations }),
        onToken: (text) => dispatch({ type: "token", id, text }),
        onDone: () => dispatch({ type: "done", id }),
        onFallback: (text) => dispatch({ type: "fallback", id, text }),
        onError: (message) => dispatch({ type: "error", id, message }),
      },
      controller.signal,
    );

    // A newer request has already taken over the input; only the current one may re-enable it.
    if (controllerRef.current === controller) setPending(false);
  }, []);

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-5 sm:px-8">
      <header className="shrink-0 border-b border-line pt-8 pb-5">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
          Ask the Twitch docs
        </h1>
        <p className="mt-1.5 max-w-[60ch] text-sm text-muted">
          Answers are written from the indexed Twitch API reference pages, and every answer arrives
          with the passages it was drawn from.
        </p>
      </header>

      <main ref={transcriptRef} className="min-h-0 flex-1 overflow-y-auto py-8">
        {exchanges.length === 0 ? (
          <div>
            <p className="text-sm text-muted">Start with one of these, or ask your own.</p>
            <ul className="mt-3 border-t border-line">
              {EXAMPLE_QUESTIONS.map((question) => (
                <li key={question}>
                  <button
                    type="button"
                    onClick={() => ask(question)}
                    className="w-full border-b-2 border-line py-3 text-left text-[0.9375rem] hover:border-violet hover:text-violet"
                  >
                    {question}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <MessageList exchanges={exchanges} />
        )}
      </main>

      <div className="shrink-0 pb-7">
        <MessageInput disabled={pending} onSubmit={ask} />
      </div>
    </div>
  );
}
