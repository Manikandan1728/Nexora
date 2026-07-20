import { FileText, File, FileSpreadsheet, Presentation, AlignLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import type { TelegramSource } from "@/types/query";

const TYPE_ICONS: Record<string, React.ElementType> = {
  pdf: FileText,
  docx: FileText,
  xlsx: FileSpreadsheet,
  pptx: Presentation,
  txt: AlignLeft,
};

interface DocumentCardProps {
  source: TelegramSource;
  onClick?: () => void;
}

export function DocumentCard({ source, onClick }: DocumentCardProps) {
  const ext = (source.content_type ?? source.filename?.split(".").pop() ?? "").toLowerCase();
  const Icon = TYPE_ICONS[ext] ?? File;

  const formattedDate = source.timestamp
    ? new Date(source.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
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
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 shrink-0 rounded-lg bg-accent/10 flex items-center justify-center">
          <Icon className="h-5 w-5 text-accent" aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground truncate">
            {source.filename || "(untitled)"}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
            {source.snippet}
          </p>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant="outline" className="text-[10px]">{ext.toUpperCase() || "FILE"}</Badge>
            {source.conversation_title && (
              <span className="text-[10px] text-muted-foreground truncate">{source.conversation_title}</span>
            )}
            {formattedDate && (
              <span className="text-[10px] text-muted-foreground ml-auto shrink-0">{formattedDate}</span>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}
