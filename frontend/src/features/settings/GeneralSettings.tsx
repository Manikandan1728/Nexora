import { Settings } from "lucide-react";
import { usePreferences } from "@/hooks/usePreferences";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { ToggleSwitch } from "@/components/settings/ToggleSwitch";
import { SelectField } from "@/components/settings/SelectField";
import type { DateFormat, LandingPage } from "@/hooks/usePreferences";

const LANDING_OPTIONS: Array<{ value: LandingPage; label: string }> = [
  { value: "/workspace",     label: "AI Chat" },
  { value: "/explore",       label: "Knowledge Search" },
  { value: "/conversations", label: "Conversations" },
];

const DATE_OPTIONS: Array<{ value: DateFormat; label: string }> = [
  { value: "relative", label: "Relative (2 days ago)" },
  { value: "absolute", label: "Absolute (Jan 15, 2024)" },
  { value: "iso",      label: "ISO (2024-01-15)" },
];

export default function GeneralSettings() {
  const { prefs, setPrefs } = usePreferences();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">General</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Application-wide preferences.</p>
      </div>

      <SettingsSection
        icon={<Settings className="h-4 w-4" />}
        title="Startup"
        description="Configure behavior when Nexora opens."
      >
        <SettingsRow
          label="Default Landing Page"
          description="The page shown when you first open Nexora."
          htmlFor="landing-page"
        >
          <SelectField
            id="landing-page"
            value={prefs.defaultLandingPage}
            options={LANDING_OPTIONS}
            onChange={(v) => setPrefs({ defaultLandingPage: v })}
          />
        </SettingsRow>

        <SettingsRow
          label="Remember Last Workspace"
          description="Return to your last open conversation when reopening."
          htmlFor="remember-workspace"
        >
          <ToggleSwitch
            id="remember-workspace"
            checked={prefs.rememberWorkspace}
            onChange={(v) => setPrefs({ rememberWorkspace: v })}
            label="Remember last workspace"
          />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection
        icon={<Settings className="h-4 w-4" />}
        title="Date & Time"
        description="Control how dates and times are displayed."
      >
        <SettingsRow
          label="Date Format"
          description="Choose how timestamps appear across the app."
          htmlFor="date-format"
        >
          <SelectField
            id="date-format"
            value={prefs.dateFormat}
            options={DATE_OPTIONS}
            onChange={(v) => setPrefs({ dateFormat: v })}
          />
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
