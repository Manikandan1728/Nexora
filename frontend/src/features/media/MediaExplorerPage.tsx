import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCollections } from "@/hooks/useCollections";
import { runQuery } from "@/api/query.service";
import { Image, Video, Mic, Music, Loader2, Filter } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { MediaCard } from "@/components/explorer/MediaCard";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import { cn } from "@/lib/utils";
import type { TelegramSource } from "@/types/query";

type MediaTab = "all" | "image" | "video" | "audio" | "voice";

const MEDIA_TABS: Array<{ id: MediaTab; label: string; Icon: React.ElementType }> = [
  { id: "all", label: "All", Icon: Filter },
  { id: "image", label: "Images", Icon: Image },
  { id: "video", label: "Video", Icon: Video },
  { id: "audio", label: "Audio", Icon: Music },
  { id: "voice", label: "Voice", Icon: Mic },
];

export default function MediaExplorerPage() {
  const collections = useCollections();
  const collection = collections.data?.collections?.[0]?.name ?? "telegram";
  const [tab, setTab] = useState<MediaTab>("all");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["media", collection],
    queryFn: () => runQuery({
      question: "media images video audio voice files attachments",
      collection_name: collection,
      top_k: 100,
      use_rag: false,
    }),
    enabled: !!collection,
  });

  const allMedia = (data?.sources ?? []).filter(s =>
    ["image", "video", "audio", "voice", "sticker"].includes(s.content_type?.toLowerCase() ?? "")
  );

  const visible: TelegramSource[] = tab === "all"
    ? allMedia
    : allMedia.filter(s => s.content_type?.toLowerCase() === tab);

  const tabCounts = MEDIA_TABS.reduce((acc, t) => {
    acc[t.id] = t.id === "all" ? allMedia.length : allMedia.filter(s => s.content_type?.toLowerCase() === t.id).length;
    return acc;
  }, {} as Record<MediaTab, number>);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Media"
        description="Browse images, videos, audio, and voice notes from your indexed Telegram chats."
      />

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Media types">
        {MEDIA_TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === id
                ? "border-accent text-accent"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {label}
            <span className="text-xs text-muted-foreground">({tabCounts[id]})</span>
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading media…</span>
        </div>
      )}

      {isError && (
        <EmptyExplorer title="Unable to load media" description="The backend is unavailable." />
      )}

      {!isLoading && visible.length === 0 && (
        <EmptyExplorer
          icon={<Image className="h-8 w-8" />}
          title="No media found"
          description="Try indexing chats that contain images, videos, or voice notes."
        />
      )}

      {/* Grid */}
      {visible.length > 0 && (
        <div
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"
          role="list"
          aria-label="Media grid"
        >
          {visible.map((source, i) => (
            <div key={`${source.document_id}-${i}`} role="listitem">
              <MediaCard source={source} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
