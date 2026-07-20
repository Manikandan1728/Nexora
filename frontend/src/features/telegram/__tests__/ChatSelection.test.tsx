import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import TelegramChatSelectionPage from "../TelegramChatSelectionPage";

vi.mock("@/api/telegram.service", () => ({
  listChats: vi.fn().mockResolvedValue({
    chats: [
      {
        chat_id: "123",
        title: "Test Group",
        chat_type: "supergroup",
        indexing_enabled: false,
      }
    ]
  }),
}));

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={qc}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>
  );
}

describe("TelegramChatSelectionPage", () => {
  it("renders the chat selection list", async () => {
    renderWithProviders(<TelegramChatSelectionPage />);
    
    // Check for title
    expect(await screen.findByText("Select Chats")).toBeInTheDocument();
    
    // Check for the mocked chat
    expect(await screen.findByText("Test Group")).toBeInTheDocument();
  });
});
