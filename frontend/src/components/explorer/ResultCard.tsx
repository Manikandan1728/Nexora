import { MessageCircle, Clock, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TelegramSource } from "@/types/query";
import { Badge } from "@/components/ui/Badge";

interface ResultCardProps {
  source: TelegramSource;
  matchedTerms?: string[];
  onClick?: () => void;
  className?: string;
}

function highlightTerms(text: string, terms: string[]): React.ReactNode {
  if (!terms.length) return text;
  const pattern = new RegExp(`(${terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, i) =>
    pattern.test(part)
      ? <mark key={i} className="bg-accent/30 text-foreground rounded px-0.5">{part}</mark>
      : part
  );
}

export function ResultCard({ source, matchedTerms = [], onClick, className }: ResultCardProps) {
  const formattedDate = source.timestamp
    ? new Date(source.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
    : null;

  const formattedTime = source.timestamp
    ? new Date(source.timestamp).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : null;

  const scorePercent = Math.round(source.score * 100);

  return (
    <button
      onClick={onClick}
      className={cn(
        "group w-full text-left rounded-xl border border-border bg-surface p-4",
        "hover:border-accent/40 hover:shadow-md transition-all duration-150",
        "focus:outline-none focus:ring-2 focus:ring-accent/50",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <MessageCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="text-xs font-medium text-accent truncate">
            {source.conversation_title || source.conversation_id}
          </span>
          {source.conversation_type && (
            <Badge variant="outline" className="text-[10px] h-4 px-1 shrink-0">
              {source.conversation_type}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {scorePercent > 0 && (
            <span className="text-[10px] text-muted-foreground">
              {scorePercent}%
            </span>
          )}
          <ExternalLink className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
        </div>
      </div>

      {/* Sender */}
      {source.sender_name && (
        <div className="mb-1.5">
          <span className="text-xs font-semibold text-foreground">{source.sender_name}</span>
        </div>
      )}

      {/* Snippet */}
      <p className="text-sm text-muted-foreground line-clamp-3 mb-3">
        {highlightTerms(source.snippet || "(No preview available)", matchedTerms)}
      </p>

      {/* Footer */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          {source.content_type && source.content_type !== "text" && (
            <Badge variant="secondary" className="text-[10px]">
              {source.content_type}
            </Badge>
          )}
          {source.filename && (
            <span className="text-[10px] text-muted-foreground truncate max-w-[120px]">
              {source.filename}
            </span>
          )}
        </div>
        {formattedDate && (
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground shrink-0">
            <Clock className="h-3 w-3" aria-hidden="true" />
            <span>{formattedDate}</span>
            {formattedTime && <span className="text-muted-foreground/60">{formattedTime}</span>}
          </div>
        )}
      </div>
    </button>
  );
}
