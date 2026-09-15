import { CitationsList } from "./CitationsList";

import type { Exchange } from "@/lib/conversation";

interface MessageListProps {
  exchanges: Exchange[];
}

function progressLabel(exchange: Exchange): string {
  return exchange.citations.length === 0
    ? "Searching the documentation"
    : "Writing the answer";
}

function Answer({ exchange }: { exchange: Exchange }) {
  if (exchange.status === "fallback") {
    return (
      <p className="mt-5 max-w-[68ch] border-l-2 border-line pl-4 text-[0.9375rem] leading-relaxed text-muted">
        {exchange.answer}
      </p>
    );
  }

  if (exchange.answer === "") {
    if (exchange.status !== "streaming") return null;
    return (
      <p className="mt-5 text-[0.9375rem] text-muted">
        {progressLabel(exchange)}
        <span className="caret ml-1 inline-block h-[0.95em] w-[0.5ch] translate-y-[0.1em] bg-violet align-baseline" />
      </p>
    );
  }

  return (
    <p className="mt-5 max-w-[68ch] text-[0.9375rem] leading-[1.7] whitespace-pre-wrap">
      {exchange.answer}
      {exchange.status === "streaming" && (
        <span className="caret ml-0.5 inline-block h-[0.95em] w-[0.5ch] translate-y-[0.1em] bg-violet align-baseline" />
      )}
    </p>
  );
}

export function MessageList({ exchanges }: MessageListProps) {
  return (
    <ol className="flex flex-col gap-10">
      {exchanges.map((exchange) => (
        <li key={exchange.id}>
          <h2 className="border-l-2 border-violet pl-4 text-[1.0625rem] leading-snug font-semibold">
            {exchange.question}
          </h2>

          <CitationsList citations={exchange.citations} />

          <Answer exchange={exchange} />

          {exchange.status === "error" && (
            <p
              role="alert"
              className="mt-4 max-w-[68ch] border-l-2 border-alert pl-4 text-[0.9375rem] leading-relaxed text-alert"
            >
              {exchange.error}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
