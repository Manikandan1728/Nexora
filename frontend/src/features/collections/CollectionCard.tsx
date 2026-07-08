import { Database, Search, Trash2, Hash, Layers } from "lucide-react";
import { Link } from "react-router-dom";
import { displayCollectionName } from "@/lib/format";
import type { CollectionInfo } from "@/types/collections";
import { cn } from "@/lib/utils";

interface Props {
  collection: CollectionInfo;
  onDelete: (name: string) => void;
  isDeleting: boolean;
}

export function CollectionCard({ collection, onDelete, isDeleting }: Props) {
  return (
    <div
      className={cn(
        "group rounded-xl bg-surface border border-border p-5 shadow-card",
        "hover:shadow-card-lg hover:border-accent/30 transition-all duration-200",
        "flex flex-col gap-4 animate-fade-in"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
            <Database className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p
              className="text-sm font-semibold text-foreground truncate"
              title={collection.name}
            >
              {displayCollectionName(collection.name)}
            </p>
            <p className="text-xs text-muted-foreground font-mono truncate">
              {collection.name}
            </p>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-lg bg-surface-hover px-3 py-2 flex items-center gap-2">
          <Hash className="h-3.5 w-3.5 text-muted-foreground shrink-0" aria-hidden="true" />
          <div>
            <p className="text-xs text-muted-foreground">Chunks</p>
            <p className="text-sm font-bold text-foreground tabular-nums">
              {collection.document_count.toLocaleString()}
            </p>
          </div>
        </div>
        <div className="rounded-lg bg-surface-hover px-3 py-2 flex items-center gap-2">
          <Layers className="h-3.5 w-3.5 text-muted-foreground shrink-0" aria-hidden="true" />
          <div>
            <p className="text-xs text-muted-foreground">Model</p>
            <p className="text-xs font-medium text-foreground truncate max-w-[80px]" title={collection.embedding_model}>
              {collection.embedding_model}
            </p>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 mt-auto">
        <Link
          to="/search"
          state={{ collection: collection.name }}
          className={cn(
            "flex-1 flex items-center justify-center gap-1.5 rounded-lg",
            "border border-border bg-surface-hover px-3 py-2 text-xs font-medium text-foreground",
            "hover:border-accent/40 hover:text-accent transition-colors"
          )}
          aria-label={`Search ${collection.name}`}
        >
          <Search className="h-3.5 w-3.5" aria-hidden="true" />
          Search
        </Link>
        <button
          type="button"
          onClick={() => onDelete(collection.name)}
          disabled={isDeleting}
          className={cn(
            "flex items-center justify-center gap-1.5 rounded-lg",
            "border border-border bg-surface-hover px-3 py-2 text-xs font-medium",
            "text-muted-foreground hover:text-danger hover:border-danger/40 transition-colors",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
          aria-label={`Delete ${collection.name}`}
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          Delete
        </button>
      </div>
    </div>
  );
}
