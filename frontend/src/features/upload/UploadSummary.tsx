import { CheckCircle2, FileText, Hash, Layers, Clock } from "lucide-react";
import { Link } from "react-router-dom";
import { formatElapsed } from "@/lib/format";
import type { UploadResponse } from "@/types/upload";

interface Props {
  result: UploadResponse;
  onReset: () => void;
}

const STAT_ROWS = (r: UploadResponse) => [
  {
    icon: FileText,
    label: "Messages Parsed",
    value: r.messages_parsed.toLocaleString(),
  },
  {
    icon: Hash,
    label: "Chunks Created",
    value: r.chunks_created.toLocaleString(),
  },
  {
    icon: Layers,
    label: "Vectors Indexed",
    value: r.vectors_indexed.toLocaleString(),
  },
  {
    icon: Clock,
    label: "Elapsed",
    value: formatElapsed(r.elapsed_seconds),
  },
];

export function UploadSummary({ result, onReset }: Props) {
  return (
    <div className="space-y-5 animate-fade-in">
      {/* Success banner */}
      <div className="flex items-center gap-3 rounded-xl border border-success/30 bg-success/10 px-5 py-4">
        <CheckCircle2 className="h-6 w-6 text-success shrink-0" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold text-foreground">
            Upload complete!
          </p>
          <p className="text-xs text-muted-foreground">
            Collection{" "}
            <span className="font-mono text-accent">{result.collection_name}</span>{" "}
            is ready to search.
          </p>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3">
        {STAT_ROWS(result).map(({ icon: Icon, label, value }) => (
          <div
            key={label}
            className="rounded-xl bg-surface border border-border p-4 flex items-start gap-3"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10 text-accent shrink-0">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-base font-bold text-foreground tabular-nums">
                {value}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Phase statuses */}
      {result.phase_statuses && result.phase_statuses.length > 0 && (
        <div className="rounded-xl bg-surface border border-border divide-y divide-border overflow-hidden">
          <p className="px-4 py-2.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Processing Phases
          </p>
          {result.phase_statuses.map((phase) => (
            <div
              key={phase.phase}
              className="flex items-center justify-between px-4 py-2.5"
            >
              <span className="text-sm text-foreground capitalize">
                {phase.phase.replace(/_/g, " ")}
              </span>
              <span
                className={
                  phase.status === "success"
                    ? "text-xs font-medium text-success"
                    : phase.status === "skipped"
                    ? "text-xs font-medium text-muted-foreground"
                    : "text-xs font-medium text-danger"
                }
              >
                {phase.status}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-3">
        <Link
          to="/search"
          state={{ collection: result.collection_name }}
          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground hover:opacity-90 transition-opacity"
        >
          Search this collection →
        </Link>
        <button
          type="button"
          onClick={onReset}
          className="flex-1 rounded-lg border border-border bg-surface px-4 py-2.5 text-sm font-medium text-foreground hover:bg-surface-hover transition-colors"
        >
          Upload another
        </button>
      </div>
    </div>
  );
}
