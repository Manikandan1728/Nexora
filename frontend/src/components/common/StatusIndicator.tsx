import { useHealth } from "@/hooks/useHealth";
import { cn } from "@/lib/utils";

interface Props {
  showLabel?: boolean;
  className?: string;
}

export function StatusIndicator({ showLabel = true, className }: Props) {
  const { data, isLoading, isError } = useHealth();

  const isOnline = !isLoading && !isError && data?.status === "ok";
  const isOffline = isError;
  const isDegraded =
    !isLoading && !isError && data?.status !== "ok";

  const dot = cn(
    "h-2 w-2 rounded-full shrink-0",
    isLoading && "bg-warning animate-pulse",
    isOnline && "bg-success animate-pulse",
    isOffline && "bg-danger",
    isDegraded && "bg-warning animate-pulse"
  );

  const label = isLoading
    ? "Checking…"
    : isOnline
    ? "Online"
    : isOffline
    ? "Offline"
    : "Degraded";

  const labelClass = cn(
    "text-xs font-medium",
    isOnline && "text-success",
    isOffline && "text-danger",
    isDegraded && "text-warning",
    isLoading && "text-muted-foreground"
  );

  return (
    <div
      className={cn("flex items-center gap-1.5", className)}
      aria-label={`Backend status: ${label}`}
      title={`Backend: ${label}`}
    >
      <span className={dot} aria-hidden="true" />
      {showLabel && <span className={labelClass}>{label}</span>}
    </div>
  );
}
