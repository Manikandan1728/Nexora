import { MessageCircle, Hash } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import { Avatar, AvatarFallback } from "@/components/ui/Avatar";

interface PersonCardProps {
  senderId: string;
  senderName: string;
  messageCount: number;
  chats: string[];
  onClick?: () => void;
}

export function PersonCard({ senderId: _senderId, senderName, messageCount, chats, onClick }: PersonCardProps) {
  const initials = senderName
    .split(" ")
    .map(w => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <button
      onClick={onClick}
      className={cn(
        "group w-full text-left rounded-xl border border-border bg-surface p-4",
        "hover:border-accent/40 hover:shadow-md transition-all duration-150",
        "focus:outline-none focus:ring-2 focus:ring-accent/50"
      )}
    >
      <div className="flex items-start gap-3">
        <Avatar className="h-10 w-10 shrink-0 bg-accent/10">
          <AvatarFallback className="text-accent text-sm font-semibold">{initials}</AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="font-semibold text-sm text-foreground truncate">{senderName}</p>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <MessageCircle className="h-3 w-3" aria-hidden="true" />
              {messageCount} messages
            </span>
            <span className="flex items-center gap-1">
              <Hash className="h-3 w-3" aria-hidden="true" />
              {chats.length} chats
            </span>
          </div>
          {chats.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {chats.slice(0, 3).map((chat) => (
                <Badge key={chat} variant="outline" className="text-[10px]">
                  {chat}
                </Badge>
              ))}
              {chats.length > 3 && (
                <Badge variant="outline" className="text-[10px]">
                  +{chats.length - 3} more
                </Badge>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}
