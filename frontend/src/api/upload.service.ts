import { apiClient } from "./client";
import { UploadResponseSchema } from "@/schemas/upload.schema";
import { mapError } from "./error-mapper";
import type { UploadResponse } from "@/types/upload";

export async function uploadZip(
  file: File,
  onProgress?: (percent: number) => void
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);

  try {
    const { data } = await apiClient.post("/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 600_000, // 10 min — large ZIPs take time
      onUploadProgress(evt) {
        if (onProgress && evt.total) {
          onProgress(Math.round((evt.loaded / evt.total) * 100));
        }
      },
    });
    return UploadResponseSchema.parse(data);
  } catch (err) {
    throw mapError(err);
  }
}
