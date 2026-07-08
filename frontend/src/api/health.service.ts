import { healthClient } from "./client";
import { HealthResponseSchema } from "@/schemas/health.schema";
import { mapError } from "./error-mapper";
import type { HealthResponse } from "@/types/health";

export async function fetchHealth(): Promise<HealthResponse> {
  try {
    const { data } = await healthClient.get("/health");
    return HealthResponseSchema.parse(data);
  } catch (err) {
    throw mapError(err);
  }
}
