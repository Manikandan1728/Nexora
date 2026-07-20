import { useState } from "react";
import { LayoutGrid, List, MessageSquare } from "lucide-react";
import { Link } from "react-router-dom";
import { useCollections } from "@/hooks/useCollections";
import { useDeleteCollection } from "@/hooks/useDeleteCollection";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { CollectionCard } from "./CollectionCard";
import { CollectionTable } from "./CollectionTable";
import { ConfirmDialog } from "./ConfirmDialog";
import { Database } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ApiError } from "@/types/api";

type ViewMode = "grid" | "table";

export default function CollectionsPage() {
  const { data, isLoading, isError, error, refetch } = useCollections();
  const deleteCollection = useDeleteCollection();
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  const collections = data?.collections ?? [];

  function requestDelete(name: string) {
    setPendingDelete(name);
  }

  function confirmDelete() {
    if (!pendingDelete) return;
    deleteCollection.mutate(pendingDelete, {
      onSettled: () => setPendingDelete(null),
    });
  }

  if (isLoading) return <LoadingSkeleton variant="page" />;

  if (isError) {
    return (
      <ErrorState
        error={error as ApiError}
        title="Failed to load collections"
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <>
      <div className="space-y-6 animate-fade-in">
        <PageHeader
          title="Collections"
          description={`${data?.total ?? 0} knowledge base${data?.total !== 1 ? "s" : ""} available`}
          actions={
            <div className="flex items-center gap-2">
              {/* View mode toggle */}
              <div className="flex items-center rounded-lg border border-border bg-surface p-1 gap-0.5">
                <button
                  type="button"
                  onClick={() => setViewMode("grid")}
                  className={cn(
                    "p-1.5 rounded-md transition-colors",
                    viewMode === "grid"
                      ? "bg-accent/10 text-accent"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                  aria-label="Grid view"
                  aria-pressed={viewMode === "grid"}
                >
                  <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("table")}
                  className={cn(
                    "p-1.5 rounded-md transition-colors",
                    viewMode === "table"
                      ? "bg-accent/10 text-accent"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                  aria-label="Table view"
                  aria-pressed={viewMode === "table"}
                >
                  <List className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>

              <Link
                to="/telegram"
                className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-xs font-semibold text-accent-foreground hover:opacity-90 transition-opacity"
              >
                <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
                Connect Telegram
              </Link>
            </div>
          }
        />

        {collections.length === 0 ? (
          <EmptyState
            icon={<Database className="h-6 w-6" />}
            title="No collections yet"
            description="Connect Telegram and enable indexing to create your first knowledge base."
            action={
              <Link
                to="/telegram"
                className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground hover:opacity-90 transition-opacity"
              >
                Connect Telegram
              </Link>
            }
          />
        ) : viewMode === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {collections.map((col) => (
              <CollectionCard
                key={col.name}
                collection={col}
                onDelete={requestDelete}
                isDeleting={
                  deleteCollection.isPending &&
                  deleteCollection.variables === col.name
                }
              />
            ))}
          </div>
        ) : (
          <CollectionTable
            collections={collections}
            onDelete={requestDelete}
            deletingName={
              deleteCollection.isPending ? deleteCollection.variables : undefined
            }
          />
        )}
      </div>

      {/* Confirm delete dialog */}
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete Collection"
        message={
          pendingDelete
            ? `Are you sure you want to delete "${pendingDelete}"? This action cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
        isPending={deleteCollection.isPending}
        variant="danger"
      />
    </>
  );
}
