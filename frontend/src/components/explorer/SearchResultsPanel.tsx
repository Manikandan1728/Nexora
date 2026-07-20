import { useState } from "react";
import { MessageCircle, FileText, Image, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { QueryResponse, TelegramSource } from "@/types/query";
import { ResultCard } from "./ResultCard";
import { Badge } from "@/components/ui/Badge";

type Tab = "messages" | "documents" | "media";

interface SearchResultsPanelProps {
  data: QueryResponse | null;
  isLoading: boolean;
  error: string | null;
  onResultClick?: (source: TelegramSource) => void;
}

const TABS: Array<{ id: Tab; label: string; Icon: React.ElementType; types: string[] }> = [
  { id: "messages", label: "Messages", Icon: MessageCircle, types: ["text", ""] },
  { id: "documents", label: "Documents", Icon: FileText, types: ["pdf", "document", "docx", "xlsx", "pptx", "txt"] },
  { id: "media", label: "Media", Icon: Image, types: ["image", "video", "audio", "voice", "sticker"] },
];

function filterByTab(sources: TelegramSource[], tab: Tab): TelegramSource[] {
  const tabDef = TABS.find(t => t.id === tab);
  if (!tabDef) return sources;
  if (tab === "messages") {
    return sources.filter(s => !s.content_type || s.content_type === "text" || s.content_type === "");
  }
  return sources.filter(s => tabDef.types.includes(s.content_type?.toLowerCase() ?? ""));
}

export function SearchResultsPanel({ data, isLoading, error, onResultClick }: SearchResultsPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>("messages");

  const sources = data?.sources ?? [];
  const matchedTerms = data?.retrieved_documents?.flatMap(d => d.matched_terms ?? []) ?? [];

  const tabCounts = TABS.reduce((acc, t) => {
    acc[t.id] = filterByTab(sources, t.id).length;
    return acc;
  }, {} as Record<Tab, number>);

  const visible = filterByTab(sources, activeTab);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
        <span className="text-sm">Searching...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-danger/30 bg-danger/5 p-6 text-center text-sm text-danger">
        {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Result categories">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            role="tab"
            aria-selected={activeTab === id}
            onClick={() => setActiveTab(id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === id
                ? "border-accent text-accent"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {label}
            <Badge variant="secondary" className="text-[10px] h-4 px-1">
              {tabCounts[id]}
            </Badge>
          </button>
        ))}
      </div>

      {/* Results */}
      {visible.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          No {activeTab} results found for this query.
        </div>
      ) : (
        <div className="space-y-3" role="list" aria-label={`${activeTab} results`}>
          {visible.map((source, i) => (
            <div key={`${source.document_id}-${i}`} role="listitem">
              <ResultCard
                source={source}
                matchedTerms={matchedTerms}
                onClick={() => onResultClick?.(source)}
              />
            </div>
          ))}
        </div>
      )}

      {/* Footer note */}
      {sources.length > 0 && (
        <p className="text-center text-xs text-muted-foreground pt-2">
          Showing top {sources.length} results. Refine your query for more specific results.
        </p>
      )}
    </div>
  );
}
