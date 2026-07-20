import { useState, useEffect, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import type { Conversation, ChatMessage } from "@/types/chat";

const STORAGE_KEY = "nexora_conversations";

export function useConversationHistory() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setConversations(JSON.parse(stored) as Conversation[]);
      }
    } catch (e) {
      console.error("Failed to load conversation history from local storage.", e);
    }
  }, []);

  const saveToStorage = useCallback((data: Conversation[]) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      setConversations(data);
    } catch (e) {
      console.error("Failed to save conversation history to local storage.", e);
    }
  }, []);

  const createConversation = useCallback(() => {
    const newConv: Conversation = {
      id: uuidv4(),
      title: "New Conversation",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      messages: [],
    };
    saveToStorage([newConv, ...conversations]);
    setActiveId(newConv.id);
    return newConv.id;
  }, [conversations, saveToStorage]);

  const deleteConversation = useCallback((id: string) => {
    const filtered = conversations.filter(c => c.id !== id);
    saveToStorage(filtered);
    if (activeId === id) {
      setActiveId(filtered.length > 0 ? filtered[0]?.id ?? null : null);
    }
  }, [conversations, activeId, saveToStorage]);

  const renameConversation = useCallback((id: string, newTitle: string) => {
    const updated = conversations.map(c => 
      c.id === id ? { ...c, title: newTitle, updated_at: new Date().toISOString() } : c
    );
    saveToStorage(updated);
  }, [conversations, saveToStorage]);

  const updateActiveConversation = useCallback((messages: ChatMessage[], newTitle?: string) => {
    if (!activeId) return;
    const updated = conversations.map(c => {
      if (c.id === activeId) {
        return {
          ...c,
          messages,
          title: newTitle && c.title === "New Conversation" ? newTitle : c.title,
          updated_at: new Date().toISOString(),
        };
      }
      return c;
    });
    // Move updated to top
    const activeConv = activeId ? updated.find(c => c.id === activeId) : undefined;
    const others = updated.filter(c => c.id !== activeId);
    if (activeConv) {
      saveToStorage([activeConv, ...others]);
    }
  }, [activeId, conversations, saveToStorage]);

  const activeConversation = conversations.find(c => c.id === activeId) || null;

  return {
    conversations,
    activeId,
    activeConversation,
    setActiveId,
    createConversation,
    deleteConversation,
    renameConversation,
    updateActiveConversation,
  };
}
