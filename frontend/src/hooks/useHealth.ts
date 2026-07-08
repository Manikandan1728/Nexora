import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/health.service";
import { QUERY_KEYS } from "@/lib/constants";
import type { HealthResponse } from "@/types/health";
import type { ApiError } from "@/types/api";

export function useHealth() {
  return useQuery<HealthResponse, ApiError>({
    queryKey: QUERY_KEYS.health,
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: 1,
    staleTime: 25_000,
  });
}
