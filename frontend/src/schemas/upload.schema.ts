import { z } from "zod";

export const PhaseStatusSchema = z.object({
  phase: z.string(),
  status: z.string(),
  detail: z.string().nullish(),
});

export const UploadResponseSchema = z.object({
  collection_name: z.string(),
  messages_parsed: z.number().int(),
  chunks_created: z.number().int(),
  vectors_indexed: z.number().int(),
  phase_statuses: z.array(PhaseStatusSchema).optional(),
  elapsed_seconds: z.number(),
});
