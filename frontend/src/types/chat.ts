import type { QueryResponse } from "./query";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  error?: boolean;
  // If the message is an assistant response, it might have citations and documents linked
  response_data?: QueryResponse;
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
  created_at: string;
  messages: ChatMessage[];
}
