import { useState, useCallback, useEffect } from "react";

const STORAGE_KEY = "nexora_recent_searches";
const MAX_RECENT = 10;

export function useRecentSearches() {
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setRecent(JSON.parse(stored) as string[]);
    } catch {
      // ignore
    }
  }, []);

  const addSearch = useCallback((query: string) => {
    if (!query.trim()) return;
    setRecent((prev) => {
      const filtered = prev.filter((q) => q !== query);
      const next = [query, ...filtered].slice(0, MAX_RECENT);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const removeSearch = useCallback((query: string) => {
    setRecent((prev) => {
      const next = prev.filter((q) => q !== query);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setRecent([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  return { recent, addSearch, removeSearch, clearAll };
}
