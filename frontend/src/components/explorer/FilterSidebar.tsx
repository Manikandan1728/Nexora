import { useState } from "react";
import { Filter, ChevronDown, ChevronUp, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { ExplorerFilters } from "@/hooks/useExplorerSearch";

const CONTENT_TYPES = [
  { value: "", label: "All types" },
  { value: "text", label: "Text" },
  { value: "image", label: "Images" },
  { value: "video", label: "Video" },
  { value: "audio", label: "Audio" },
  { value: "voice", label: "Voice" },
  { value: "pdf", label: "PDF" },
  { value: "document", label: "Documents" },
];

interface FilterSidebarProps {
  filters: ExplorerFilters;
  onChange: (f: ExplorerFilters) => void;
  senderOptions?: Array<{ id: string; name: string }>;
  chatOptions?: Array<{ id: string; title: string }>;
  className?: string;
}

export function FilterSidebar({
  filters,
  onChange,
  senderOptions = [],
  chatOptions = [],
  className,
}: FilterSidebarProps) {
  const [isOpen, setIsOpen] = useState(true);

  const activeCount = Object.values(filters).filter(Boolean).length;

  const setFilter = (key: keyof ExplorerFilters, value: string | undefined) => {
    onChange({ ...filters, [key]: value || undefined });
  };

  const clearAll = () => onChange({});

  return (
    <aside
      className={cn("rounded-xl border border-border bg-surface overflow-hidden", className)}
      aria-label="Search filters"
    >
      {/* Header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-4 py-3 hover:bg-surface/80 transition-colors"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-accent" aria-hidden="true" />
          <span className="text-sm font-medium text-foreground">Filters</span>
          {activeCount > 0 && (
            <Badge className="h-4 w-4 p-0 text-[10px] flex items-center justify-center bg-accent text-white rounded-full">
              {activeCount}
            </Badge>
          )}
        </div>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {isOpen && (
        <div className="border-t border-border divide-y divide-border/50">
          {/* Content type */}
          <div className="px-4 py-3">
            <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Type</p>
            <div className="flex flex-wrap gap-1.5">
              {CONTENT_TYPES.map((ct) => (
                <button
                  key={ct.value}
                  onClick={() => setFilter("content_type", ct.value || undefined)}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs border transition-colors",
                    filters.content_type === (ct.value || undefined)
                      ? "bg-accent/10 border-accent/50 text-accent"
                      : "border-border text-muted-foreground hover:border-accent/30 hover:text-foreground"
                  )}
                >
                  {ct.label}
                </button>
              ))}
            </div>
          </div>

          {/* Sender filter */}
          {senderOptions.length > 0 && (
            <div className="px-4 py-3">
              <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Sender</p>
              <div className="space-y-1 max-h-36 overflow-y-auto">
                {senderOptions.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setFilter("sender_id", filters.sender_id === s.id ? undefined : s.id)}
                    className={cn(
                      "flex w-full items-center justify-between rounded px-2 py-1.5 text-xs transition-colors",
                      filters.sender_id === s.id
                        ? "bg-accent/10 text-accent"
                        : "text-muted-foreground hover:bg-surface/80 hover:text-foreground"
                    )}
                  >
                    <span className="truncate">{s.name}</span>
                    {filters.sender_id === s.id && <X className="h-3 w-3 shrink-0" />}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chat filter */}
          {chatOptions.length > 0 && (
            <div className="px-4 py-3">
              <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Chat</p>
              <div className="space-y-1 max-h-36 overflow-y-auto">
                {chatOptions.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setFilter("conversation_id", filters.conversation_id === c.id ? undefined : c.id)}
                    className={cn(
                      "flex w-full items-center justify-between rounded px-2 py-1.5 text-xs transition-colors",
                      filters.conversation_id === c.id
                        ? "bg-accent/10 text-accent"
                        : "text-muted-foreground hover:bg-surface/80 hover:text-foreground"
                    )}
                  >
                    <span className="truncate">{c.title}</span>
                    {filters.conversation_id === c.id && <X className="h-3 w-3 shrink-0" />}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Clear */}
          {activeCount > 0 && (
            <div className="px-4 py-3">
              <Button variant="ghost" size="sm" onClick={clearAll} className="w-full text-xs text-muted-foreground">
                Clear all filters
              </Button>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
