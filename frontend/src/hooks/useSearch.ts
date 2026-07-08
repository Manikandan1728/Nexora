import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { runQuery } from "@/api/query.service";
import type { QueryRequest, QueryResponse } from "@/types/query";
import type { ApiError } from "@/types/api";

export function useSearch() {
  return useMutation<QueryResponse, ApiError, QueryRequest>({
    mutationFn: runQuery,
    onError: (err) => {
      toast.error(err.message);
    },
  });
}
