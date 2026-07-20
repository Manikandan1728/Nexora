// frontend/src/types/telegram.ts
// [ADDITIVE] — New file. Telegram integration TypeScript types.

export type AuthorizationStatus =
  | "disconnected"
  | "waiting_phone"
  | "waiting_code"
  | "waiting_password"
  | "ready"
  | "closed"
  | "error";

export type ChatType = "private" | "group" | "supergroup" | "channel" | "bot" | "unknown";

/**
 * Safe public account view returned by the backend.
 * Never contains phone_number or phone_number_encrypted —
 * only the masked form is present.
 */
export interface TelegramAccountResponse {
  telegram_account_id: string;
  display_name: string | null;
  username: string | null;
  authorization_status: AuthorizationStatus;
  session_status: string;
  /** Masked phone, e.g. "+91 ******3210". May be null if data is missing or corrupted. */
  phone_number_masked: string | null;
}

export interface TelegramStatus {
  authorization_status: AuthorizationStatus;
  client_type: string;
  is_paused: boolean;
  /** Account info (including masked phone) from Mission 3 backend. */
  account: TelegramAccountResponse | null;
}

export interface TelegramChat {
  chat_id: string;
  title: string;
  chat_type: ChatType;
  last_activity?: string | null;
  indexing_enabled: boolean;
  indexing_enabled_at?: string | null;
  processing_status: string;
}

export interface ChatListResponse {
  chats: TelegramChat[];
  total: number;
}

export interface MockEventResponse {
  processed: number;
  ignored: number;
  errors: number;
  details: string[];
}

export interface ProcessingStatusResponse {
  is_paused: boolean;
  messages_in_queue: number;
  client_type: string;
}

export interface ConnectRequest {
  owner_id: string;
}

/**
 * Response from POST /auth/phone (Mission 3).
 * Replaces the old AuthResponse for phone submission —
 * status and masked phone only, no plaintext.
 */
export interface PhoneSubmissionResult {
  status: AuthorizationStatus;
  phone_number_masked: string;
  telegram_account_id: string;
  authentication_attempt_id?: string | null;
}

export interface AuthResponse {
  authorization_status: AuthorizationStatus;
  message: string;
  authentication_attempt_id?: string | null;
}

export interface UpdateChatRequest {
  indexing_enabled?: boolean;
  indexing_enabled_at?: string | null;
}
