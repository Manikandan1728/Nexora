import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, Bot, User, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage as ChatMessageType } from "@/types/chat";
import { Avatar, AvatarFallback } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        "group flex w-full gap-4 px-4 py-6 md:px-6 hover:bg-surface/50 transition-colors",
        isUser ? "" : "bg-surface/30"
      )}
    >
      <Avatar className={cn("h-8 w-8 shrink-0", isUser ? "bg-accent/20" : "bg-primary/20")}>
        <AvatarFallback>
          {isUser ? <User className="h-4 w-4 text-accent" /> : <Bot className="h-4 w-4 text-primary" />}
        </AvatarFallback>
      </Avatar>

      <div className="flex w-full flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-sm text-foreground">
            {isUser ? "You" : "Nexora AI"}
          </span>
          {message.error && (
            <span className="flex items-center gap-1 text-xs text-danger">
              <AlertTriangle className="h-3 w-3" /> Error
            </span>
          )}
        </div>

        <div
          className={cn(
            "prose prose-sm dark:prose-invert max-w-none break-words",
            message.error && "text-danger"
          )}
        >
          {message.content ? (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ node, ...props }) => (
                  <a {...props} className="text-accent hover:underline" target="_blank" rel="noreferrer" />
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          ) : (
            isStreaming && (
              <span className="flex items-center gap-1 text-muted-foreground animate-pulse">
                Thinking<span className="animate-bounce">.</span>
                <span className="animate-bounce delay-75">.</span>
                <span className="animate-bounce delay-150">.</span>
              </span>
            )
          )}
        </div>

        {!isUser && message.content && (
          <div className="mt-2 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
              onClick={handleCopy}
            >
              {copied ? <Check className="h-3 w-3 mr-1" /> : <Copy className="h-3 w-3 mr-1" />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
