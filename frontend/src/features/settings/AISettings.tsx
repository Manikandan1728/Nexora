import { Brain, Database, Cpu, HelpCircle } from "lucide-react";
import { useHealth } from "@/hooks/useHealth";
import { useCollections } from "@/hooks/useCollections";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

function Tooltip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex items-center">
      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground ml-1 cursor-help" aria-hidden="true" />
      <span
        role="tooltip"
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 rounded-lg border border-border bg-surface px-3 py-2 text-xs text-muted-foreground shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10"
      >
        {text}
      </span>
    </span>
  );
}

export default function AISettings() {
  const health = useHealth();
  const collections = useCollections();
  const info = health.data;

  const collectionList = collections.data?.collections ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">AI & Models</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Read-only view of active AI configuration.</p>
      </div>

      <SettingsSection icon={<Brain className="h-4 w-4" />} title="Language Model">
        <SettingsRow label={
          <span className="flex items-center">LLM Provider<Tooltip text="The large language model used to generate answers from retrieved context." /></span>
        }>
          <Badge
            variant="outline"
            className={cn(
              info?.llm_provider_available ? "border-success/40 text-success" : "border-muted text-muted-foreground"
            )}
          >
            {info?.llm_provider_available ? "Available" : "Unavailable"}
          </Badge>
        </SettingsRow>

        <SettingsRow label={
          <span className="flex items-center">Engine Status<Tooltip text="The overall status of the RAG engine backend." /></span>
        }>
          <span className={cn(
            "text-sm font-medium",
            info?.engine_status === "ready" ? "text-success" : "text-warning"
          )}>
            {info?.engine_status ?? "—"}
          </span>
        </SettingsRow>

        <SettingsRow label="Backend Version">
          <span className="text-sm font-mono text-foreground">{info?.version ?? "—"}</span>
        </SettingsRow>

        <SettingsRow label="Application">
          <span className="text-sm text-foreground">{info?.app_name ?? "—"}</span>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection icon={<Database className="h-4 w-4" />} title="Vector Database">
        <SettingsRow label={
          <span className="flex items-center">Database<Tooltip text="ChromaDB stores the vector embeddings used for semantic retrieval." /></span>
        }>
          <span className="text-sm text-foreground font-medium">ChromaDB</span>
        </SettingsRow>

        <SettingsRow label={
          <span className="flex items-center">Collections<Tooltip text="Each collection contains a set of embeddings from one or more indexed Telegram chats." /></span>
        }>
          <span className="text-sm font-medium text-foreground">{collectionList.length}</span>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection icon={<Cpu className="h-4 w-4" />} title="Collections">
        {collectionList.length === 0 ? (
          <div className="px-5 py-4 text-sm text-muted-foreground">No collections indexed yet.</div>
        ) : (
          <div className="divide-y divide-border/50">
            {collectionList.map((col) => (
              <SettingsRow key={col.name} label={col.name}>
                <span className="text-xs text-muted-foreground font-mono">
                  {(col as { count?: number }).count ?? "—"} docs
                </span>
              </SettingsRow>
            ))}
          </div>
        )}
      </SettingsSection>
    </div>
  );
}
