import { Bot, FileText, MessageSquare } from "lucide-react";
import { formatElapsed, formatScore } from "@/lib/format";
import type { QueryResponse } from "@/types/query";
import { ResultCard } from "@/components/search/ResultCard";
import { TelegramSourceCard } from "@/components/search/TelegramSourceCard";

interface Props {
  result: QueryResponse;
}

export function AnswerPanel({ result }: Props) {
  const hasAnswer = result.answer && result.answer.trim().length > 0;
  const isLlmUnavailable = result.llm_used === false && result.message?.includes("LLM provider");
  const hasTelegramSources = (result.sources ?? []).length > 0;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Answer or specific fallback */}
      {isLlmUnavailable ? (
        <div className="rounded-xl border border-warning/20 bg-warning/5 px-5 py-4">
          <p className="text-sm font-semibold text-warning">
            AI answer is unavailable because the LLM provider is not running. Showing retrieved results instead.
          </p>
          <p className="mt-1 text-xs text-warning/80">
            Start Ollama or configure OpenAI to enable generated answers.
          </p>
        </div>
      ) : (
        <div className="rounded-xl bg-surface border border-border shadow-card overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-border bg-surface-hover">
            <Bot className="h-4 w-4 text-accent" aria-hidden="true" />
            <span className="text-xs font-semibold text-foreground uppercase tracking-wider">
              {result.llm_used ? "AI Answer" : "Search Results"}
            </span>
            <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
              {result.confidence != null && (
                <span>Confidence: {formatScore(result.confidence)}</span>
              )}
              <span>{formatElapsed(result.elapsed_seconds)}</span>
            </div>
          </div>
          <div className="px-5 py-4">
            {hasAnswer ? (
              <div className="answer-prose text-sm text-foreground leading-relaxed">
                {result.answer!.split("\n").map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            ) : result.message ? (
              <p className="text-sm text-muted-foreground">{result.message}</p>
            ) : (
              <p className="text-sm text-muted-foreground">
                No AI answer generated. See retrieved documents below.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Telegram source citations [ADDITIVE — Req 12, 14] */}
      {hasTelegramSources && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
            <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
            Telegram Sources ({result.sources!.length})
          </div>
          <div className="space-y-2">
            {result.sources!.map((src) => (
              <TelegramSourceCard key={src.document_id} source={src} />
            ))}
          </div>
        </div>
      )}

      {/* Retrieved Documents */}
      {result.retrieved_documents && result.retrieved_documents.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            Sources ({result.retrieved_documents.length})
          </div>
          <div className="space-y-3">
            {result.retrieved_documents.map((doc) => (
              <ResultCard key={doc.document_id} doc={doc} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

