import { z } from "zod";

export const CollectionInfoSchema = z.object({
  name: z.string(),
  document_count: z.number().int(),
  embedding_model: z.string(),
  schema_version: z.string(),
});

export const CollectionListResponseSchema = z.object({
  collections: z.array(CollectionInfoSchema).optional(),
  total: z.number().int(),
});

export const DeleteCollectionResponseSchema = z.object({
  collection_name: z.string(),
  deleted: z.boolean(),
  message: z.string(),
});
