import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Users, Radio, Search, ToggleLeft, ToggleRight, Trash2, Loader2 } from "lucide-react";
import { listChats, updateChat, deleteChatData } from "@/api/telegram.service";
import type { TelegramChat, ChatType } from "@/types/telegram";
import { cn } from "@/lib/utils";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Avatar, AvatarFallback } from "@/components/ui/Avatar";

const CHAT_TYPE_ICON: Record<ChatType, React.ReactNode> = {
  private:    <MessageSquare className="h-3.5 w-3.5" />,
  group:      <Users className="h-3.5 w-3.5" />,
  supergroup: <Users className="h-3.5 w-3.5" />,
  channel:    <Radio className="h-3.5 w-3.5" />,
  bot:        <MessageSquare className="h-3.5 w-3.5" />,
  unknown:    <MessageSquare className="h-3.5 w-3.5" />,
};

function ChatCard({ chat, onToggle, onDelete }: {
  chat: TelegramChat;
  onToggle: (chat_id: string, enabled: boolean) => void;
  onDelete: (chat_id: string) => void;
}) {
  return (
    <Card className={cn("p-4 flex flex-col gap-3 transition-shadow hover:shadow-md", chat.indexing_enabled && "border-accent/50 bg-accent/5")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Avatar>
            <AvatarFallback>{chat.title.substring(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
          <div className="flex flex-col">
            <span className="font-semibold text-sm truncate">{chat.title}</span>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-muted-foreground flex items-center gap-1">
                {CHAT_TYPE_ICON[chat.chat_type]}
              </span>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                {chat.chat_type}
              </Badge>
            </div>
          </div>
        </div>
        <button
          onClick={() => onToggle(chat.chat_id, !chat.indexing_enabled)}
          aria-label={chat.indexing_enabled ? "Disable indexing" : "Enable indexing"}
          className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
        >
          {chat.indexing_enabled
            ? <ToggleRight className="h-6 w-6 text-accent" />
            : <ToggleLeft className="h-6 w-6" />}
        </button>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground pt-2">
        {chat.last_activity && (
          <span>Last active: {new Date(chat.last_activity).toLocaleDateString()}</span>
        )}
        {chat.indexing_enabled_at && (
          <span>Indexing since: {new Date(chat.indexing_enabled_at).toLocaleString()}</span>
        )}
      </div>

      {chat.indexing_enabled && (
        <button
          onClick={() => onDelete(chat.chat_id)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-destructive transition-colors self-start mt-2"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete indexed data
        </button>
      )}
    </Card>
  );
}

export default function TelegramChatSelectionPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const { data, isLoading, error } = useQuery({
    queryKey: ["telegram-chats"],
    queryFn: listChats,
  });

  const toggleMut = useMutation({
    mutationFn: ({ chat_id, enabled }: { chat_id: string; enabled: boolean }) =>
      updateChat(chat_id, { indexing_enabled: enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-chats"] }),
  });

  const deleteMut = useMutation({
    mutationFn: (chat_id: string) => deleteChatData(chat_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-chats"] }),
  });

  const chats = data?.chats ?? [];
  const filtered = chats
    .filter(c => c.title.toLowerCase().includes(filter.toLowerCase()))
    .filter(c => typeFilter === "all" || c.chat_type === typeFilter);

  const navigate = useNavigate();

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6 pt-10 pb-20 animate-in fade-in zoom-in-95 duration-500">
      <div className="text-center space-y-2 mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Select Chats</h1>
        <p className="text-muted-foreground">Choose which conversations Nexora should index.</p>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            type="text"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Search chats…"
            className="pl-9"
          />
        </div>
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="h-10 rounded-md border border-border bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        >
          <option value="all">All types</option>
          <option value="private">Private</option>
          <option value="group">Group</option>
          <option value="supergroup">Supergroup</option>
          <option value="channel">Channel</option>
        </select>
      </div>

      {/* List */}
      {isLoading && (
        <div className="flex items-center gap-2 text-muted-foreground text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading chats…
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive">Failed to load chats. Is the backend running?</p>
      )}

      <div className="space-y-3">
        {filtered.map(chat => (
          <ChatCard
            key={chat.chat_id}
            chat={chat}
            onToggle={(id, enabled) => toggleMut.mutate({ chat_id: id, enabled })}
            onDelete={id => deleteMut.mutate(id)}
          />
        ))}
        {filtered.length === 0 && !isLoading && (
          <div className="text-center py-8 text-muted-foreground text-sm">
            No chats found matching your criteria.
          </div>
        )}
      </div>

      {chats.length > 0 && (
        <div className="pt-8 border-t border-border flex justify-end">
          <Button 
            size="lg" 
            onClick={() => navigate("/telegram/status")}
          >
            Continue to Indexing Status
          </Button>
        </div>
      )}

      <p className="text-xs text-muted-foreground border-t border-border pt-3">
        Only messages received after enabling indexing are processed.
        Historical messages are never indexed.
      </p>
    </div>
  );
}
