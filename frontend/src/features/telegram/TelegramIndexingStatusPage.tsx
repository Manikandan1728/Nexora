import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Loader2, ArrowRight } from "lucide-react";
import { getProcessingStatus, pauseProcessing, resumeProcessing } from "@/api/telegram.service";
import { Card, CardContent } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Progress } from "@/components/ui/Progress";
import { useNavigate } from "react-router-dom";

export default function TelegramIndexingStatusPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["telegram-processing-status"],
    queryFn: getProcessingStatus,
    refetchInterval: 3000,
  });

  const pauseMut  = useMutation({ mutationFn: pauseProcessing,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-processing-status"] }) });
  const resumeMut = useMutation({ mutationFn: resumeProcessing,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["telegram-processing-status"] }) });

  // Simulate progress for UI demonstration since API doesn't return total count yet
  const totalMessagesEstimate = 5000;
  const processed = data?.messages_in_queue ? Math.max(0, totalMessagesEstimate - data.messages_in_queue) : 0;
  const progressPercent = Math.min(100, Math.round((processed / totalMessagesEstimate) * 100));

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6 pt-10 pb-20 animate-in fade-in zoom-in-95 duration-500">
      <div className="text-center space-y-2 mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Indexing Status</h1>
        <p className="text-muted-foreground">Nexora is downloading and embedding your Telegram conversations.</p>
      </div>

      <Card>
        <CardContent className="p-6 space-y-8">
          
          <div className="space-y-4">
            <div className="flex justify-between items-end">
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">Overall Progress</p>
                <p className="text-2xl font-bold">{progressPercent}%</p>
              </div>
              <Badge variant={data?.is_paused ? 'warning' : 'success'}>
                {data?.is_paused ? "Paused" : "Indexing Active"}
              </Badge>
            </div>
            <Progress value={progressPercent} className="h-3" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg bg-surface-hover p-4 border border-border">
              <p className="text-xs text-muted-foreground mb-1">Messages Remaining</p>
              <p className="text-xl font-semibold">
                {isLoading ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /> : data?.messages_in_queue ?? 0}
              </p>
            </div>
            <div className="rounded-lg bg-surface-hover p-4 border border-border">
              <p className="text-xs text-muted-foreground mb-1">Client Type</p>
              <p className="text-xl font-semibold capitalize">
                {isLoading ? <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /> : data?.client_type ?? "Mock"}
              </p>
            </div>
          </div>

          <div className="flex gap-4 pt-4 border-t border-border">
            <Button
              variant="outline"
              onClick={() => pauseMut.mutate()}
              disabled={data?.is_paused}
              isLoading={pauseMut.isPending}
              className="flex-1"
            >
              <Pause className="mr-2 h-4 w-4" /> Pause
            </Button>
            <Button
              onClick={() => resumeMut.mutate()}
              disabled={!data?.is_paused}
              isLoading={resumeMut.isPending}
              className="flex-1"
            >
              <Play className="mr-2 h-4 w-4" /> Resume
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end pt-6">
        <Button size="lg" onClick={() => navigate("/workspace")}>
          Enter AI Workspace <ArrowRight className="ml-2 w-4 h-4" />
        </Button>
      </div>

    </div>
  );
}
