// frontend/src/api/telegram.service.ts
// [MODIFIED] Part 2B — Mission 4 (Frontend Safety).
//
// Safety contract:
//   - submitPhone sends owner_id + phone_number. The phone value is never
//     stored in localStorage, sessionStorage, or passed through URL params.
//   - getTelegramStatus sends owner_id as a query param.
//   - disconnectTelegram sends owner_id in the request body.
//   - deleteAccount sends owner_id as a query param to DELETE /account.
//   - No function in this module ever reads back or surfaces the ciphertext form.
//   - Response types are strictly typed to TelegramAccountResponse / PhoneSubmissionResult.

import { apiClient } from "./client";
import type {
  TelegramStatus,
  ChatListResponse,
  TelegramChat,
  AuthResponse,
  MockEventResponse,
  ProcessingStatusResponse,
  UpdateChatRequest,
  PhoneSubmissionResult,
  TelegramAccountResponse,
} from "@/types/telegram";

const BASE = "/integrations/telegram";

// ---------------------------------------------------------------------------
// Auth & connection
// ---------------------------------------------------------------------------

/** Fetch current authorization status. Requires owner_id. */
export async function getTelegramStatus(owner_id: string): Promise<TelegramStatus> {
  const { data } = await apiClient.get<TelegramStatus>(`${BASE}/status`, {
    params: { owner_id },
  });
  return data;
}

export async function connectTelegram(owner_id: string): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>(`${BASE}/connect`, { owner_id });
  return data;
}

/**
 * Submit the phone number for Telegram authorization.
 *
 * Security:
 *   - `phoneNumber` is passed directly to the backend and immediately discarded.
 *   - The backend returns only `phone_number_masked`; the raw value is never
 *     stored, echoed back, or placed in any log.
 *   - The calling UI component is responsible for clearing its local state
 *     as soon as this function resolves.
 */
export async function submitPhone(
  owner_id: string,
  phoneNumber: string,
): Promise<PhoneSubmissionResult> {
  const { data } = await apiClient.post<PhoneSubmissionResult>(`${BASE}/auth/phone`, {
    owner_id,
    phone_number: phoneNumber,
  });
  return data;
}

export async function submitCode(owner_id: string, attempt_id: string, code: string): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>(`${BASE}/auth/code`, { owner_id, attempt_id, code });
  return data;
}

export async function submitPassword(owner_id: string, attempt_id: string, password: string): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>(`${BASE}/auth/password`, { owner_id, attempt_id, password });
  return data;
}

/**
 * Temporary disconnect — the encrypted phone payload is preserved on the backend
 * so the user can reconnect without re-entering their number.
 */
export async function disconnectTelegram(owner_id: string): Promise<AuthResponse> {
  const { data } = await apiClient.post<AuthResponse>(`${BASE}/disconnect`, { owner_id });
  return data;
}

/**
 * Explicit account deletion — backend clears the stored encrypted phone data.
 */
export async function deleteAccount(owner_id: string): Promise<AuthResponse> {
  const { data } = await apiClient.delete<AuthResponse>(`${BASE}/account`, {
    params: { owner_id },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Account list
// ---------------------------------------------------------------------------

export async function listAccounts(owner_id: string): Promise<TelegramAccountResponse[]> {
  const { data } = await apiClient.get<TelegramAccountResponse[]>(`${BASE}/accounts`, {
    params: { owner_id },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Chats
// ---------------------------------------------------------------------------

export async function listChats(): Promise<ChatListResponse> {
  const { data } = await apiClient.get<ChatListResponse>(`${BASE}/chats`);
  return data;
}

export async function getChat(chat_id: string): Promise<TelegramChat> {
  const { data } = await apiClient.get<TelegramChat>(`${BASE}/chats/${chat_id}`);
  return data;
}

export async function updateChat(
  chat_id: string,
  body: UpdateChatRequest
): Promise<TelegramChat> {
  const { data } = await apiClient.patch<TelegramChat>(`${BASE}/chats/${chat_id}`, body);
  return data;
}

export async function deleteChatData(chat_id: string): Promise<{ deleted: boolean; message: string }> {
  const { data } = await apiClient.delete(`${BASE}/chats/${chat_id}/data`);
  return data;
}

// ---------------------------------------------------------------------------
// Mock events & processing status
// ---------------------------------------------------------------------------

export async function ingestMockEvent(
  event: Record<string, unknown>,
  owner_id = "user_123"
): Promise<MockEventResponse> {
  const { data } = await apiClient.post<MockEventResponse>(`${BASE}/mock-events`, {
    event,
    owner_id,
  });
  return data;
}

export async function getProcessingStatus(): Promise<ProcessingStatusResponse> {
  const { data } = await apiClient.get<ProcessingStatusResponse>(`${BASE}/processing-status`);
  return data;
}

export async function pauseProcessing(): Promise<ProcessingStatusResponse> {
  const { data } = await apiClient.post<ProcessingStatusResponse>(`${BASE}/pause`);
  return data;
}

export async function resumeProcessing(): Promise<ProcessingStatusResponse> {
  const { data } = await apiClient.post<ProcessingStatusResponse>(`${BASE}/resume`);
  return data;
}
