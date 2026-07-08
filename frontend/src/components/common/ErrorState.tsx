import { AlertTriangle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApiError } from "@/types/api";

interface Props {
  error?: ApiError | Error | null;
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  error,
  title = "Something went wrong",
  message,
  onRetry,
  className,
}: Props) {
  const displayMessage =
    message ??
    (error instanceof Error
      ? error.message
      : (error as ApiError | null)?.message ?? "An unexpected error occurred.");

  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-4 rounded-xl",
        "border border-danger/20 bg-danger/5 p-10 text-center",
        "animate-fade-in",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-danger/10">
        <AlertTriangle className="h-6 w-6 text-danger" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground max-w-xs">{displayMessage}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-surface border border-border hover:bg-surface-hover transition-colors text-foreground"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  );
}
