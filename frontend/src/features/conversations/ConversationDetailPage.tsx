import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useCollections } from "@/hooks/useCollections";
import { runQuery } from "@/api/query.service";
import { getChat } from "@/api/telegram.service";
import { ArrowLeft, Loader2, MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Avatar, AvatarFallback } from "@/components/ui/Avatar";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import type { TelegramSource } from "@/types/query";

function MessageItem({ source }: { source: TelegramSource }) {
  const formattedDate = source.timestamp
    ? new Date(source.timestamp).toLocaleString(undefined, {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
      })
    : null;
  const initials = (source.sender_name || "?").slice(0, 2).toUpperCase();

  return (
    <div className="group flex gap-3 rounded-lg p-3 hover:bg-surface/60 transition-colors">
      <Avatar className="h-8 w-8 shrink-0 mt-0.5">
        <AvatarFallback className="text-xs bg-accent/10 text-accent">{initials}</AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 mb-0.5">
          <span className="text-xs font-semibold text-foreground">{source.sender_name || "Unknown"}</span>
          {formattedDate && (
            <span className="text-[10px] text-muted-foreground">{formattedDate}</span>
          )}
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap">{source.snippet}</p>
        {source.content_type && source.content_type !== "text" && (
          <span className="inline-block mt-1 text-[10px] bg-surface border border-border rounded px-1 py-0.5 text-muted-foreground">
            {source.content_type}
            {source.filename ? ` · ${source.filename}` : ""}
          </span>
        )}
      </div>
    </div>
  );
}

export default function ConversationDetailPage() {
  const { chatId } = useParams<{ chatId: string }>();
  const navigate = useNavigate();
  const collections = useCollections();
  const collection = collections.data?.collections?.[0]?.name ?? "telegram";

  const chat = useQuery({
    queryKey: ["chat", chatId],
    queryFn: () => getChat(chatId!),
    enabled: !!chatId,
  });

  const messages = useQuery({
    queryKey: ["conversation-messages", chatId, collection],
    queryFn: () => runQuery({
      question: "messages",
      collection_name: collection,
      top_k: 50,
      use_rag: false,
      filters: { conversation_id: chatId },
    }),
    enabled: !!chatId && !!collection,
  });

  const sources: TelegramSource[] = (messages.data?.sources ?? []).sort((a, b) => {
    if (!a.timestamp || !b.timestamp) return 0;
    return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
  });

  return (
    <div className="flex flex-col h-full animate-fade-in">
      {/* Back header */}
      <div className="flex items-center gap-3 mb-6">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} aria-label="Go back">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-foreground truncate">
            {chat.data?.title ?? chatId}
          </h1>
          {sources.length > 0 && (
            <p className="text-xs text-muted-foreground">{sources.length} indexed messages</p>
          )}
        </div>
      </div>

      {/* Loading */}
      {(messages.isLoading || chat.isLoading) && (
        <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading messages…</span>
        </div>
      )}

      {/* Error */}
      {messages.isError && (
        <EmptyExplorer
          title="Could not load messages"
          description="The backend returned an error. Please try again."
        />
      )}

      {/* Results */}
      {messages.isSuccess && sources.length === 0 && (
        <EmptyExplorer
          icon={<MessageCircle className="h-8 w-8" />}
          title="No indexed messages"
          description="This conversation has no messages in the knowledge base yet."
        />
      )}

      {sources.length > 0 && (
        <div
          className="flex-1 overflow-y-auto space-y-1 custom-scrollbar"
          role="list"
          aria-label="Conversation messages"
        >
          {sources.map((source, i) => (
            <div key={`${source.document_id}-${i}`} role="listitem">
              <MessageItem source={source} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
