import { z } from "zod";

export const CitationSchema = z.object({
  document_id: z.string(),
  rank: z.number().int(),
  similarity_score: z.number(),
  source_chat: z.string(),
  chunk_index: z.number().int(),
  start_timestamp: z.string(),
  end_timestamp: z.string(),
});

export const RetrievedDocumentSchema = z.object({
  document_id: z.string(),
  text: z.string(),
  similarity_score: z.number(),
  rank: z.number().int(),
  metadata: z.record(z.unknown()).optional(),
  focused_snippet: z.string().nullish(),
  matched_messages: z
    .array(z.object({ text: z.string(), index: z.number().int() }))
    .nullish(),
  matched_terms: z.array(z.string()).nullish(),
  relevance_reason: z.string().nullish(),
  is_low_confidence: z.boolean().optional(),
  no_strong_passage: z.boolean().nullish(),
});

export const TelegramSourceSchema = z.object({
  document_id: z.string(),
  source: z.string(),
  conversation_id: z.string(),
  conversation_title: z.string(),
  conversation_type: z.string(),
  sender_id: z.string(),
  sender_name: z.string(),
  message_id: z.string(),
  timestamp: z.string(),
  content_type: z.string(),
  filename: z.string(),
  chunk_index: z.number().int(),
  snippet: z.string(),
  score: z.number(),
});

export const QueryResponseSchema = z.object({
  question: z.string(),
  answer: z.string().nullish(),
  citations: z.array(CitationSchema).optional(),
  retrieved_documents: z.array(RetrievedDocumentSchema).optional(),
  sources: z.array(TelegramSourceSchema).optional(),
  confidence: z.number().nullish(),
  llm_used: z.boolean().optional(),
  message: z.string().nullish(),
  no_strong_match: z.boolean().optional(),
  elapsed_seconds: z.number(),
});

/** Form validation schema — tighter rules for the search form */
export const QueryFormSchema = z.object({
  question: z
    .string()
    .min(1, "Question is required")
    .max(2000, "Question must be 2000 characters or fewer"),
  collection_name: z.string().min(1, "Select a collection"),
  top_k: z.number().int().min(1).max(50),
  use_rag: z.boolean(),
});

export type QueryFormValues = z.infer<typeof QueryFormSchema>;
