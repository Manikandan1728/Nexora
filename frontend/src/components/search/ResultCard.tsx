import { useState, useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronDown, Copy, Check, Settings, AlertTriangle } from "lucide-react";
import type { RetrievedDocument } from "@/types/query";
import { cn } from "@/lib/utils";
import { MetadataBadges } from "./MetadataBadges";

interface Props {
  doc: RetrievedDocument;
}

// Simple regex to find URLs and replace them with anchor tags
function formatTextWithLinks(text: string) {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const parts = text.split(urlRegex);

  return parts.map((part, i) => {
    if (urlRegex.test(part)) {
      return (
        <a
          key={i}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent underline underline-offset-2 hover:opacity-80 transition-opacity"
        >
          {part}
        </a>
      );
    }
    return <span key={i} className="whitespace-pre-wrap">{part}</span>;
  });
}

export function ResultCard({ doc }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [metadataExpanded, setMetadataExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  // Reset metadata toggle when card collapses
  useEffect(() => {
    if (!expanded) {
      setMetadataExpanded(false);
    }
  }, [expanded]);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(doc.text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const score = doc.similarity_score;
  const isLowConfidence = doc.is_low_confidence ?? (score < 0.4);

  const knownCompactKeys = [
    "chunk_index",
    "token_count",
    "message_count",
    "contains_images",
    "contains_audio",
    "contains_documents",
    "source_chat",
    "timestamp",
    "start_timestamp",
  ];

  const advancedMetadata = doc.metadata
    ? Object.entries(doc.metadata).filter(([k]) => !knownCompactKeys.includes(k))
    : [];

  const sourceChat = doc.metadata?.source_chat as string | undefined;

  const timestampRaw = (doc.metadata?.timestamp ||
    doc.metadata?.start_timestamp) as string | undefined;
  let formattedTimestamp: string | undefined = undefined;

  if (timestampRaw) {
    const parsedDate = new Date(timestampRaw);
    if (!isNaN(parsedDate.getTime())) {
      formattedTimestamp = parsedDate.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    }
  }

  return (
    <div
      className={cn(
        "rounded-xl bg-surface border p-4 transition-colors",
        expanded ? "border-accent/50 shadow-card" : "border-border hover:border-accent/30"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            #{doc.rank}
          </span>
          <span
            className="text-xs font-semibold px-2 py-0.5 rounded-full bg-surface-hover text-muted-foreground"
            title={`Raw score: ${score}`}
          >
            Relevance {(score * 100).toFixed(1)}%
          </span>
          {isLowConfidence && (
            <span className="flex items-center gap-1 text-xs font-medium text-warning bg-warning/10 px-2 py-0.5 rounded-full">
              <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              Low confidence match
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <MetadataBadges metadata={doc.metadata} />
          {expanded && (
            <button
              onClick={handleCopy}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-hover transition-colors ml-1"
              title="Copy chunk text"
              aria-label="Copy chunk text"
            >
              {copied ? (
                <Check className="h-4 w-4 text-success" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Source Chat & Timestamp */}
      {(sourceChat || formattedTimestamp) && (
        <div className="flex flex-wrap items-center gap-2 mb-2 text-xs text-muted-foreground">
          {sourceChat && (
            <span className="font-medium truncate max-w-[200px]" title={sourceChat}>
              {sourceChat}
            </span>
          )}
          {sourceChat && formattedTimestamp && <span>•</span>}
          {formattedTimestamp && (
            <span title={timestampRaw}>{formattedTimestamp}</span>
          )}
        </div>
      )}

      {/* Body */}
      <div className="text-sm text-foreground leading-relaxed mt-2">
        {expanded ? (
          <div>{formatTextWithLinks(doc.text)}</div>
        ) : (
          <div className="line-clamp-4 whitespace-pre-wrap">
            {doc.focused_snippet ? formatTextWithLinks(doc.focused_snippet) : doc.text}
          </div>
        )}
      </div>

      {/* Expanded Only: Advanced Metadata */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={
              shouldReduceMotion ? { opacity: 0 } : { height: 0, opacity: 0 }
            }
            animate={
              shouldReduceMotion ? { opacity: 1 } : { height: "auto", opacity: 1 }
            }
            exit={
              shouldReduceMotion ? { opacity: 0 } : { height: 0, opacity: 0 }
            }
            className="overflow-hidden"
          >
            <div className="pt-4 mt-4 border-t border-border">
              <button
                type="button"
                onClick={() => setMetadataExpanded(!metadataExpanded)}
                className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                aria-expanded={metadataExpanded}
              >
                <Settings className="h-3.5 w-3.5" aria-hidden="true" />
                Advanced metadata
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 transition-transform duration-200",
                    metadataExpanded && "rotate-180"
                  )}
                  aria-hidden="true"
                />
              </button>

              <AnimatePresence initial={false}>
                {metadataExpanded && advancedMetadata.length > 0 && (
                  <motion.div
                    initial={
                      shouldReduceMotion
                        ? { opacity: 0 }
                        : { height: 0, opacity: 0 }
                    }
                    animate={
                      shouldReduceMotion
                        ? { opacity: 1 }
                        : { height: "auto", opacity: 1 }
                    }
                    exit={
                      shouldReduceMotion
                        ? { opacity: 0 }
                        : { height: 0, opacity: 0 }
                    }
                    className="overflow-hidden"
                  >
                    <div className="mt-3 bg-surface-hover rounded-lg p-3 max-h-48 overflow-y-auto text-xs text-muted-foreground space-y-1.5">
                      {advancedMetadata.map(([k, v]) => (
                        <div
                          key={k}
                          className="flex flex-col sm:flex-row sm:gap-2 border-b border-border/50 pb-1.5 last:border-0 last:pb-0"
                        >
                          <span className="font-semibold shrink-0">{k}:</span>
                          <span className="font-mono break-all text-foreground">
                            {typeof v === "object"
                              ? JSON.stringify(v)
                              : String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
                {metadataExpanded && advancedMetadata.length === 0 && (
                  <motion.div
                    initial={
                      shouldReduceMotion
                        ? { opacity: 0 }
                        : { height: 0, opacity: 0 }
                    }
                    animate={
                      shouldReduceMotion
                        ? { opacity: 1 }
                        : { height: "auto", opacity: 1 }
                    }
                    exit={
                      shouldReduceMotion
                        ? { opacity: 0 }
                        : { height: 0, opacity: 0 }
                    }
                    className="overflow-hidden"
                  >
                    <div className="mt-3 text-xs text-muted-foreground italic">
                      No additional metadata available.
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Expand/Collapse Toggle */}
      <div className="mt-3 pt-3 border-t border-border/50">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center justify-center gap-1.5 text-xs font-medium text-accent hover:opacity-80 transition-opacity min-h-[32px]"
          aria-expanded={expanded}
        >
          {expanded ? "Collapse" : "View full conversation"}
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 transition-transform duration-200",
              expanded && "rotate-180"
            )}
            aria-hidden="true"
          />
        </button>
      </div>
    </div>
  );
}
