import { cn } from "@/lib/utils";

interface Props {
  variant?: "page" | "card" | "text" | "avatar";
  className?: string;
  lines?: number;
}

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "skeleton rounded-md animate-shimmer",
        className
      )}
      aria-hidden="true"
    />
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-6 animate-fade-in" aria-label="Loading page…" aria-busy="true">
      {/* Header */}
      <div className="space-y-2">
        <SkeletonBlock className="h-7 w-48" />
        <SkeletonBlock className="h-4 w-80" />
      </div>
      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl bg-surface border border-border p-4 space-y-3">
            <SkeletonBlock className="h-4 w-24" />
            <SkeletonBlock className="h-8 w-16" />
          </div>
        ))}
      </div>
      {/* Content block */}
      <div className="rounded-xl bg-surface border border-border p-6 space-y-3">
        <SkeletonBlock className="h-4 w-full" />
        <SkeletonBlock className="h-4 w-5/6" />
        <SkeletonBlock className="h-4 w-4/6" />
      </div>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div
      className="rounded-xl bg-surface border border-border p-4 space-y-3 animate-fade-in"
      aria-label="Loading…"
      aria-busy="true"
    >
      <SkeletonBlock className="h-4 w-32" />
      <SkeletonBlock className="h-3 w-full" />
      <SkeletonBlock className="h-3 w-3/4" />
    </div>
  );
}

function TextSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2 animate-fade-in" aria-busy="true">
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonBlock
          key={i}
          className={cn("h-4", i === lines - 1 ? "w-3/4" : "w-full")}
        />
      ))}
    </div>
  );
}

export function LoadingSkeleton({ variant = "page", className, lines }: Props) {
  if (variant === "page") return <PageSkeleton />;
  if (variant === "card") return <CardSkeleton />;
  if (variant === "text") return <TextSkeleton lines={lines} />;
  if (variant === "avatar")
    return <SkeletonBlock className={cn("h-10 w-10 rounded-full", className)} />;
  return <PageSkeleton />;
}
