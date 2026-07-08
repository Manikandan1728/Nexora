import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { uploadZip } from "@/api/upload.service";
import { QUERY_KEYS } from "@/lib/constants";
import type { UploadResponse } from "@/types/upload";
import type { ApiError } from "@/types/api";

export function useUpload() {
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState(0);

  const mutation = useMutation<UploadResponse, ApiError, File>({
    mutationFn: (file: File) => uploadZip(file, setProgress),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.collections });
      toast.success("Upload complete! Collection is ready to search.");
    },
    onError: (err) => {
      toast.error(err.message);
    },
    onMutate: () => {
      setProgress(0);
    },
    onSettled: () => {
      // keep progress at 100 briefly so the bar fills visually
    },
  });

  return { ...mutation, progress };
}
