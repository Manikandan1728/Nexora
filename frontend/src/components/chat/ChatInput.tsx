import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  isGenerating: boolean;
  onStopGeneration?: () => void;
}

export function ChatInput({ onSendMessage, isGenerating, onStopGeneration }: ChatInputProps) {
  const [content, setContent] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  };

  useEffect(() => {
    handleInput();
  }, [content]);

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (isGenerating) {
      onStopGeneration?.();
      return;
    }
    if (content.trim()) {
      onSendMessage(content);
      setContent("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="relative flex w-full flex-col gap-2 rounded-2xl bg-surface border border-border p-3 shadow-card focus-within:border-accent/40 focus-within:ring-1 focus-within:ring-accent/40 transition-all"
    >
      <textarea
        ref={textareaRef}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask a question about your knowledge..."
        className="w-full max-h-[200px] min-h-[44px] resize-none bg-transparent px-2 py-1.5 text-sm text-foreground outline-none placeholder:text-muted-foreground"
        rows={1}
        disabled={isGenerating}
      />
      <div className="flex items-center justify-between px-2 pt-2 border-t border-border/50">
        <span className="text-[10px] text-muted-foreground flex items-center gap-1">
          <kbd className="rounded border border-border bg-surface px-1 py-0.5">Shift</kbd> +{" "}
          <kbd className="rounded border border-border bg-surface px-1 py-0.5">Enter</kbd> to add a new line
        </span>
        <Button
          type="submit"
          disabled={(!content.trim() && !isGenerating)}
          className={cn(
            "h-8 w-8 rounded-full p-0 transition-colors",
            isGenerating ? "bg-danger hover:bg-danger/80" : "bg-accent hover:bg-accent/80"
          )}
        >
          {isGenerating ? (
            <span className="h-3 w-3 rounded-sm bg-white" />
          ) : (
            <Send className="h-4 w-4 text-white" />
          )}
          <span className="sr-only">{isGenerating ? "Stop generation" : "Send message"}</span>
        </Button>
      </div>
    </form>
  );
}
