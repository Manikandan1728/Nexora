import { useState, useEffect, useRef, useCallback } from "react";
import { runQuery } from "@/api/query.service";
import type { QueryResponse, TelegramSource } from "@/types/query";

export interface ExplorerFilters {
  content_type?: string;
  sender_id?: string;
  conversation_id?: string;
}

export interface ExplorerSearchState {
  results: QueryResponse | null;
  isLoading: boolean;
  error: string | null;
  query: string;
  setQuery: (q: string) => void;
  filters: ExplorerFilters;
  setFilters: (f: ExplorerFilters) => void;
  search: (q: string, f?: ExplorerFilters) => void;
  reset: () => void;
}

const DEBOUNCE_MS = 400;

export function useExplorerSearch(
  collection: string,
  topK = 50
): ExplorerSearchState {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<ExplorerFilters>({});
  const [results, setResults] = useState<QueryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const search = useCallback(
    async (q: string, f: ExplorerFilters = filters) => {
      if (!q.trim()) {
        setResults(null);
        return;
      }
      // Cancel previous request
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();

      setIsLoading(true);
      setError(null);
      try {
        const apiFilters: Record<string, unknown> = {};
        if (f.content_type) apiFilters["content_type"] = f.content_type;
        if (f.sender_id) apiFilters["sender_id"] = f.sender_id;
        if (f.conversation_id) apiFilters["conversation_id"] = f.conversation_id;

        const data = await runQuery({
          question: q,
          collection_name: collection,
          top_k: topK,
          use_rag: false,
          filters: Object.keys(apiFilters).length > 0 ? apiFilters : undefined,
        });
        setResults(data);
      } catch (err: unknown) {
        if (err instanceof Error && err.name !== "AbortError") {
          setError(err.message ?? "Search failed");
        }
      } finally {
        setIsLoading(false);
      }
    },
    [collection, topK, filters]
  );

  // Debounced trigger whenever query or filters change
  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void search(query, filters);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, filters, search]);

  const reset = useCallback(() => {
    setQuery("");
    setFilters({});
    setResults(null);
    setError(null);
  }, []);

  return { results, isLoading, error, query, setQuery, filters, setFilters, search, reset };
}

// Helpers to extract unique values from results
export function uniqueSenders(sources: TelegramSource[]) {
  const seen = new Set<string>();
  return sources.filter((s) => {
    if (seen.has(s.sender_id)) return false;
    seen.add(s.sender_id);
    return true;
  });
}

export function uniqueConversations(sources: TelegramSource[]) {
  const seen = new Set<string>();
  return sources.filter((s) => {
    if (seen.has(s.conversation_id)) return false;
    seen.add(s.conversation_id);
    return true;
  });
}
