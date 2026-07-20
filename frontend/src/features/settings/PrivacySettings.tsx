import { useState } from "react";
import { ShieldCheck, Trash2, AlertTriangle, HardDrive, Lock } from "lucide-react";
import { usePreferences, getLocalStorageUsageKB } from "@/hooks/usePreferences";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { Button } from "@/components/ui/Button";
import { toast } from "sonner";

function DangerAction({
  label,
  description,
  buttonLabel,
  onConfirm,
}: {
  label: string;
  description: string;
  buttonLabel: string;
  onConfirm: () => void;
}) {
  const [confirm, setConfirm] = useState(false);
  return (
    <SettingsRow label={label} description={description} danger>
      {confirm ? (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Are you sure?</span>
          <Button
            variant="outline"
            size="sm"
            className="text-danger border-danger/40 hover:bg-danger/10"
            onClick={() => { onConfirm(); setConfirm(false); }}
          >
            <Trash2 className="h-3.5 w-3.5 mr-1.5" />
            Confirm
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>Cancel</Button>
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="text-danger border-danger/40 hover:bg-danger/10"
          onClick={() => setConfirm(true)}
        >
          <Trash2 className="h-3.5 w-3.5 mr-1.5" />
          {buttonLabel}
        </Button>
      )}
    </SettingsRow>
  );
}

export default function PrivacySettings() {
  const { resetPrefs } = usePreferences();
  const usageKB = getLocalStorageUsageKB();

  const clearConversationHistory = () => {
    localStorage.removeItem("nexora_conversations");
    toast.success("Conversation history cleared.");
  };

  const clearRecentSearches = () => {
    localStorage.removeItem("nexora_recent_searches");
    toast.success("Cached searches cleared.");
  };

  const clearAllPreferences = () => {
    resetPrefs();
    toast.success("All preferences reset to defaults.");
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Privacy & Security</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Manage your local data. No secrets or keys are ever stored in the browser.
        </p>
      </div>

      {/* Encryption status */}
      <SettingsSection icon={<Lock className="h-4 w-4" />} title="Encryption">
        <SettingsRow label="Phone Number Encryption" description="Stored AES-GCM encrypted on the server. Never exposed to the browser.">
          <span className="flex items-center gap-1 text-sm text-success font-medium">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Protected
          </span>
        </SettingsRow>
        <SettingsRow label="Session Secrets" description="Managed server-side only. This browser never holds encryption keys.">
          <span className="flex items-center gap-1 text-sm text-success font-medium">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            Server-side only
          </span>
        </SettingsRow>
      </SettingsSection>

      {/* Local storage info */}
      <SettingsSection icon={<HardDrive className="h-4 w-4" />} title="Local Storage">
        <SettingsRow label="Estimated Usage" description="Conversation history, preferences, and recent searches.">
          <span className="text-sm font-mono text-foreground">{usageKB} KB</span>
        </SettingsRow>
        <SettingsRow label="Stored Data" description="Nexora stores conversations and preferences locally. No sensitive data is held in the browser.">
          <span className="text-xs text-muted-foreground">Conversations, prefs, searches</span>
        </SettingsRow>
      </SettingsSection>

      {/* Data actions */}
      <SettingsSection
        icon={<AlertTriangle className="h-4 w-4" />}
        title="Clear Data"
        description="These actions affect local browser storage only. Indexed Telegram data on the server is not affected."
      >
        <DangerAction
          label="Clear Conversation History"
          description="Removes all AI chat conversations stored locally in this browser."
          buttonLabel="Clear History"
          onConfirm={clearConversationHistory}
        />
        <DangerAction
          label="Clear Cached Searches"
          description="Removes the list of recent searches from local storage."
          buttonLabel="Clear Searches"
          onConfirm={clearRecentSearches}
        />
        <DangerAction
          label="Reset All Preferences"
          description="Restores all settings and appearance preferences to their default values."
          buttonLabel="Reset Preferences"
          onConfirm={clearAllPreferences}
        />
      </SettingsSection>
    </div>
  );
}
