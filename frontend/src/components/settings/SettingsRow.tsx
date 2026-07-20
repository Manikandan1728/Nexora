import { cn } from "@/lib/utils";

interface SettingsRowProps {
  label: React.ReactNode;
  description?: string;
  htmlFor?: string;
  children: React.ReactNode;
  className?: string;
  danger?: boolean;
}

export function SettingsRow({ label, description, htmlFor, children, className, danger }: SettingsRowProps) {
  return (
    <div className={cn("flex items-center justify-between gap-4 px-5 py-4", className)}>
      <div className="flex-1 min-w-0">
        {htmlFor ? (
          <label htmlFor={htmlFor} className={cn("text-sm font-medium block", danger ? "text-danger" : "text-foreground")}>
            {label}
          </label>
        ) : (
          <p className={cn("text-sm font-medium", danger ? "text-danger" : "text-foreground")}>{label}</p>
        )}
        {description && (
          <p className="text-xs text-muted-foreground mt-0.5 leading-snug">{description}</p>
        )}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
