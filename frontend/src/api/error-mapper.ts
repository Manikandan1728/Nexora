import type { AxiosError } from "axios";
import { ZodError } from "zod";
import type { ApiError } from "@/types/api";

interface BackendErrorBody {
  error?: string;
  message?: string;
  detail?: string;
}

/**
 * Normalize every possible error into a single ApiError shape.
 * This is the ONLY place that touches raw Axios / Zod errors.
 * Everything above this boundary only ever sees ApiError.
 */
export function mapError(err: unknown): ApiError {
  // ── Zod parse failure (unexpected response shape from backend) ──────
  if (err instanceof ZodError) {
    const first = err.errors[0];
    return {
      status: 422,
      code: "parse_error",
      message: `Unexpected response shape: ${first?.message ?? "unknown"}`,
    };
  }

  // ── Axios error ───────────────────────────────────────────────────
  const axiosErr = err as AxiosError<BackendErrorBody>;
  if (axiosErr.isAxiosError) {
    if (!axiosErr.response) {
      // Network unreachable / timeout / ECONNREFUSED
      return {
        status: 0,
        code: "network_error",
        message:
          "Cannot reach the Nexora backend. Make sure the server is running.",
      };
    }

    const { status, data } = axiosErr.response;

    // Backend returns { error, message, detail? }
    const message =
      data?.message ?? data?.error ?? axiosErr.message ?? "An error occurred.";

    const code = data?.error ?? `http_${status}`;

    return { status, code, message };
  }

  // ── Unknown / re-thrown ApiError ──────────────────────────────────
  const maybe = err as Partial<ApiError>;
  if (typeof maybe.status === "number" && typeof maybe.message === "string") {
    return maybe as ApiError;
  }

  // ── Fallback ──────────────────────────────────────────────────────
  const msg = err instanceof Error ? err.message : "An unexpected error occurred.";
  return { status: 500, code: "unknown", message: msg };
}
