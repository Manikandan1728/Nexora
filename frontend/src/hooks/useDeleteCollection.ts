import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { deleteCollection } from "@/api/collections.service";
import { QUERY_KEYS } from "@/lib/constants";
import type { ApiError } from "@/types/api";

export function useDeleteCollection() {
  const queryClient = useQueryClient();

  return useMutation<{ message: string }, ApiError, string>({
    mutationFn: async (name: string) => {
      const res = await deleteCollection(name);
      return { message: res.message };
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.collections });
      toast.success(data.message);
    },
    onError: (err) => {
      toast.error(err.message);
    },
  });
}
