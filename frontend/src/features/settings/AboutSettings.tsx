import { Info, Code2, Globe, Package } from "lucide-react";
import { useHealth } from "@/hooks/useHealth";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { Badge } from "@/components/ui/Badge";

const FRONTEND_VERSION = "8.0.0";
const STACK = [
  { name: "React 18", role: "UI Framework" },
  { name: "TypeScript", role: "Type Safety" },
  { name: "TanStack Query", role: "Data Fetching" },
  { name: "React Router v6", role: "Routing" },
  { name: "Tailwind CSS", role: "Styling" },
  { name: "Vite", role: "Build Tool" },
  { name: "Vitest", role: "Testing" },
];

export default function AboutSettings() {
  const health = useHealth();
  const info = health.data;
  const isDev = import.meta.env.DEV;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">About Nexora</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Version and technology information.</p>
      </div>

      <SettingsSection icon={<Info className="h-4 w-4" />} title="Application">
        <SettingsRow label="Frontend Version">
          <span className="text-sm font-mono text-foreground">v{FRONTEND_VERSION}</span>
        </SettingsRow>
        <SettingsRow label="Backend Version">
          <span className="text-sm font-mono text-foreground">{info?.version ?? "—"}</span>
        </SettingsRow>
        <SettingsRow label="Environment">
          <Badge variant={isDev ? "secondary" : "default"}>
            {isDev ? "Development" : "Production"}
          </Badge>
        </SettingsRow>
        <SettingsRow label="Backend Status">
          <Badge
            variant="outline"
            className={health.isError ? "border-danger/40 text-danger" : "border-success/40 text-success"}
          >
            {health.isLoading ? "Checking…" : health.isError ? "Offline" : "Online"}
          </Badge>
        </SettingsRow>
      </SettingsSection>

      <SettingsSection icon={<Globe className="h-4 w-4" />} title="Product">
        <div className="px-5 py-4">
          <p className="text-sm text-muted-foreground leading-relaxed">
            <strong className="text-foreground">Nexora</strong> is a Telegram-only AI Knowledge Retrieval Platform
            powered by Retrieval-Augmented Generation (RAG). Connect your Telegram account, select chats to index,
            and query your conversations with AI-powered semantic search.
          </p>
        </div>
      </SettingsSection>

      <SettingsSection icon={<Code2 className="h-4 w-4" />} title="Technology Stack">
        <div className="divide-y divide-border/50">
          {STACK.map(({ name, role }) => (
            <SettingsRow key={name} label={name}>
              <span className="text-xs text-muted-foreground">{role}</span>
            </SettingsRow>
          ))}
        </div>
      </SettingsSection>

      <SettingsSection icon={<Package className="h-4 w-4" />} title="Open Source">
        <div className="px-5 py-4">
          <p className="text-sm text-muted-foreground">
            Nexora uses open-source libraries. Dependency license information is available via{" "}
            <code className="bg-surface-hover px-1 py-0.5 rounded text-xs font-mono">npm list --json</code>.
          </p>
        </div>
      </SettingsSection>
    </div>
  );
}
