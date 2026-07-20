import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCollections } from "@/hooks/useCollections";
import { runQuery } from "@/api/query.service";
import { FileText, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { DocumentCard } from "@/components/explorer/DocumentCard";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import { cn } from "@/lib/utils";
import type { TelegramSource } from "@/types/query";

type DocTab = "all" | "pdf" | "docx" | "xlsx" | "txt";

const DOC_TABS: Array<{ id: DocTab; label: string }> = [
  { id: "all", label: "All Documents" },
  { id: "pdf", label: "PDF" },
  { id: "docx", label: "Word" },
  { id: "xlsx", label: "Excel" },
  { id: "txt", label: "Text" },
];

const DOC_TYPES = ["pdf", "docx", "xlsx", "pptx", "txt", "document"];

export default function DocumentExplorerPage() {
  const collections = useCollections();
  const collection = collections.data?.collections?.[0]?.name ?? "telegram";
  const [tab, setTab] = useState<DocTab>("all");
  const [search, setSearch] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["documents", collection],
    queryFn: () => runQuery({
      question: "documents files pdf docx xlsx text attachments",
      collection_name: collection,
      top_k: 100,
      use_rag: false,
    }),
    enabled: !!collection,
  });

  const allDocs: TelegramSource[] = (data?.sources ?? []).filter(s =>
    DOC_TYPES.includes(s.content_type?.toLowerCase() ?? "") || !!s.filename
  );

  const tabFiltered: TelegramSource[] = tab === "all"
    ? allDocs
    : allDocs.filter(s => s.content_type?.toLowerCase() === tab || s.filename?.endsWith(`.${tab}`));

  const visible = search
    ? tabFiltered.filter(s =>
        s.filename?.toLowerCase().includes(search.toLowerCase()) ||
        s.snippet?.toLowerCase().includes(search.toLowerCase())
      )
    : tabFiltered;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <PageHeader
          title="Documents"
          description="Browse PDFs, Word docs, spreadsheets, and other files from your indexed chats."
        />
        <input
          type="search"
          placeholder="Filter documents…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 w-full sm:w-48"
          aria-label="Filter documents"
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Document types">
        {DOC_TABS.map(({ id, label }) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              "px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === id
                ? "border-accent text-accent"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading documents…</span>
        </div>
      )}

      {isError && (
        <EmptyExplorer title="Unable to load documents" description="The backend is unavailable." />
      )}

      {!isLoading && visible.length === 0 && (
        <EmptyExplorer
          icon={<FileText className="h-8 w-8" />}
          title="No documents found"
          description="Share files in your indexed Telegram chats to see them here."
        />
      )}

      {visible.length > 0 && (
        <div className="space-y-2" role="list" aria-label="Documents">
          {visible.map((source, i) => (
            <div key={`${source.document_id}-${i}`} role="listitem">
              <DocumentCard source={source} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
