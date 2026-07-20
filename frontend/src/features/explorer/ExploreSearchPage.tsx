import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Search, X, Clock, ArrowRight } from "lucide-react";
import { useCollections } from "@/hooks/useCollections";
import { useExplorerSearch } from "@/hooks/useExplorerSearch";
import { useRecentSearches } from "@/hooks/useRecentSearches";
import { FilterSidebar } from "@/components/explorer/FilterSidebar";
import { SearchResultsPanel } from "@/components/explorer/SearchResultsPanel";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import { uniqueSenders, uniqueConversations } from "@/hooks/useExplorerSearch";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { cn } from "@/lib/utils";

export default function ExploreSearchPage() {
  const navigate = useNavigate();
  const collectionsQuery = useCollections();
  const collections = collectionsQuery.data?.collections ?? [];
  const [selectedCollection, setSelectedCollection] = useState<string>("");

  // Use first available collection if none selected
  const activeCollection = selectedCollection || collections[0]?.name || "telegram";

  const explorer = useExplorerSearch(activeCollection, 50);
  const { recent, addSearch, removeSearch, clearAll } = useRecentSearches();
  const [isFocused, setIsFocused] = useState(false);

  const handleSearch = useCallback((q: string) => {
    if (q.trim()) {
      explorer.setQuery(q);
      addSearch(q);
    }
  }, [explorer, addSearch]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      handleSearch(explorer.query);
    }
    if (e.key === "Escape") {
      explorer.reset();
    }
  };

  // Derive filter options from results
  const sources = explorer.results?.sources ?? [];
  const senderOptions = uniqueSenders(sources).map(s => ({ id: s.sender_id, name: s.sender_name }));
  const chatOptions = uniqueConversations(sources).map(s => ({ id: s.conversation_id, title: s.conversation_title }));

  const showDropdown = isFocused && !explorer.query && recent.length > 0;

  return (
    <div className="flex flex-col h-full gap-0 animate-fade-in">
      <PageHeader
        title="Knowledge Search"
        description="Semantically search everything Nexora has indexed from your Telegram."
      />

      {/* Search bar */}
      <div className="relative mb-6">
        <div className={cn(
          "flex items-center gap-3 rounded-2xl border bg-surface px-4 py-3 shadow-card transition-all",
          isFocused ? "border-accent/50 ring-1 ring-accent/30" : "border-border"
        )}>
          <Search className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            placeholder="Search your knowledge base…"
            value={explorer.query}
            onChange={e => explorer.setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setTimeout(() => setIsFocused(false), 150)}
            className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            aria-label="Search knowledge base"
            autoComplete="off"
          />
          {/* Collection selector */}
          {collections.length > 1 && (
            <select
              value={activeCollection}
              onChange={e => setSelectedCollection(e.target.value)}
              className="text-xs text-muted-foreground bg-transparent border-l border-border pl-3 ml-1 outline-none cursor-pointer"
              aria-label="Select collection"
            >
              {collections.map(c => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>
          )}
          {explorer.query && (
            <button
              onClick={() => explorer.reset()}
              className="text-muted-foreground hover:text-foreground transition-colors"
              aria-label="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Recent searches dropdown */}
        {showDropdown && (
          <div className="absolute top-full left-0 right-0 z-20 mt-1 rounded-xl border border-border bg-surface shadow-lg p-2 animate-fade-in">
            <div className="flex items-center justify-between px-2 py-1 mb-1">
              <span className="text-xs text-muted-foreground font-medium">Recent searches</span>
              <button onClick={clearAll} className="text-xs text-muted-foreground hover:text-foreground">Clear all</button>
            </div>
            {recent.map((q) => (
              <div key={q} className="flex items-center gap-2 group">
                <button
                  onClick={() => handleSearch(q)}
                  className="flex-1 flex items-center gap-2 px-2 py-1.5 rounded text-sm text-muted-foreground hover:text-foreground hover:bg-surface/80 text-left"
                >
                  <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span className="truncate">{q}</span>
                </button>
                <button
                  onClick={() => removeSearch(q)}
                  className="p-1 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-danger transition-opacity"
                  aria-label={`Remove "${q}" from recent searches`}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Two-column layout */}
      <div className="flex gap-6 flex-1 min-h-0">
        {/* Filters */}
        <aside className="hidden lg:block w-56 shrink-0">
          <FilterSidebar
            filters={explorer.filters}
            onChange={explorer.setFilters}
            senderOptions={senderOptions}
            chatOptions={chatOptions}
          />
        </aside>

        {/* Results */}
        <div className="flex-1 min-w-0">
          {collectionsQuery.isLoading ? (
            <LoadingSkeleton variant="card" />
          ) : collections.length === 0 ? (
            <EmptyExplorer
              title="No indexed data yet"
              description="Connect Telegram and enable chat indexing to start exploring your knowledge."
              action={
                <button
                  onClick={() => navigate("/telegram")}
                  className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 transition-opacity"
                >
                  Connect Telegram <ArrowRight className="h-4 w-4" />
                </button>
              }
            />
          ) : !explorer.query ? (
            <EmptyExplorer
              icon={<Search className="h-8 w-8" />}
              title="Start searching"
              description="Type a question or keyword to search across all indexed Telegram content."
            />
          ) : (
            <SearchResultsPanel
              data={explorer.results}
              isLoading={explorer.isLoading}
              error={explorer.error}
            />
          )}
        </div>
      </div>
    </div>
  );
}
