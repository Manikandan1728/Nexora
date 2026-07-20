import { cn } from "@/lib/utils";

interface EmptyExplorerProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyExplorer({ icon, title, description, action, className }: EmptyExplorerProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center py-20 text-center gap-4 animate-fade-in", className)}>
      {icon && (
        <div className="h-16 w-16 rounded-2xl bg-surface border border-border flex items-center justify-center text-muted-foreground">
          {icon}
        </div>
      )}
      <div className="space-y-1.5">
        <p className="text-base font-semibold text-foreground">{title}</p>
        {description && (
          <p className="text-sm text-muted-foreground max-w-xs">{description}</p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
