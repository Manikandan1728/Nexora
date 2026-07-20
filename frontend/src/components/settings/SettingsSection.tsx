import { cn } from "@/lib/utils";

interface SettingsSectionProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function SettingsSection({ title, description, icon, children, className }: SettingsSectionProps) {
  return (
    <section
      className={cn("rounded-xl border border-border bg-surface overflow-hidden shadow-card", className)}
    >
      <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
        {icon && <span className="text-accent shrink-0" aria-hidden="true">{icon}</span>}
        <div>
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {description && (
            <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
          )}
        </div>
      </div>
      <div className="divide-y divide-border/50">{children}</div>
    </section>
  );
}
