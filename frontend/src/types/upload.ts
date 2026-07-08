export interface PhaseStatus {
  phase: string;
  status: string;
  detail?: string | null;
}

export interface UploadResponse {
  collection_name: string;
  messages_parsed: number;
  chunks_created: number;
  vectors_indexed: number;
  phase_statuses?: PhaseStatus[];
  elapsed_seconds: number;
}
