export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  engine_status: string;
  llm_provider_available: boolean;
}
