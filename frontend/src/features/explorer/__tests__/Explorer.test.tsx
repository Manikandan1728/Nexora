import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ResultCard } from "@/components/explorer/ResultCard";
import { SearchResultsPanel } from "@/components/explorer/SearchResultsPanel";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import { FilterSidebar } from "@/components/explorer/FilterSidebar";
import { PersonCard } from "@/components/explorer/PersonCard";
import type { TelegramSource, QueryResponse } from "@/types/query";

const mockSource: TelegramSource = {
  document_id: "doc-1",
  source: "telegram",
  conversation_id: "chat-1",
  conversation_title: "Dev Team",
  conversation_type: "group",
  sender_id: "user-1",
  sender_name: "Alice",
  message_id: "msg-1",
  timestamp: "2024-01-15T10:30:00Z",
  content_type: "text",
  filename: "",
  chunk_index: 0,
  snippet: "This is a test message about deployment.",
  score: 0.87,
};

const mockResponse: QueryResponse = {
  question: "deployment",
  sources: [mockSource],
  retrieved_documents: [],
  elapsed_seconds: 0.5,
};

// ── ResultCard ──────────────────────────────────────────────────────────────

describe("ResultCard", () => {
  it("renders sender name, chat title, and snippet", () => {
    render(<ResultCard source={mockSource} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Dev Team")).toBeInTheDocument();
    expect(screen.getByText(/deployment/i)).toBeInTheDocument();
  });

  it("calls onClick when clicked", () => {
    const onClick = vi.fn();
    render(<ResultCard source={mockSource} onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });

  it("highlights matched terms in the snippet", () => {
    render(<ResultCard source={mockSource} matchedTerms={["deployment"]} />);
    const mark = document.querySelector("mark");
    expect(mark).not.toBeNull();
    expect(mark?.textContent).toContain("deployment");
  });

  it("shows relevance score", () => {
    render(<ResultCard source={mockSource} />);
    expect(screen.getByText("87%")).toBeInTheDocument();
  });
});

// ── SearchResultsPanel ──────────────────────────────────────────────────────

describe("SearchResultsPanel", () => {
  it("shows loading state", () => {
    render(<SearchResultsPanel data={null} isLoading={true} error={null} />);
    expect(screen.getByText(/searching/i)).toBeInTheDocument();
  });

  it("shows error message", () => {
    render(<SearchResultsPanel data={null} isLoading={false} error="Search failed" />);
    expect(screen.getByText("Search failed")).toBeInTheDocument();
  });

  it("renders message tab results", () => {
    render(<SearchResultsPanel data={mockResponse} isLoading={false} error={null} />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders empty tab message when switching to Documents with no docs", () => {
    render(<SearchResultsPanel data={mockResponse} isLoading={false} error={null} />);
    fireEvent.click(screen.getByRole("tab", { name: /documents/i }));
    expect(screen.getByText(/no documents results/i)).toBeInTheDocument();
  });

  it("returns null when no data and not loading", () => {
    const { container } = render(<SearchResultsPanel data={null} isLoading={false} error={null} />);
    expect(container.firstChild).toBeNull();
  });
});

// ── EmptyExplorer ───────────────────────────────────────────────────────────

describe("EmptyExplorer", () => {
  it("renders title and description", () => {
    render(<EmptyExplorer title="Nothing here" description="Try searching for something." />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Try searching for something.")).toBeInTheDocument();
  });
});

// ── FilterSidebar ───────────────────────────────────────────────────────────

describe("FilterSidebar", () => {
  it("renders filter options", () => {
    const onChange = vi.fn();
    render(<FilterSidebar filters={{}} onChange={onChange} />);
    expect(screen.getByText("Filters")).toBeInTheDocument();
    expect(screen.getByText("Images")).toBeInTheDocument();
  });

  it("calls onChange when a content type is selected", () => {
    const onChange = vi.fn();
    render(<FilterSidebar filters={{}} onChange={onChange} />);
    fireEvent.click(screen.getByText("Images"));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ content_type: "image" }));
  });
});

// ── PersonCard ──────────────────────────────────────────────────────────────

describe("PersonCard", () => {
  it("renders sender name, message count, and chats", () => {
    render(
      <PersonCard
        senderId="u1"
        senderName="Bob Smith"
        messageCount={42}
        chats={["Dev Team", "General"]}
      />
    );
    expect(screen.getByText("Bob Smith")).toBeInTheDocument();
    expect(screen.getByText(/42 messages/i)).toBeInTheDocument();
    expect(screen.getByText("Dev Team")).toBeInTheDocument();
  });

  it("shows +N more when more than 3 chats", () => {
    render(
      <PersonCard
        senderId="u2"
        senderName="Carol"
        messageCount={10}
        chats={["A", "B", "C", "D", "E"]}
      />
    );
    expect(screen.getByText("+2 more")).toBeInTheDocument();
  });
});
