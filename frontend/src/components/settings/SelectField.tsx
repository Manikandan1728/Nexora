import { cn } from "@/lib/utils";

interface Option<T extends string> {
  value: T;
  label: string;
}

interface SelectFieldProps<T extends string> {
  id: string;
  value: T;
  options: Option<T>[];
  onChange: (val: T) => void;
  className?: string;
}

export function SelectField<T extends string>({
  id,
  value,
  options,
  onChange,
  className,
}: SelectFieldProps<T>) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className={cn(
        "rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-foreground",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 cursor-pointer",
        "hover:border-accent/40 transition-colors",
        className
      )}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
