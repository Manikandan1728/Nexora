import { Image, Video, Mic, Music, StickerIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TelegramSource } from "@/types/query";

const MEDIA_ICONS: Record<string, React.ElementType> = {
  image: Image,
  video: Video,
  voice: Mic,
  audio: Music,
  sticker: StickerIcon,
};

interface MediaCardProps {
  source: TelegramSource;
  onClick?: () => void;
}

export function MediaCard({ source, onClick }: MediaCardProps) {
  const ct = source.content_type?.toLowerCase() ?? "image";
  const Icon = MEDIA_ICONS[ct] ?? Image;

  const formattedDate = source.timestamp
    ? new Date(source.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : null;

  return (
    <button
      onClick={onClick}
      className={cn(
        "group relative aspect-square rounded-xl border border-border bg-surface overflow-hidden",
        "hover:border-accent/40 hover:shadow-lg transition-all duration-150",
        "focus:outline-none focus:ring-2 focus:ring-accent/50"
      )}
    >
      {/* Placeholder gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-accent/5 to-primary/5 flex items-center justify-center">
        <Icon className="h-8 w-8 text-muted-foreground/40" aria-hidden="true" />
      </div>

      {/* Overlay on hover */}
      <div className="absolute inset-0 bg-background/80 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-2">
        {source.sender_name && (
          <p className="text-xs font-medium text-foreground truncate">{source.sender_name}</p>
        )}
        <p className="text-[10px] text-muted-foreground truncate">{source.conversation_title}</p>
        {formattedDate && (
          <p className="text-[10px] text-muted-foreground">{formattedDate}</p>
        )}
      </div>

      {/* Type badge */}
      <div className="absolute top-2 left-2">
        <span className="rounded px-1 py-0.5 bg-background/70 backdrop-blur text-[10px] text-foreground uppercase">
          {ct}
        </span>
      </div>
    </button>
  );
}
