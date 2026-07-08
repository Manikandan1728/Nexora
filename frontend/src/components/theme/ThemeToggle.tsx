import { useTheme } from "@/hooks/useTheme";
import { Moon, Sun, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light" as const, Icon: Sun, label: "Light" },
  { value: "dark" as const, Icon: Moon, label: "Dark" },
  { value: "system" as const, Icon: Monitor, label: "System" },
];

interface Props {
  className?: string;
  /** compact = icon only toggle between dark/light */
  compact?: boolean;
}

export function ThemeToggle({ className, compact = true }: Props) {
  const { theme, setTheme, resolvedTheme } = useTheme();

  if (compact) {
    const isDark = resolvedTheme === "dark";
    return (
      <button
        type="button"
        onClick={() => setTheme(isDark ? "light" : "dark")}
        className={cn(
          "p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-hover transition-colors",
          className
        )}
        aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      >
        {isDark ? (
          <Sun className="h-4 w-4" aria-hidden="true" />
        ) : (
          <Moon className="h-4 w-4" aria-hidden="true" />
        )}
      </button>
    );
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 p-1 rounded-lg bg-surface border border-border",
        className
      )}
      role="radiogroup"
      aria-label="Theme selection"
    >
      {OPTIONS.map(({ value, Icon, label }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          onClick={() => setTheme(value)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
            theme === value
              ? "bg-accent text-accent-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-surface-hover"
          )}
          title={label}
        >
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          {label}
        </button>
      ))}
    </div>
  );
}
