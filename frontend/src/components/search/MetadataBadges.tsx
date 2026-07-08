import { Hash, Layers, MessageSquare, Image, Mic, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  metadata?: Record<string, unknown>;
  className?: string;
}

export function MetadataBadges({ metadata, className }: Props) {
  if (!metadata) return null;

  const chunkIndex = metadata.chunk_index as number | undefined;
  const tokenCount = metadata.token_count as number | undefined;
  const messageCount = metadata.message_count as number | undefined;
  const hasImages = Boolean(metadata.contains_images);
  const hasAudio = Boolean(metadata.contains_audio);
  const hasDocs = Boolean(metadata.contains_documents);

  const hasAnyBadge =
    chunkIndex !== undefined ||
    tokenCount !== undefined ||
    messageCount !== undefined ||
    hasImages ||
    hasAudio ||
    hasDocs;

  if (!hasAnyBadge) return null;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {chunkIndex !== undefined && (
        <span
          className="flex items-center gap-1 rounded bg-surface-hover px-1.5 py-0.5 text-xs text-muted-foreground"
          title="Chunk Index"
        >
          <Hash className="h-3 w-3" aria-hidden="true" />
          {chunkIndex}
        </span>
      )}
      {tokenCount !== undefined && (
        <span
          className="flex items-center gap-1 rounded bg-surface-hover px-1.5 py-0.5 text-xs text-muted-foreground"
          title="Token Count"
        >
          <Layers className="h-3 w-3" aria-hidden="true" />
          {tokenCount.toLocaleString()}
        </span>
      )}
      {messageCount !== undefined && (
        <span
          className="flex items-center gap-1 rounded bg-surface-hover px-1.5 py-0.5 text-xs text-muted-foreground"
          title="Message Count"
        >
          <MessageSquare className="h-3 w-3" aria-hidden="true" />
          {messageCount.toLocaleString()}
        </span>
      )}
      {hasImages && (
        <span
          className="flex items-center justify-center rounded bg-surface-hover p-0.5 text-muted-foreground"
          title="Contains Images"
        >
          <Image className="h-3 w-3" aria-hidden="true" />
        </span>
      )}
      {hasAudio && (
        <span
          className="flex items-center justify-center rounded bg-surface-hover p-0.5 text-muted-foreground"
          title="Contains Audio"
        >
          <Mic className="h-3 w-3" aria-hidden="true" />
        </span>
      )}
      {hasDocs && (
        <span
          className="flex items-center justify-center rounded bg-surface-hover p-0.5 text-muted-foreground"
          title="Contains Documents"
        >
          <FileText className="h-3 w-3" aria-hidden="true" />
        </span>
      )}
    </div>
  );
}
