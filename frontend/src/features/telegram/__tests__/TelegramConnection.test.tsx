import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import TelegramConnectionPage from "../TelegramConnectionPage";

// Mock the API service
vi.mock("@/api/telegram.service", () => ({
  getTelegramStatus: vi.fn().mockResolvedValue({
    authorization_status: "disconnected",
    account: null,
  }),
  connectTelegram: vi.fn(),
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

describe("TelegramConnectionPage", () => {
  it("renders the connection page in disconnected state", async () => {
    renderWithProviders(<TelegramConnectionPage />);
    
    // Check for title
    expect(await screen.findByText("Connect Telegram")).toBeInTheDocument();
    
    // Check for status badge showing 'Disconnected'
    expect(screen.getByText("Disconnected")).toBeInTheDocument();
    
    // Connect button should be visible
    expect(screen.getByRole("button", { name: /initialize connection/i })).toBeInTheDocument();
  });
});
