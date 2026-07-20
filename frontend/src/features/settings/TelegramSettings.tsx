import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { User, RefreshCw, LogOut, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { getTelegramStatus, disconnectTelegram, connectTelegram, listChats } from "@/api/telegram.service";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const OWNER_ID = "user_123"; // matches existing pattern across the app

export default function TelegramSettings() {
  const qc = useQueryClient();
  const [showConfirm, setShowConfirm] = useState(false);

  const status = useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => getTelegramStatus(OWNER_ID),
    refetchInterval: 30_000,
  });

  const chats = useQuery({
    queryKey: ["telegram-chats"],
    queryFn: listChats,
  });

  const disconnect = useMutation({
    mutationFn: () => disconnectTelegram(OWNER_ID),
    onSuccess: () => {
      toast.success("Telegram account disconnected.");
      void qc.invalidateQueries({ queryKey: ["telegram-status"] });
      setShowConfirm(false);
    },
    onError: () => toast.error("Failed to disconnect. Please try again."),
  });

  const reconnect = useMutation({
    mutationFn: () => connectTelegram(OWNER_ID),
    onSuccess: () => {
      toast.success("Reconnecting to Telegram…");
      void qc.invalidateQueries({ queryKey: ["telegram-status"] });
    },
    onError: () => toast.error("Failed to reconnect."),
  });

  const account = status.data?.account;
  const isConnected = status.data?.authorization_status === "ready";
  const indexedChats = chats.data?.chats.filter(c => c.indexing_enabled) ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Telegram</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Manage your connected Telegram account.</p>
      </div>

      <SettingsSection icon={<User className="h-4 w-4" />} title="Account">
        {status.isLoading ? (
          <div className="flex items-center gap-2 px-5 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading account info…
          </div>
        ) : (
          <>
            <SettingsRow label="Status">
              <Badge
                variant={isConnected ? "default" : "secondary"}
                className={cn(isConnected ? "bg-success/20 text-success border-success/30" : "")}
              >
                {isConnected ? (
                  <><CheckCircle2 className="h-3 w-3 mr-1 inline" />Connected</>
                ) : (
                  <><AlertTriangle className="h-3 w-3 mr-1 inline" />{status.data?.authorization_status ?? "Unknown"}</>
                )}
              </Badge>
            </SettingsRow>

            {account && (
              <>
                {account.display_name && (
                  <SettingsRow label="Account Name">
                    <span className="text-sm font-medium text-foreground">{account.display_name}</span>
                  </SettingsRow>
                )}
                {account.username && (
                  <SettingsRow label="Username">
                    <span className="text-sm text-muted-foreground font-mono">@{account.username}</span>
                  </SettingsRow>
                )}
                {account.phone_number_masked && (
                  <SettingsRow label="Phone Number" description="Stored encrypted on the server.">
                    <span className="text-sm font-mono text-foreground">{account.phone_number_masked}</span>
                  </SettingsRow>
                )}
              </>
            )}

            <SettingsRow label="Indexed Chats">
              <span className="text-sm font-medium text-foreground">{indexedChats.length}</span>
            </SettingsRow>
          </>
        )}
      </SettingsSection>

      <SettingsSection icon={<RefreshCw className="h-4 w-4" />} title="Account Actions">
        <SettingsRow
          label="Refresh Status"
          description="Re-fetch current account information from the server."
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => void qc.invalidateQueries({ queryKey: ["telegram-status"] })}
            disabled={status.isFetching}
          >
            {status.isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
            Refresh
          </Button>
        </SettingsRow>

        {!isConnected && (
          <SettingsRow label="Reconnect" description="Restore your Telegram session.">
            <Button
              variant="outline"
              size="sm"
              onClick={() => reconnect.mutate()}
              disabled={reconnect.isPending}
            >
              {reconnect.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
              Reconnect
            </Button>
          </SettingsRow>
        )}

        {isConnected && (
          <SettingsRow
            label="Disconnect Account"
            description="Temporarily disconnect without erasing your encrypted data."
            danger
          >
            {showConfirm ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Confirm?</span>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-danger border-danger/40 hover:bg-danger/10"
                  onClick={() => disconnect.mutate()}
                  disabled={disconnect.isPending}
                >
                  {disconnect.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <LogOut className="h-3.5 w-3.5 mr-1.5" />}
                  Yes, disconnect
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setShowConfirm(false)}>Cancel</Button>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                className="text-danger border-danger/40 hover:bg-danger/10"
                onClick={() => setShowConfirm(true)}
              >
                <LogOut className="h-3.5 w-3.5 mr-1.5" />
                Disconnect
              </Button>
            )}
          </SettingsRow>
        )}
      </SettingsSection>
    </div>
  );
}
