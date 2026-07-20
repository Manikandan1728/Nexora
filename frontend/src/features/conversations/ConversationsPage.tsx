import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listChats } from "@/api/telegram.service";
import { MessageSquare, Users, Radio, Hash, ChevronRight, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Avatar, AvatarFallback } from "@/components/ui/Avatar";
import { PageHeader } from "@/components/common/PageHeader";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import type { TelegramChat, ChatType } from "@/types/telegram";
import { useState } from "react";

const CHAT_ICON: Record<ChatType, React.ElementType> = {
  private: MessageSquare,
  group: Users,
  supergroup: Users,
  channel: Radio,
  bot: MessageSquare,
  unknown: Hash,
};

function ChatListItem({ chat, onClick }: { chat: TelegramChat; onClick: () => void }) {
  const Icon = CHAT_ICON[chat.chat_type] ?? MessageSquare;
  const initials = chat.title.slice(0, 2).toUpperCase();
  const formattedDate = chat.last_activity
    ? new Date(chat.last_activity).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : null;

  return (
    <button
      onClick={onClick}
      className={cn(
        "group w-full text-left rounded-xl border border-border bg-surface p-4",
        "hover:border-accent/40 hover:shadow-md transition-all duration-150",
        "focus:outline-none focus:ring-2 focus:ring-accent/50"
      )}
    >
      <div className="flex items-center gap-3">
        <Avatar className="h-10 w-10 shrink-0">
          <AvatarFallback className="bg-accent/10 text-accent text-sm font-semibold">{initials}</AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="font-semibold text-sm text-foreground truncate">{chat.title}</p>
            <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" aria-hidden="true" />
          </div>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="outline" className="text-[10px] gap-0.5">
              <Icon className="h-2.5 w-2.5 mr-0.5" aria-hidden="true" />
              {chat.chat_type}
            </Badge>
            <Badge
              variant={chat.indexing_enabled ? "default" : "secondary"}
              className="text-[10px]"
            >
              {chat.indexing_enabled ? "Indexed" : "Not indexed"}
            </Badge>
            {formattedDate && (
              <span className="text-[10px] text-muted-foreground ml-auto">{formattedDate}</span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

export default function ConversationsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["telegram-chats"],
    queryFn: listChats,
  });

  const chats = (data?.chats ?? []).filter(c =>
    !search || c.title.toLowerCase().includes(search.toLowerCase())
  );
  const indexed = chats.filter(c => c.indexing_enabled);
  const notIndexed = chats.filter(c => !c.indexing_enabled);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Loading conversations…</span>
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyExplorer
        title="Unable to load conversations"
        description="The backend is unavailable. Make sure the Nexora API is running."
      />
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <PageHeader
          title="Conversations"
          description={`${data?.total ?? 0} Telegram chats found, ${indexed.length} indexed.`}
        />
        <input
          type="search"
          placeholder="Filter chats…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 w-full sm:w-56"
          aria-label="Filter chats"
        />
      </div>

      {chats.length === 0 ? (
        <EmptyExplorer
          icon={<MessageSquare className="h-8 w-8" />}
          title="No chats found"
          description={search ? "Try a different filter." : "Connect and index your Telegram to see conversations here."}
        />
      ) : (
        <div className="space-y-6">
          {indexed.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                Indexed ({indexed.length})
              </h2>
              <div className="space-y-2">
                {indexed.map(chat => (
                  <ChatListItem
                    key={chat.chat_id}
                    chat={chat}
                    onClick={() => navigate(`/conversations/${chat.chat_id}`)}
                  />
                ))}
              </div>
            </section>
          )}
          {notIndexed.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                Not Indexed ({notIndexed.length})
              </h2>
              <div className="space-y-2 opacity-60">
                {notIndexed.map(chat => (
                  <ChatListItem
                    key={chat.chat_id}
                    chat={chat}
                    onClick={() => {}}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
