import type { Citation } from "@/lib/askQuestion";

interface CitationsListProps {
  citations: Citation[];
}

function displayUrl(sourceUrl: string): string {
  return sourceUrl.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

export function CitationsList({ citations }: CitationsListProps) {
  if (citations.length === 0) return null;

  return (
    <section aria-label="Retrieved passages" className="mt-4">
      <h3 className="text-[0.8125rem] font-medium text-muted">Retrieved passages</h3>
      <ol className="mt-2 border-t border-line">
        {citations.map((citation) => (
          <li
            key={`${citation.source_url}#${citation.chunk_index}`}
            className="relative pt-2 pb-2.5"
          >
            <div className="flex items-baseline gap-3">
              <a
                href={citation.source_url}
                target="_blank"
                rel="noreferrer"
                className="min-w-0 flex-1 truncate text-sm font-medium text-ink decoration-violet/40 underline-offset-4 hover:underline"
              >
                {citation.title}
              </a>
              <span className="shrink-0 font-mono text-xs text-muted">
                passage {citation.chunk_index}
              </span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-violet">
                {citation.score.toFixed(2)}
              </span>
            </div>
            <p className="mt-0.5 truncate font-mono text-[0.6875rem] text-muted">
              {displayUrl(citation.source_url)}
            </p>
            {/* The row's own divider carries the match score, so the evidence is measured, not just listed. */}
            <span aria-hidden className="absolute inset-x-0 bottom-0 h-[2px] bg-line" />
            <span
              aria-hidden
              className="absolute bottom-0 left-0 h-[2px] bg-violet"
              style={{ width: `${Math.max(0, Math.min(1, citation.score)) * 100}%` }}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}
