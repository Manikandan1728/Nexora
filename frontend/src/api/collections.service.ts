import { apiClient } from "./client";
import {
  CollectionListResponseSchema,
  DeleteCollectionResponseSchema,
} from "@/schemas/collections.schema";
import { mapError } from "./error-mapper";
import type {
  CollectionListResponse,
  DeleteCollectionResponse,
} from "@/types/collections";

export async function listCollections(): Promise<CollectionListResponse> {
  try {
    const { data } = await apiClient.get("/collections");
    return CollectionListResponseSchema.parse(data);
  } catch (err) {
    throw mapError(err);
  }
}

export async function deleteCollection(
  name: string
): Promise<DeleteCollectionResponse> {
  try {
    const { data } = await apiClient.delete(
      `/collections/${encodeURIComponent(name)}`
    );
    return DeleteCollectionResponseSchema.parse(data);
  } catch (err) {
    throw mapError(err);
  }
}
