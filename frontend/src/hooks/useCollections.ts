import { useQuery } from "@tanstack/react-query";
import { listCollections } from "@/api/collections.service";
import { QUERY_KEYS } from "@/lib/constants";
import type { CollectionListResponse } from "@/types/collections";
import type { ApiError } from "@/types/api";

export function useCollections() {
  return useQuery<CollectionListResponse, ApiError>({
    queryKey: QUERY_KEYS.collections,
    queryFn: listCollections,
    staleTime: 60_000,
  });
}
