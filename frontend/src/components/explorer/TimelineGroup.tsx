import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { TelegramSource } from "@/types/query";
import { ResultCard } from "./ResultCard";

interface TimelineGroupProps {
  dateLabel: string;
  sources: TelegramSource[];
  defaultOpen?: boolean;
  onResultClick?: (source: TelegramSource) => void;
}

export function TimelineGroup({ dateLabel, sources, defaultOpen = true, onResultClick }: TimelineGroupProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="relative">
      {/* Timeline line */}
      <div className="absolute left-4 top-10 bottom-0 w-px bg-border" aria-hidden="true" />

      {/* Date header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex items-center gap-3 py-3 w-full text-left group"
        aria-expanded={isOpen}
      >
        {/* Dot */}
        <div className="relative z-10 h-8 w-8 shrink-0 rounded-full border-2 border-accent bg-background flex items-center justify-center">
          {isOpen
            ? <ChevronDown className="h-3 w-3 text-accent" aria-hidden="true" />
            : <ChevronRight className="h-3 w-3 text-accent" aria-hidden="true" />
          }
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{dateLabel}</span>
          <span className="text-xs text-muted-foreground">
            {sources.length} {sources.length === 1 ? "result" : "results"}
          </span>
        </div>
      </button>

      {/* Items */}
      {isOpen && (
        <div className={cn("ml-12 space-y-2 pb-4")}>
          {sources.map((source, i) => (
            <ResultCard
              key={`${source.document_id}-${i}`}
              source={source}
              onClick={() => onResultClick?.(source)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
