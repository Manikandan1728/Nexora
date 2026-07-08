/** Format bytes into human-readable string */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const size = sizes[i] ?? "B";
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${size}`;
}

/** Format elapsed seconds into a readable duration */
export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

/** Format a similarity score [0..1] as a percentage string */
export function formatScore(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

/** Truncate text to maxLen chars with ellipsis */
export function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen).trimEnd() + "…";
}

/** Strip the nexora_ prefix from collection names for display */
export function displayCollectionName(name: string): string {
  return name.replace(/^nexora_/, "").replace(/_/g, " ");
}
