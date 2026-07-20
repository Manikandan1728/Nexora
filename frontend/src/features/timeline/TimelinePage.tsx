import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCollections } from "@/hooks/useCollections";
import { runQuery } from "@/api/query.service";
import { CalendarDays, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { TimelineGroup } from "@/components/explorer/TimelineGroup";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import type { TelegramSource } from "@/types/query";
import { Button } from "@/components/ui/Button";

function groupByDate(sources: TelegramSource[]): Map<string, TelegramSource[]> {
  const map = new Map<string, TelegramSource[]>();
  for (const source of sources) {
    if (!source.timestamp) continue;
    const d = new Date(source.timestamp);
    const label = d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
    if (!map.has(label)) map.set(label, []);
    map.get(label)!.push(source);
  }
  return map;
}

export default function TimelinePage() {
  const collections = useCollections();
  const collection = collections.data?.collections?.[0]?.name ?? "telegram";
  const [monthOffset, setMonthOffset] = useState(0);

  const targetDate = useMemo(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - monthOffset);
    return d;
  }, [monthOffset]);

  const monthLabel = targetDate.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["timeline", collection, monthLabel],
    queryFn: () => runQuery({
      question: `messages from ${monthLabel}`,
      collection_name: collection,
      top_k: 100,
      use_rag: false,
    }),
    enabled: !!collection,
  });

  const grouped = useMemo(() => {
    const sources = data?.sources ?? [];
    // Sort newest first
    const sorted = [...sources].sort((a, b) =>
      new Date(b.timestamp ?? 0).getTime() - new Date(a.timestamp ?? 0).getTime()
    );
    return groupByDate(sorted);
  }, [data]);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <PageHeader
          title="Timeline"
          description="Chronological view of your indexed Telegram content."
        />
        {/* Month navigator */}
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="icon" onClick={() => setMonthOffset(o => o + 1)} aria-label="Previous month">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-medium text-foreground min-w-[130px] text-center">{monthLabel}</span>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setMonthOffset(o => Math.max(0, o - 1))}
            disabled={monthOffset === 0}
            aria-label="Next month"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading timeline…</span>
        </div>
      )}

      {isError && (
        <EmptyExplorer
          title="Unable to load timeline"
          description="The backend is unavailable."
        />
      )}

      {!isLoading && grouped.size === 0 && (
        <EmptyExplorer
          icon={<CalendarDays className="h-8 w-8" />}
          title="No activity this month"
          description="Try navigating to a previous month or indexing more Telegram chats."
        />
      )}

      {/* Timeline */}
      <div className="pl-2">
        {Array.from(grouped.entries()).map(([dateLabel, sources]) => (
          <TimelineGroup
            key={dateLabel}
            dateLabel={dateLabel}
            sources={sources}
            defaultOpen={true}
          />
        ))}
      </div>
    </div>
  );
}
