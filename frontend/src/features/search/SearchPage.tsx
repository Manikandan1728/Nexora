import { useLocation } from "react-router-dom";
import { useSearch } from "@/hooks/useSearch";
import { useCollections } from "@/hooks/useCollections";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { SearchForm } from "./SearchForm";
import { AnswerPanel } from "./AnswerPanel";
import { CitationList } from "./CitationList";
import { Search, Upload, SearchX } from "lucide-react";
import { Link } from "react-router-dom";
import type { ApiError } from "@/types/api";

export default function SearchPage() {
  const location = useLocation();
  const defaultCollection = (location.state as { collection?: string } | null)?.collection;

  const collectionsQuery = useCollections();
  const search = useSearch();

  const collections = collectionsQuery.data?.collections ?? [];

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      <PageHeader
        title="Search"
        description="Ask questions about your knowledge base and get AI-powered answers."
      />

      {/* Collections loading */}
      {collectionsQuery.isLoading && (
        <LoadingSkeleton variant="card" />
      )}

      {/* No collections */}
      {!collectionsQuery.isLoading && collections.length === 0 && (
        <EmptyState
          icon={<Upload className="h-6 w-6" />}
          title="No collections yet"
          description="Upload a WhatsApp chat ZIP to create your first knowledge base."
          action={
            <Link
              to="/upload"
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground hover:opacity-90 transition-opacity"
            >
              Go to Upload
            </Link>
          }
        />
      )}

      {/* Search form */}
      {collections.length > 0 && (
        <div className="rounded-xl bg-surface border border-border p-5 shadow-card">
          <div className="flex items-center gap-2 mb-4">
            <Search className="h-4 w-4 text-accent" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-foreground">Ask a Question</h2>
          </div>
          <SearchForm
            collections={collections}
            defaultCollection={defaultCollection}
            onSubmit={(req) => search.mutate(req)}
            isPending={search.isPending}
          />
        </div>
      )}

      {/* Error */}
      {search.isError && (
        <ErrorState
          error={search.error as ApiError}
          title="Search failed"
          onRetry={() => search.reset()}
        />
      )}

      {/* Results */}
      {search.isPending && (
        <div className="space-y-3">
          <LoadingSkeleton variant="card" />
          <LoadingSkeleton variant="card" />
        </div>
      )}

      {search.isSuccess && search.data && !search.isPending && (
        <div className="space-y-6">
          {search.data.retrieved_documents?.length === 0 ? (
            <EmptyState
              icon={<SearchX className="h-6 w-6" />}
              title="No relevant conversations found."
              description="Try adjusting your search terms or expanding your query."
            />
          ) : (
            <>
              <AnswerPanel result={search.data} />
              {search.data.citations && search.data.citations.length > 0 && (
                <CitationList citations={search.data.citations} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
