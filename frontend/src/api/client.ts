import axios from "axios";
import { mapError } from "./error-mapper";

/**
 * Base URL strategy (Step 0 decision):
 *  - Dev: requests go to /api/* which the Vite dev proxy forwards to
 *    http://127.0.0.1:8000, stripping the /api prefix. This sidesteps
 *    missing CORS headers on the backend.
 *  - Production: set VITE_API_BASE_URL to the real backend URL. The
 *    production server must add CORS headers.
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL
  ? String(import.meta.env.VITE_API_BASE_URL)
  : "/api";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 15_000,
  headers: { "Content-Type": "application/json" },
});

// Short timeout for health polls so they don't hang the UI
export const healthClient = axios.create({
  baseURL: BASE_URL,
  timeout: 3_000,
  headers: { "Content-Type": "application/json" },
});

// Normalize every error before it leaves this layer
function attachErrorInterceptor(instance: typeof apiClient) {
  instance.interceptors.response.use(
    (response) => response,
    (err: unknown) => {
      throw mapError(err);
    }
  );
}

attachErrorInterceptor(apiClient);
attachErrorInterceptor(healthClient);
