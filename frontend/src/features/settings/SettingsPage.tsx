import { PageHeader } from "@/components/common/PageHeader";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { useHealth } from "@/hooks/useHealth";
import { Brain, Palette, Server, Info } from "lucide-react";
import { cn } from "@/lib/utils";

function SettingsSection({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl bg-surface border border-border shadow-card overflow-hidden">
      <div className="flex items-center gap-3 px-5 py-4 border-b border-border">
        <span className="text-accent">{icon}</span>
        <div>
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {description && (
            <p className="text-xs text-muted-foreground">{description}</p>
          )}
        </div>
      </div>
      <div className="px-5 py-5">{children}</div>
    </section>
  );
}

export default function SettingsPage() {
  const health = useHealth();
  const info = health.data;

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <PageHeader
        title="Settings"
        description="Appearance and system preferences."
      />

      {/* Appearance */}
      <SettingsSection
        icon={<Palette className="h-4 w-4" />}
        title="Appearance"
        description="Customize how Nexora looks on your device."
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Theme</p>
            <p className="text-xs text-muted-foreground">
              Choose between light, dark, or system theme.
            </p>
          </div>
          <ThemeToggle compact={false} />
        </div>
      </SettingsSection>

      {/* Backend */}
      <SettingsSection
        icon={<Server className="h-4 w-4" />}
        title="Backend"
        description="Connection and API information."
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between py-2 border-b border-border">
            <span className="text-sm text-muted-foreground">Status</span>
            <span
              className={cn(
                "text-sm font-medium",
                health.isError ? "text-danger" : "text-success"
              )}
            >
              {health.isLoading
                ? "Checking…"
                : health.isError
                ? "Offline"
                : "Online"}
            </span>
          </div>
          {info && (
            <>
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-sm text-muted-foreground">App Name</span>
                <span className="text-sm font-medium text-foreground">
                  {info.app_name}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-sm text-muted-foreground">Version</span>
                <span className="text-sm font-mono text-foreground">
                  {info.version}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-sm text-muted-foreground">Engine</span>
                <span
                  className={cn(
                    "text-sm font-medium",
                    info.engine_status === "ready" ? "text-success" : "text-warning"
                  )}
                >
                  {info.engine_status}
                </span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-muted-foreground">LLM Provider</span>
                <span
                  className={cn(
                    "text-sm font-medium",
                    info.llm_provider_available ? "text-success" : "text-muted-foreground"
                  )}
                >
                  {info.llm_provider_available ? "Available" : "Unavailable"}
                </span>
              </div>
            </>
          )}
        </div>
      </SettingsSection>

      {/* About */}
      <SettingsSection
        icon={<Brain className="h-4 w-4" />}
        title="About Nexora"
      >
        <div className="space-y-3">
          <div className="flex items-start gap-3 rounded-lg border border-border bg-surface-hover p-4">
            <Info className="h-4 w-4 text-accent shrink-0 mt-0.5" aria-hidden="true" />
            <div className="space-y-1 text-sm text-muted-foreground">
              <p>
                <strong className="text-foreground">Nexora</strong> is an AI Personal
                Knowledge Engine that indexes your WhatsApp conversations and lets you
                search them with AI-powered answers.
              </p>
              <p>
                Built with React, TanStack Query, FastAPI, and ChromaDB.
              </p>
            </div>
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Frontend</span>
            <span className="font-mono">v1.0.0</span>
          </div>
        </div>
      </SettingsSection>
    </div>
  );
}
