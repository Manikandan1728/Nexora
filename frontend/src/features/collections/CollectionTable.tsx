import { Search, Trash2, Database } from "lucide-react";
import { Link } from "react-router-dom";
import { displayCollectionName } from "@/lib/format";
import type { CollectionInfo } from "@/types/collections";
import { cn } from "@/lib/utils";

interface Props {
  collections: CollectionInfo[];
  onDelete: (name: string) => void;
  deletingName?: string;
}

export function CollectionTable({ collections, onDelete, deletingName }: Props) {
  return (
    <div className="rounded-xl bg-surface border border-border shadow-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Collections table">
          <thead>
            <tr className="border-b border-border bg-surface-hover">
              <th
                scope="col"
                className="px-5 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider"
              >
                Collection
              </th>
              <th
                scope="col"
                className="px-5 py-3 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider"
              >
                Chunks
              </th>
              <th
                scope="col"
                className="hidden md:table-cell px-5 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider"
              >
                Embedding Model
              </th>
              <th
                scope="col"
                className="px-5 py-3 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wider"
              >
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {collections.map((col) => {
              const isDeleting = deletingName === col.name;
              return (
                <tr
                  key={col.name}
                  className={cn(
                    "hover:bg-surface-hover transition-colors",
                    isDeleting && "opacity-50"
                  )}
                  aria-busy={isDeleting}
                >
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <Database className="h-4 w-4 text-accent shrink-0" aria-hidden="true" />
                      <div className="min-w-0">
                        <p className="font-medium text-foreground truncate">
                          {displayCollectionName(col.name)}
                        </p>
                        <p className="text-xs text-muted-foreground font-mono truncate max-w-[200px]">
                          {col.name}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums font-medium text-foreground">
                    {col.document_count.toLocaleString()}
                  </td>
                  <td className="hidden md:table-cell px-5 py-3 text-muted-foreground text-xs font-mono">
                    {col.embedding_model}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        to="/search"
                        state={{ collection: col.name }}
                        className={cn(
                          "flex items-center gap-1 rounded-md border border-border",
                          "px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
                          "hover:text-accent hover:border-accent/40 transition-colors"
                        )}
                        aria-label={`Search ${col.name}`}
                      >
                        <Search className="h-3.5 w-3.5" aria-hidden="true" />
                        <span className="hidden sm:inline">Search</span>
                      </Link>
                      <button
                        type="button"
                        onClick={() => onDelete(col.name)}
                        disabled={isDeleting}
                        className={cn(
                          "flex items-center gap-1 rounded-md border border-border",
                          "px-2.5 py-1.5 text-xs font-medium text-muted-foreground",
                          "hover:text-danger hover:border-danger/40 transition-colors",
                          "disabled:opacity-50 disabled:cursor-not-allowed"
                        )}
                        aria-label={`Delete ${col.name}`}
                      >
                        {isDeleting ? (
                          <span className="h-3.5 w-3.5 rounded-full border-2 border-current/30 border-t-current animate-spin" aria-hidden="true" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        )}
                        <span className="hidden sm:inline">
                          {isDeleting ? "Deleting…" : "Delete"}
                        </span>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
