import { z } from "zod";

export const HealthResponseSchema = z.object({
  status: z.string(),
  app_name: z.string(),
  version: z.string(),
  engine_status: z.string(),
  llm_provider_available: z.boolean(),
});
