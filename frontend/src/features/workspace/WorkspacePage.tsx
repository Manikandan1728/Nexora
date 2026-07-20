import { useState, useRef, useEffect } from "react";
import { useConversationHistory } from "@/hooks/useConversationHistory";
import { useChat } from "@/hooks/useChat";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatInput } from "@/components/chat/ChatInput";
import { SuggestedPrompts } from "@/components/chat/SuggestedPrompts";
import { CitationPanel } from "@/components/chat/CitationPanel";
import { PanelRightClose, PanelRightOpen, MessageSquare, Trash2, Plus, Edit2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

export default function WorkspacePage() {
  const {
    conversations,
    activeId,
    activeConversation,
    setActiveId,
    createConversation,
    deleteConversation,
    renameConversation,
    updateActiveConversation,
  } = useConversationHistory();

  // Make sure there is always an active conversation if none exists
  useEffect(() => {
    if (conversations.length === 0) {
      createConversation();
    } else if (!activeId && conversations[0]) {
      setActiveId(conversations[0].id);
    }
  }, [conversations, activeId, createConversation, setActiveId]);

  const {
    sendMessage,
    isGenerating,
    stopGeneration,
    streamingContent,
    streamingMessageId
  } = useChat({
    messages: activeConversation?.messages || [],
    updateMessages: updateActiveConversation,
  });

  const [isCitationOpen, setIsCitationOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change or streaming
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeConversation?.messages, streamingContent]);

  // Find the latest response data for the citation panel
  const latestResponseData = [...(activeConversation?.messages || [])]
    .reverse()
    .find((m) => m.response_data)?.response_data;

  // Automatically open citation panel if a response has citations
  useEffect(() => {
    if (latestResponseData?.sources?.length || latestResponseData?.retrieved_documents?.length) {
      setIsCitationOpen(true);
    }
  }, [latestResponseData]);

  const handleSuggestedPrompt = (prompt: string) => {
    sendMessage(prompt);
  };

  const handleRename = (id: string, oldTitle: string) => {
    const newTitle = prompt("Rename conversation:", oldTitle);
    if (newTitle && newTitle.trim()) {
      renameConversation(id, newTitle.trim());
    }
  };

  return (
    <div className="flex h-[calc(100vh-64px)] w-full overflow-hidden bg-background">
      {/* Sidebar for History (Desktop) */}
      <aside className="hidden w-64 flex-col border-r border-border bg-surface/30 md:flex">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold text-sm">History</h2>
          <Button variant="ghost" size="icon" onClick={() => createConversation()} className="h-8 w-8">
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={cn(
                "group flex w-full items-center justify-between rounded-lg px-2 py-2 text-sm transition-colors cursor-pointer",
                activeId === conv.id ? "bg-accent/10 text-accent font-medium" : "text-muted-foreground hover:bg-surface/80 hover:text-foreground"
              )}
              onClick={() => setActiveId(conv.id)}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <MessageSquare className="h-4 w-4 shrink-0" />
                <span className="truncate">{conv.title}</span>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={(e) => { e.stopPropagation(); handleRename(conv.id, conv.title); }} className="p-1 hover:text-accent">
                  <Edit2 className="h-3 w-3" />
                </button>
                <button onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); }} className="p-1 hover:text-danger">
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex flex-1 flex-col relative min-w-0">
        <header className="flex h-12 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm truncate md:hidden">
              {activeConversation?.title || "AI Workspace"}
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsCitationOpen(!isCitationOpen)}
            className="text-muted-foreground hover:text-foreground"
            title="Toggle Context Panel"
          >
            {isCitationOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
          </Button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto custom-scrollbar">
          {!activeConversation?.messages.length ? (
            <div className="flex h-full items-center justify-center p-4">
              <SuggestedPrompts onSelect={handleSuggestedPrompt} />
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-3xl flex-col pb-6">
              {activeConversation.messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  message={
                    msg.id === streamingMessageId
                      ? { ...msg, content: streamingContent }
                      : msg
                  }
                  isStreaming={msg.id === streamingMessageId}
                />
              ))}
            </div>
          )}
        </div>

        <div className="bg-background px-4 py-4 md:px-6 shadow-[0_-10px_40px_rgba(0,0,0,0.3)]">
          <div className="mx-auto max-w-3xl">
            <ChatInput
              onSendMessage={sendMessage}
              isGenerating={isGenerating}
              onStopGeneration={stopGeneration}
            />
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Nexora AI can make mistakes. Consider verifying important information.
            </p>
          </div>
        </div>
      </main>

      {/* Citations Panel */}
      <aside
        className={cn(
          "absolute inset-y-0 right-0 z-20 w-80 transform transition-transform duration-300 ease-in-out md:relative md:transform-none",
          isCitationOpen ? "translate-x-0" : "translate-x-full md:hidden"
        )}
      >
        <CitationPanel
          responseData={latestResponseData}
          isOpen={isCitationOpen}
          onClose={() => setIsCitationOpen(false)}
        />
      </aside>

      {/* Mobile overlay */}
      {isCitationOpen && (
        <div
          className="fixed inset-0 z-10 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={() => setIsCitationOpen(false)}
        />
      )}
    </div>
  );
}
