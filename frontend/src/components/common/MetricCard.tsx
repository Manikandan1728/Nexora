import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string | number;
  icon?: ReactNode;
  trend?: { value: string; positive?: boolean };
  className?: string;
  description?: string;
}

export function MetricCard({
  label,
  value,
  icon,
  trend,
  className,
  description,
}: Props) {
  return (
    <div
      className={cn(
        "rounded-xl bg-surface border border-border p-4 shadow-card",
        "flex flex-col gap-3 transition-shadow hover:shadow-card-lg",
        "animate-fade-in",
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        {icon && (
          <span className="text-accent" aria-hidden="true">
            {icon}
          </span>
        )}
      </div>

      <div className="space-y-1">
        <p className="text-2xl font-bold text-foreground tabular-nums">
          {value}
        </p>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </div>

      {trend && (
        <div
          className={cn(
            "flex items-center gap-1 text-xs font-medium",
            trend.positive ? "text-success" : "text-muted-foreground"
          )}
        >
          <span>{trend.value}</span>
        </div>
      )}
    </div>
  );
}
