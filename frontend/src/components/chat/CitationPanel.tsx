import { useState } from "react";
import { ChevronRight, FileText, MessageCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { QueryResponse, TelegramSource } from "@/types/query";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

interface CitationPanelProps {
  responseData: QueryResponse | undefined;
  onClose?: () => void;
  isOpen: boolean;
}

export function CitationPanel({ responseData, onClose, isOpen }: CitationPanelProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!isOpen || !responseData) {
    return null;
  }

  const sources = responseData.sources || [];
  const docs = responseData.retrieved_documents || [];

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="flex h-full w-full flex-col border-l border-border bg-background animate-fade-in">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="font-semibold text-foreground flex items-center gap-2">
          <FileText className="h-4 w-4 text-accent" />
          Retrieved Context
        </h3>
        {onClose && (
          <Button variant="ghost" size="icon" onClick={onClose} className="h-8 w-8 text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {sources.length === 0 && docs.length === 0 && (
          <div className="text-sm text-muted-foreground text-center mt-10">
            No context retrieved.
          </div>
        )}

        {sources.map((source: TelegramSource, index: number) => {
          const isExpanded = expandedId === source.document_id;
          return (
            <Card key={source.document_id + index} className="overflow-hidden border border-border shadow-sm">
              <button
                onClick={() => toggleExpand(source.document_id)}
                className="flex w-full items-center justify-between bg-surface px-3 py-2 text-left hover:bg-surface/80 transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <MessageCircle className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="truncate text-sm font-medium text-foreground">
                    {source.conversation_title || source.conversation_id || "Telegram Chat"}
                  </span>
                </div>
                <ChevronRight className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", isExpanded && "rotate-90")} />
              </button>
              
              {isExpanded && (
                <div className="border-t border-border bg-background p-3 text-sm">
                  <div className="mb-2 flex flex-wrap gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {source.sender_name || "Unknown"}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      Score: {(source.score * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <p className="text-muted-foreground whitespace-pre-wrap font-mono text-xs">
                    {source.snippet || "(No snippet available)"}
                  </p>
                </div>
              )}
            </Card>
          );
        })}

        {/* Fallback for documents without telegram sources (if any) */}
        {sources.length === 0 && docs.map((doc, index) => {
          const isExpanded = expandedId === doc.document_id;
          return (
            <Card key={doc.document_id + index} className="overflow-hidden border border-border shadow-sm">
              <button
                onClick={() => toggleExpand(doc.document_id)}
                className="flex w-full items-center justify-between bg-surface px-3 py-2 text-left hover:bg-surface/80 transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="truncate text-sm font-medium text-foreground">
                    Document {index + 1}
                  </span>
                </div>
                <ChevronRight className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", isExpanded && "rotate-90")} />
              </button>
              
              {isExpanded && (
                <div className="border-t border-border bg-background p-3 text-sm">
                  <div className="mb-2 flex flex-wrap gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      Score: {(doc.similarity_score * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <p className="text-muted-foreground whitespace-pre-wrap font-mono text-xs">
                    {doc.text}
                  </p>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
