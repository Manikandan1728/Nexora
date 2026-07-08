import { ExternalLink, MessageSquare, Hash } from "lucide-react";
import { formatScore } from "@/lib/format";
import type { Citation } from "@/types/query";
import { cn } from "@/lib/utils";

interface Props {
  citations: Citation[];
}

export function CitationList({ citations }: Props) {
  if (citations.length === 0) return null;

  return (
    <div className="space-y-2 animate-fade-in">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
        Citations ({citations.length})
      </p>
      <div className="space-y-2">
        {citations.map((cite) => (
          <div
            key={`${cite.document_id}-${cite.rank}`}
            className={cn(
              "rounded-xl bg-surface border border-border p-4",
              "hover:border-accent/30 transition-colors"
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/10 text-accent">
                  <span className="text-xs font-bold">{cite.rank}</span>
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <MessageSquare className="h-3 w-3" aria-hidden="true" />
                    <span className="font-mono truncate max-w-[180px]" title={cite.source_chat}>
                      {cite.source_chat}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Hash className="h-3 w-3" aria-hidden="true" />
                    <span>Chunk {cite.chunk_index}</span>
                  </div>
                </div>
              </div>

              <span
                className={cn(
                  "shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full",
                  cite.similarity_score >= 0.8
                    ? "bg-success/10 text-success"
                    : cite.similarity_score >= 0.6
                    ? "bg-warning/10 text-warning"
                    : "bg-surface-hover text-muted-foreground"
                )}
              >
                {formatScore(cite.similarity_score)}
              </span>
            </div>

            {(cite.start_timestamp || cite.end_timestamp) && (
              <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
                <span>
                  {cite.start_timestamp}
                  {cite.end_timestamp && cite.end_timestamp !== cite.start_timestamp
                    ? ` → ${cite.end_timestamp}`
                    : ""}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
