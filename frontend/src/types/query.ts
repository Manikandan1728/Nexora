export interface QueryRequest {
  question: string;
  collection_name: string;
  top_k?: number;
  filters?: Record<string, unknown> | null;
  use_rag?: boolean;
}

export interface RetrievedDocument {
  document_id: string;
  text: string;
  similarity_score: number;
  rank: number;
  metadata?: Record<string, unknown>;
  focused_snippet?: string | null;
  matched_messages?: Array<{ text: string; index: number }> | null;
  matched_terms?: string[] | null;
  relevance_reason?: string | null;
  is_low_confidence?: boolean;
  no_strong_passage?: boolean | null;
}

export interface Citation {
  document_id: string;
  rank: number;
  similarity_score: number;
  source_chat: string;
  chunk_index: number;
  start_timestamp: string;
  end_timestamp: string;
}

export interface QueryResponse {
  question: string;
  answer?: string | null;
  citations?: Citation[];
  retrieved_documents?: RetrievedDocument[];
  /** Telegram-native source citations (Req 12). Empty for non-Telegram. */
  sources?: TelegramSource[];
  confidence?: number | null;
  llm_used?: boolean;
  message?: string | null;
  no_strong_match?: boolean;
  elapsed_seconds: number;
}

/** Telegram source citation — never contains owner_id or internal paths (Req 13). */
export interface TelegramSource {
  document_id: string;
  source: string;
  conversation_id: string;
  conversation_title: string;
  conversation_type: string;
  /** Stable sender identifier — used for filtering, never display-only name. */
  sender_id: string;
  /** Display name only — never send as filter value. */
  sender_name: string;
  message_id: string;
  timestamp: string;
  content_type: string;
  filename: string;
  chunk_index: number;
  snippet: string;
  score: number;
}
