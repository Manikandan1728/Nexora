import { apiClient } from "./client";
import { QueryResponseSchema } from "@/schemas/query.schema";
import { mapError } from "./error-mapper";
import type { QueryRequest, QueryResponse } from "@/types/query";

export async function runQuery(req: QueryRequest): Promise<QueryResponse> {
  try {
    const { data } = await apiClient.post("/query", req, {
      timeout: 120_000, // RAG can be slow
    });
    return QueryResponseSchema.parse(data);
  } catch (err) {
    throw mapError(err);
  }
}
