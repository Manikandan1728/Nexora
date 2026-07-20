import { MessageSquarePlus } from "lucide-react";

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void;
}

const PROMPTS = [
  "What meetings did I miss today?",
  "Summarize yesterday's discussions.",
  "Find my deployment decisions.",
  "Are there any tasks assigned to me?",
];

export function SuggestedPrompts({ onSelect }: SuggestedPromptsProps) {
  return (
    <div className="flex w-full max-w-2xl flex-col gap-4 animate-fade-in">
      <div className="flex items-center gap-2 text-muted-foreground">
        <MessageSquarePlus className="h-4 w-4" />
        <h3 className="text-sm font-medium">Suggested Prompts</h3>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onSelect(prompt)}
            className="flex text-left items-center rounded-xl bg-surface border border-border p-3 text-sm text-foreground shadow-sm hover:border-accent/40 hover:bg-accent/5 hover:shadow-card transition-all"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
