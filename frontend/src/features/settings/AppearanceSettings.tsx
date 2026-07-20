import { Palette, Type, Layers, Zap } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { usePreferences } from "@/hooks/usePreferences";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { SettingsRow } from "@/components/settings/SettingsRow";
import { ToggleSwitch } from "@/components/settings/ToggleSwitch";
import { SelectField } from "@/components/settings/SelectField";
import type { Density, FontSize } from "@/hooks/usePreferences";

const DENSITY_OPTIONS: Array<{ value: Density; label: string }> = [
  { value: "comfortable", label: "Comfortable" },
  { value: "compact",     label: "Compact" },
];

const FONT_OPTIONS: Array<{ value: FontSize; label: string }> = [
  { value: "sm", label: "Small" },
  { value: "md", label: "Medium (default)" },
  { value: "lg", label: "Large" },
];

export default function AppearanceSettings() {
  const { theme } = useTheme();
  const { prefs, setPrefs } = usePreferences();

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-foreground">Appearance</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Customize Nexora's look and feel.</p>
      </div>

      <SettingsSection icon={<Palette className="h-4 w-4" />} title="Theme">
        <SettingsRow
          label="Color Theme"
          description={`Currently using ${theme} theme.`}
        >
          <ThemeToggle compact={false} />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection icon={<Layers className="h-4 w-4" />} title="Layout">
        <SettingsRow
          label="Density"
          description="Adjust spacing and padding across the interface."
          htmlFor="density"
        >
          <SelectField
            id="density"
            value={prefs.density}
            options={DENSITY_OPTIONS}
            onChange={(v) => setPrefs({ density: v })}
          />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection icon={<Type className="h-4 w-4" />} title="Typography">
        <SettingsRow
          label="Font Size"
          description="Adjust the base font size across all text."
          htmlFor="font-size"
        >
          <SelectField
            id="font-size"
            value={prefs.fontSize}
            options={FONT_OPTIONS}
            onChange={(v) => setPrefs({ fontSize: v })}
          />
        </SettingsRow>
      </SettingsSection>

      <SettingsSection icon={<Zap className="h-4 w-4" />} title="Motion">
        <SettingsRow
          label="Reduce Motion"
          description="Disable animations and transitions for accessibility or performance."
          htmlFor="reduced-motion"
        >
          <ToggleSwitch
            id="reduced-motion"
            checked={prefs.reducedMotion}
            onChange={(v) => setPrefs({ reducedMotion: v })}
            label="Reduce motion"
          />
        </SettingsRow>
      </SettingsSection>
    </div>
  );
}
