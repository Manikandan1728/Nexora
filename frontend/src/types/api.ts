/** Normalized API error shape — the only error type that escapes the API layer. */
export interface ApiError {
  status: number;
  message: string;
  code: string;
}
