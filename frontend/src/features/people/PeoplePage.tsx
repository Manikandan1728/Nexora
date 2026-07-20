import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCollections } from "@/hooks/useCollections";
import { runQuery } from "@/api/query.service";
import { Users, Loader2 } from "lucide-react";
import { PageHeader } from "@/components/common/PageHeader";
import { PersonCard } from "@/components/explorer/PersonCard";
import { EmptyExplorer } from "@/components/explorer/EmptyExplorer";
import { ResultCard } from "@/components/explorer/ResultCard";
import type { TelegramSource } from "@/types/query";

interface PersonEntry {
  sender_id: string;
  sender_name: string;
  count: number;
  chats: string[];
}

function aggregatePeople(sources: TelegramSource[]): PersonEntry[] {
  const map = new Map<string, PersonEntry>();
  for (const s of sources) {
    if (!s.sender_id || !s.sender_name) continue;
    if (!map.has(s.sender_id)) {
      map.set(s.sender_id, { sender_id: s.sender_id, sender_name: s.sender_name, count: 0, chats: [] });
    }
    const entry = map.get(s.sender_id)!;
    entry.count++;
    if (s.conversation_title && !entry.chats.includes(s.conversation_title)) {
      entry.chats.push(s.conversation_title);
    }
  }
  return Array.from(map.values()).sort((a, b) => b.count - a.count);
}

export default function PeoplePage() {
  const collections = useCollections();
  const collection = collections.data?.collections?.[0]?.name ?? "telegram";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["people", collection],
    queryFn: () => runQuery({
      question: "messages from people users participants",
      collection_name: collection,
      top_k: 100,
      use_rag: false,
    }),
    enabled: !!collection,
  });

  const allSources = data?.sources ?? [];

  const people = useMemo(() => aggregatePeople(allSources), [allSources]);

  const filteredPeople = search
    ? people.filter(p => p.sender_name.toLowerCase().includes(search.toLowerCase()))
    : people;

  const selectedMessages: TelegramSource[] = selectedId
    ? allSources.filter(s => s.sender_id === selectedId)
    : [];

  const selectedPerson = people.find(p => p.sender_id === selectedId);

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="People"
        description="Explore contributors across your indexed Telegram knowledge base."
      />

      <div className="flex gap-6">
        {/* People list */}
        <div className={selectedId ? "hidden lg:block w-72 shrink-0" : "flex-1"}>
          <div className="mb-4">
            <input
              type="search"
              placeholder="Search people…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30"
              aria-label="Search people"
            />
          </div>

          {isLoading && (
            <div className="flex items-center justify-center py-20 gap-2 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm">Loading people…</span>
            </div>
          )}

          {isError && (
            <EmptyExplorer title="Unable to load" description="The backend is unavailable." />
          )}

          {!isLoading && filteredPeople.length === 0 && (
            <EmptyExplorer
              icon={<Users className="h-8 w-8" />}
              title="No people found"
              description="Index Telegram chats with active participants to see them here."
            />
          )}

          {filteredPeople.length > 0 && (
            <div className="space-y-2" role="list" aria-label="People directory">
              {filteredPeople.map(person => (
                <div key={person.sender_id} role="listitem">
                  <PersonCard
                    senderId={person.sender_id}
                    senderName={person.sender_name}
                    messageCount={person.count}
                    chats={person.chats}
                    onClick={() => setSelectedId(
                      selectedId === person.sender_id ? null : person.sender_id
                    )}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Messages from selected person */}
        {selectedId && (
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-foreground">
                Messages from {selectedPerson?.sender_name}
              </h2>
              <button
                onClick={() => setSelectedId(null)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                Clear
              </button>
            </div>
            {selectedMessages.length === 0 ? (
              <EmptyExplorer
                title="No messages"
                description="No indexed messages found for this person."
              />
            ) : (
              <div className="space-y-2" role="list">
                {selectedMessages.map((s, i) => (
                  <div key={`${s.document_id}-${i}`} role="listitem">
                    <ResultCard source={s} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
