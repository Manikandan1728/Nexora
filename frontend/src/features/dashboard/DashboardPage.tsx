import { Brain, Database, FileText, Zap, Activity, Server } from "lucide-react";
import { Link } from "react-router-dom";
import { useHealth } from "@/hooks/useHealth";
import { useCollections } from "@/hooks/useCollections";
import { MetricCard } from "@/components/common/MetricCard";
import { PageHeader } from "@/components/common/PageHeader";
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton";
import { ErrorState } from "@/components/common/ErrorState";
import { cn } from "@/lib/utils";
import type { ApiError } from "@/types/api";

function QuickActionCard({
  to,
  icon,
  label,
  description,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  description: string;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "group flex items-start gap-4 rounded-xl bg-surface border border-border p-4",
        "shadow-card hover:shadow-card-lg hover:border-accent/40",
        "transition-all duration-200 animate-fade-in"
      )}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent group-hover:bg-accent/20 transition-colors">
        {icon}
      </div>
      <div>
        <p className="text-sm font-semibold text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const health = useHealth();
  const collections = useCollections();

  if (health.isLoading || collections.isLoading) {
    return <LoadingSkeleton variant="page" />;
  }

  if (health.isError) {
    return (
      <ErrorState
        error={health.error as ApiError}
        title="Backend unavailable"
        message="Cannot reach the Nexora API. Make sure the backend is running."
        onRetry={() => void health.refetch()}
      />
    );
  }

  const totalCollections = collections.data?.total ?? 0;
  const collectionList = collections.data?.collections ?? [];
  const totalDocs = collectionList.reduce(
    (acc, c) => acc + c.document_count,
    0
  );
  const llmAvailable = health.data?.llm_provider_available ?? false;
  const engineStatus = health.data?.engine_status ?? "unknown";

  return (
    <div className="space-y-8 animate-fade-in">
      <PageHeader
        title="Dashboard"
        description="Welcome to Nexora — your Telegram AI Knowledge Retrieval Platform."
      />

      {/* Metrics */}
      <section aria-label="System metrics">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            label="Collections"
            value={totalCollections}
            icon={<Database className="h-4 w-4" />}
            description="Knowledge bases"
          />
          <MetricCard
            label="Documents"
            value={totalDocs.toLocaleString()}
            icon={<FileText className="h-4 w-4" />}
            description="Indexed chunks"
          />
          <MetricCard
            label="LLM"
            value={llmAvailable ? "Active" : "Unavailable"}
            icon={<Zap className="h-4 w-4" />}
            description={llmAvailable ? "AI answers enabled" : "Retrieval only"}
          />
          <MetricCard
            label="Engine"
            value={engineStatus}
            icon={<Activity className="h-4 w-4" />}
            description={health.data?.version ?? ""}
          />
        </div>
      </section>

      {/* Backend status card */}
      <section
        aria-label="Backend health"
        className="rounded-xl bg-surface border border-border p-5 shadow-card"
      >
        <div className="flex items-center gap-2 mb-4">
          <Server className="h-4 w-4 text-accent" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-foreground">Backend Status</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <p className="text-xs text-muted-foreground mb-1">App</p>
            <p className="text-sm font-medium text-foreground">
              {health.data?.app_name ?? "—"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Version</p>
            <p className="text-sm font-medium text-foreground">
              {health.data?.version ?? "—"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">Status</p>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 text-sm font-medium",
                health.data?.status === "ok" ? "text-success" : "text-danger"
              )}
            >
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  health.data?.status === "ok" ? "bg-success" : "bg-danger"
                )}
              />
              {health.data?.status === "ok" ? "Operational" : "Degraded"}
            </span>
          </div>
        </div>
      </section>

      {/* Quick actions */}
      <section aria-label="Quick actions">
        <h2 className="text-sm font-semibold text-foreground mb-3">
          Quick Actions
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <QuickActionCard
            to="/telegram"
            icon={<Brain className="h-5 w-5" />}
            label="Connect Telegram"
            description="Authenticate and start indexing your Telegram conversations"
          />
          <QuickActionCard
            to="/search"
            icon={<Zap className="h-5 w-5" />}
            label="Search & Ask"
            description="Query your knowledge base with AI-powered answers"
          />
          <QuickActionCard
            to="/collections"
            icon={<Database className="h-5 w-5" />}
            label="Manage Collections"
            description={`${totalCollections} collection${totalCollections !== 1 ? "s" : ""} ready to explore`}
          />
        </div>
      </section>

      {/* Recent collections table */}
      {collectionList.length > 0 && (
        <section
          aria-label="Recent collections"
          className="rounded-xl bg-surface border border-border shadow-card overflow-hidden"
        >
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">
              Recent Collections
            </h2>
            <Link
              to="/collections"
              className="text-xs text-accent hover:text-accent/80 transition-colors"
            >
              View all →
            </Link>
          </div>
          <div className="divide-y divide-border">
            {collectionList.slice(0, 5).map((col) => (
              <div
                key={col.name}
                className="flex items-center justify-between px-5 py-3 hover:bg-surface-hover transition-colors"
              >
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {col.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {col.document_count.toLocaleString()} chunks · {col.embedding_model}
                  </p>
                </div>
                <Link
                  to="/search"
                  state={{ collection: col.name }}
                  className="text-xs text-accent hover:underline"
                >
                  Search
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
