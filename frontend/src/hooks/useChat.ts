import { useState, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import { runQuery } from "@/api/query.service";
import type { ChatMessage } from "@/types/chat";
import type { QueryRequest } from "@/types/query";

export function useChat({
  messages,
  updateMessages
}: {
  messages: ChatMessage[];
  updateMessages: (msgs: ChatMessage[], newTitle?: string) => void;
}) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  

  const sendMessage = useCallback(async (content: string, useRag: boolean = true) => {
    if (!content.trim() || isGenerating) return;

    const userMessage: ChatMessage = {
      id: uuidv4(),
      role: "user",
      content: content.trim(),
      timestamp: new Date().toISOString(),
    };

    const newMessages = [...messages, userMessage];
    
    // Auto-title if it's the first message
    const newTitle = messages.length === 0 ? content.slice(0, 30) + "..." : undefined;
    updateMessages(newMessages, newTitle);

    setIsGenerating(true);
    setStreamingContent("");
    
    const assistantMessageId = uuidv4();
    setStreamingMessageId(assistantMessageId);
    
    // Add a placeholder assistant message (will be updated via streamingContent)
    const assistantMessagePlaceholder: ChatMessage = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
    };
    updateMessages([...newMessages, assistantMessagePlaceholder]);

    try {
      // 1. Fire API Request
      const request: QueryRequest = {
        question: content,
        collection_name: "telegram", // Default fallback if needed, but we should probably fetch the available collections or pass it.
        top_k: 10,
        use_rag: useRag,
        filters: {}
      };
      
      const response = await runQuery(request);
      
      // 2. Pseudo-stream the answer
      const answer = response.answer || "*(No generated answer was returned. Only context was retrieved.)*";
      const chunks = answer.split(/(\s+)/); // Split by whitespace preserving the whitespace
      
      let currentContent = "";
      for (const chunk of chunks) {
        currentContent += chunk;
        setStreamingContent(currentContent);
        // Small delay to simulate streaming
        await new Promise(r => setTimeout(r, 10));
      }

      // 3. Finalize message
      const finalizedAssistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: "assistant",
        content: currentContent,
        timestamp: new Date().toISOString(),
        response_data: response,
      };

      updateMessages([...newMessages, finalizedAssistantMessage]);

    } catch (error) {
      console.error("Chat generation error:", error);
      const errorAssistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: "assistant",
        content: "I'm sorry, I encountered an error while trying to process your request.",
        timestamp: new Date().toISOString(),
        error: true,
      };
      updateMessages([...newMessages, errorAssistantMessage]);
    } finally {
      setIsGenerating(false);
      setStreamingMessageId(null);
      setStreamingContent("");
    }

  }, [messages, isGenerating, updateMessages]);

  const stopGeneration = useCallback(() => {
    // We would abort the fetch request here if our api client supported passing the signal.
    // For now we just reset the generating state.
    setIsGenerating(false);
    setStreamingMessageId(null);
    setStreamingContent("");
  }, []);

  return {
    sendMessage,
    isGenerating,
    stopGeneration,
    streamingContent,
    streamingMessageId
  };
}
