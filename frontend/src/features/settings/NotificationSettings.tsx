import { Bell } from "lucide-react";
import { usePreferences } from "@/hooks/usePreferences";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { ToggleSwitch } from "@/components/settings/ToggleSwitch";

export default function NotificationSettings() {
  const { prefs, setPrefs } = usePreferences();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Notifications</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Control which in-app toast notifications you receive.
        </p>
      </div>

      <SettingsSection icon={<Bell className="h-4 w-4" />} title="Synchronization">
        <SettingsRow
          label="Sync Completed"
          description="Show a toast when a synchronization cycle completes successfully."
          htmlFor="notif-sync-complete"
        >
          <ToggleSwitch
            id="notif-sync-complete"
            checked={prefs.notifySyncComplete}
            onChange={(v) => setPrefs({ notifySyncComplete: v })}
            label="Notify on sync complete"
          />
        </SettingsRow>

        <SettingsRow
          label="Sync Failures"
          description="Show an alert when synchronization encounters an error."
          htmlFor="notif-sync-failure"
        >
          <ToggleSwitch
            id="notif-sync-failure"
            checked={prefs.notifySyncFailure}
            onChange={(v) => setPrefs({ notifySyncFailure: v })}
            label="Notify on sync failure"
          />
        </SettingsRow>

        <SettingsRow
          label="Connection Issues"
          description="Alert when the backend connection is lost or restored."
          htmlFor="notif-connection"
        >
          <ToggleSwitch
            id="notif-connection"
            checked={prefs.notifyConnectionIssue}
            onChange={(v) => setPrefs({ notifyConnectionIssue: v })}
            label="Notify on connection issues"
          />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection icon={<Bell className="h-4 w-4" />} title="AI">
        <SettingsRow
          label="AI Errors"
          description="Show a notification when the AI fails to generate an answer."
          htmlFor="notif-ai-error"
        >
          <ToggleSwitch
            id="notif-ai-error"
            checked={prefs.notifyAiError}
            onChange={(v) => setPrefs({ notifyAiError: v })}
            label="Notify on AI errors"
          />
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
