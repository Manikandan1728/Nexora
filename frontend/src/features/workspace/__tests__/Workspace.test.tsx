import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import WorkspacePage from "../WorkspacePage";
import { useConversationHistory } from "@/hooks/useConversationHistory";
import { useChat } from "@/hooks/useChat";

// Mock the hooks
vi.mock("@/hooks/useConversationHistory");
vi.mock("@/hooks/useChat");

describe("WorkspacePage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    (useConversationHistory as any).mockReturnValue({
      conversations: [{ id: "1", title: "Test Chat", messages: [] }],
      activeId: "1",
      activeConversation: { id: "1", title: "Test Chat", messages: [] },
      setActiveId: vi.fn(),
      createConversation: vi.fn(),
      deleteConversation: vi.fn(),
      renameConversation: vi.fn(),
      updateActiveConversation: vi.fn(),
    });

    (useChat as any).mockReturnValue({
      sendMessage: vi.fn(),
      isGenerating: false,
      stopGeneration: vi.fn(),
      streamingContent: "",
      streamingMessageId: null,
    });
  });

  it("renders the empty state with suggested prompts when there are no messages", () => {
    render(<WorkspacePage />);
    expect(screen.getByText("Suggested Prompts")).toBeInTheDocument();
  });

  it("calls sendMessage when a suggested prompt is clicked", () => {
    const mockSendMessage = vi.fn();
    (useChat as any).mockReturnValue({
      sendMessage: mockSendMessage,
      isGenerating: false,
    });
    render(<WorkspacePage />);
    fireEvent.click(screen.getByText(/What meetings did I miss today\?/i));
    expect(mockSendMessage).toHaveBeenCalledWith("What meetings did I miss today?");
  });

  it("renders messages if conversation is active", () => {
    (useConversationHistory as any).mockReturnValue({
      conversations: [{ id: "1", title: "Test Chat", messages: [] }],
      activeId: "1",
      activeConversation: {
        id: "1",
        title: "Test Chat",
        messages: [{ id: "msg1", role: "user", content: "Hello AI", timestamp: "" }],
      },
      setActiveId: vi.fn(),
      createConversation: vi.fn(),
    });

    render(<WorkspacePage />);
    expect(screen.getByText("Hello AI")).toBeInTheDocument();
  });
});
