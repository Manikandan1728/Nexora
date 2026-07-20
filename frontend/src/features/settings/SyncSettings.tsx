import { useQuery, useMutation } from "@tanstack/react-query";
import { RefreshCw, Pause, Play, Loader2, CheckCircle2 } from "lucide-react";
import { getProcessingStatus, pauseProcessing, resumeProcessing, listChats } from "@/api/telegram.service";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export default function SyncSettings() {
  const statusQuery = useQuery({
    queryKey: ["processing-status"],
    queryFn: getProcessingStatus,
    refetchInterval: 10_000,
  });

  const chats = useQuery({
    queryKey: ["telegram-chats"],
    queryFn: listChats,
  });

  const pause = useMutation({
    mutationFn: pauseProcessing,
    onSuccess: () => {
      toast.success("Synchronization paused.");
      void statusQuery.refetch();
    },
    onError: () => toast.error("Failed to pause synchronization."),
  });

  const resume = useMutation({
    mutationFn: resumeProcessing,
    onSuccess: () => {
      toast.success("Synchronization resumed.");
      void statusQuery.refetch();
    },
    onError: () => toast.error("Failed to resume synchronization."),
  });

  const s = statusQuery.data;
  const isPaused = s?.is_paused ?? false;
  const indexedChats = chats.data?.chats.filter(c => c.indexing_enabled) ?? [];
  const totalChats = chats.data?.total ?? 0;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Synchronization</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Monitor and control the Telegram indexing pipeline.</p>
      </div>

      <SettingsSection icon={<RefreshCw className="h-4 w-4" />} title="Status">
        {statusQuery.isLoading ? (
          <div className="flex items-center gap-2 px-5 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading status…
          </div>
        ) : (
          <>
            <SettingsRow label="Sync Status">
              <Badge
                variant="outline"
                className={cn(
                  isPaused ? "border-warning/40 text-warning" : "border-success/40 text-success"
                )}
              >
                {isPaused
                  ? <><Pause className="h-3 w-3 mr-1 inline" />Paused</>
                  : <><CheckCircle2 className="h-3 w-3 mr-1 inline" />Running</>
                }
              </Badge>
            </SettingsRow>

            <SettingsRow label="Messages in Queue">
              <span className="text-sm font-medium text-foreground font-mono">
                {s?.messages_in_queue ?? 0}
              </span>
            </SettingsRow>

            <SettingsRow label="Client Type">
              <span className="text-sm text-muted-foreground">{s?.client_type ?? "—"}</span>
            </SettingsRow>

            <SettingsRow label="Total Chats">
              <span className="text-sm font-medium text-foreground">{totalChats}</span>
            </SettingsRow>

            <SettingsRow label="Indexed Chats">
              <span className="text-sm font-medium text-foreground">{indexedChats.length}</span>
            </SettingsRow>
          </>
        )}
      </SettingsSection>

      <SettingsSection icon={<RefreshCw className="h-4 w-4" />} title="Controls">
        <SettingsRow
          label={isPaused ? "Resume Synchronization" : "Pause Synchronization"}
          description={
            isPaused
              ? "Restart the indexing pipeline to process new messages."
              : "Temporarily halt message processing without losing data."
          }
        >
          {isPaused ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => resume.mutate()}
              disabled={resume.isPending}
              className="text-success border-success/40 hover:bg-success/10"
            >
              {resume.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                : <Play className="h-3.5 w-3.5 mr-1.5" />
              }
              Resume
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => pause.mutate()}
              disabled={pause.isPending}
              className="text-warning border-warning/40 hover:bg-warning/10"
            >
              {pause.isPending
                ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                : <Pause className="h-3.5 w-3.5 mr-1.5" />
              }
              Pause
            </Button>
          )}
        </SettingsRow>

        <SettingsRow
          label="Refresh Status"
          description="Poll the server for the latest processing status."
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => void statusQuery.refetch()}
            disabled={statusQuery.isFetching}
          >
            {statusQuery.isFetching
              ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            }
            Refresh
          </Button>
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
