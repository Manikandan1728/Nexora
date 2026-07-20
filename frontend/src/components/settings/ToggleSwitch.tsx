import { cn } from "@/lib/utils";

interface ToggleSwitchProps {
  id: string;
  checked: boolean;
  onChange: (val: boolean) => void;
  label?: string;
  disabled?: boolean;
}

export function ToggleSwitch({ id, checked, onChange, label, disabled }: ToggleSwitchProps) {
  return (
    <button
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
        checked ? "bg-accent" : "bg-border",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      <span
        className={cn(
          "inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-6" : "translate-x-1"
        )}
        aria-hidden="true"
      />
    </button>
  );
}
