export const QUERY_KEYS = {
  health: ["health"] as const,
  collections: ["collections"] as const,
  query: (
    collection: string,
    question: string,
    topK: number,
    useRag: boolean
  ) => ["query", collection, question, topK, useRag] as const,
} as const;

export const MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024; // 200 MB

export const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: "LayoutDashboard" },
  { path: "/upload", label: "Upload", icon: "Upload" },
  { path: "/search", label: "Search", icon: "Search" },
  { path: "/collections", label: "Collections", icon: "Database" },
  { path: "/settings", label: "Settings", icon: "Settings" },
] as const;
