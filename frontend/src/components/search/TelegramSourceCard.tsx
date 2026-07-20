// frontend/src/components/search/TelegramSourceCard.tsx
// [ADDITIVE] Renders a single Telegram source citation (Req 14).
// Shows: conversation title/type, sender name, timestamp, content type,
// filename (when present), and snippet. Raw IDs are hidden from normal view.

import { MessageSquare, Users, Radio, FileText, Mic, Video, Image, Link } from "lucide-react";
import type { TelegramSource } from "@/types/query";

interface Props {
  source: TelegramSource;
  showDebugIds?: boolean;
}

const CONTENT_TYPE_ICON: Record<string, React.ReactNode> = {
  text:     <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />,
  link:     <Link          className="h-3.5 w-3.5" aria-hidden="true" />,
  pdf:      <FileText      className="h-3.5 w-3.5" aria-hidden="true" />,
  docx:     <FileText      className="h-3.5 w-3.5" aria-hidden="true" />,
  pptx:     <FileText      className="h-3.5 w-3.5" aria-hidden="true" />,
  image:    <Image         className="h-3.5 w-3.5" aria-hidden="true" />,
  voice:    <Mic           className="h-3.5 w-3.5" aria-hidden="true" />,
  video:    <Video         className="h-3.5 w-3.5" aria-hidden="true" />,
  document: <FileText      className="h-3.5 w-3.5" aria-hidden="true" />,
};

const CHAT_TYPE_ICON: Record<string, React.ReactNode> = {
  private:    <MessageSquare className="h-3 w-3" aria-hidden="true" />,
  group:      <Users         className="h-3 w-3" aria-hidden="true" />,
  supergroup: <Users         className="h-3 w-3" aria-hidden="true" />,
  channel:    <Radio         className="h-3 w-3" aria-hidden="true" />,
};

function formatTimestamp(ts: string): string {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

export function TelegramSourceCard({ source, showDebugIds = false }: Props) {
  const contentIcon = CONTENT_TYPE_ICON[source.content_type] ?? CONTENT_TYPE_ICON.text;
  const chatIcon    = CHAT_TYPE_ICON[source.conversation_type] ?? CHAT_TYPE_ICON.private;
  const hasFile     = Boolean(source.filename);
  const displayTs   = formatTimestamp(source.timestamp);
  const scoreLabel  = `${(source.score * 100).toFixed(1)}%`;

  return (
    <div className="rounded-lg border border-border bg-surface p-3 space-y-2 text-sm">
      {/* Header row — conversation + score */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-muted-foreground shrink-0">{chatIcon}</span>
          {/* conversation_title for display; conversation_id used for filtering only */}
          <span className="font-medium truncate">
            {source.conversation_title || source.conversation_id}
          </span>
          {source.conversation_type && (
            <span className="text-xs text-muted-foreground bg-surface-hover px-1.5 py-0.5 rounded shrink-0">
              {source.conversation_type}
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground shrink-0">{scoreLabel}</span>
      </div>

      {/* Sender + timestamp */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
        {source.sender_name && (
          <span className="font-medium text-foreground">{source.sender_name}</span>
        )}
        {displayTs && <span>{displayTs}</span>}
      </div>

      {/* Content type + filename */}
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="shrink-0">{contentIcon}</span>
        <span className="capitalize">{source.content_type}</span>
        {hasFile && (
          <>
            <span>·</span>
            <span className="truncate font-mono text-foreground">{source.filename}</span>
          </>
        )}
      </div>

      {/* Snippet */}
      {source.snippet && (
        <p className="text-xs text-foreground bg-surface-hover rounded px-2 py-1.5 leading-relaxed line-clamp-3">
          {source.snippet}
        </p>
      )}

      {/* Debug IDs — hidden by default (Req 14) */}
      {showDebugIds && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer hover:text-foreground">Debug IDs</summary>
          <div className="mt-1 space-y-0.5 font-mono">
            <div>doc: {source.document_id}</div>
            <div>msg: {source.message_id}</div>
            <div>conv: {source.conversation_id}</div>
            <div>sender: {source.sender_id}</div>
          </div>
        </details>
      )}
    </div>
  );
}
