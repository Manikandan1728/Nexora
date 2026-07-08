import { cn } from "@/lib/utils";

interface Props {
  progress: number;
  fileName?: string;
  isPending: boolean;
}

export function UploadProgress({ progress, fileName, isPending }: Props) {
  if (!isPending) return null;

  return (
    <div
      className="space-y-3 rounded-xl bg-surface border border-border p-5 animate-fade-in"
      role="status"
      aria-label="Upload in progress"
      aria-live="polite"
    >
      <div className="flex items-center justify-between text-sm">
        <div className="flex flex-col gap-0.5">
          <span className="font-medium text-foreground">Uploading…</span>
          {fileName && (
            <span className="text-xs text-muted-foreground truncate max-w-xs">
              {fileName}
            </span>
          )}
        </div>
        <span className="text-accent font-semibold tabular-nums text-sm">
          {progress}%
        </span>
      </div>

      {/* Progress bar */}
      <div className="relative h-2 w-full rounded-full bg-surface-hover overflow-hidden">
        <div
          className={cn(
            "absolute inset-y-0 left-0 rounded-full bg-accent transition-all duration-300",
            progress < 100 && "animate-pulse"
          )}
          style={{ width: `${progress}%` }}
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          role="progressbar"
        />
      </div>

      <p className="text-xs text-muted-foreground">
        {progress < 100
          ? "Uploading file to server…"
          : "Processing and indexing. This may take a few minutes…"}
      </p>
    </div>
  );
}
