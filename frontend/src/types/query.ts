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
  confidence?: number | null;
  llm_used?: boolean;
  message?: string | null;
  elapsed_seconds: number;
}
