import { useState, useCallback, useEffect } from "react";

const PREFS_KEY = "nexora_prefs";

export type DateFormat = "relative" | "absolute" | "iso";
export type Density = "comfortable" | "compact";
export type FontSize = "sm" | "md" | "lg";
export type LandingPage = "/workspace" | "/explore" | "/conversations";

export interface Preferences {
  // General
  defaultLandingPage: LandingPage;
  dateFormat: DateFormat;
  rememberWorkspace: boolean;
  // Appearance (theme is managed separately by useTheme)
  density: Density;
  fontSize: FontSize;
  reducedMotion: boolean;
  // Notifications
  notifySyncComplete: boolean;
  notifySyncFailure: boolean;
  notifyConnectionIssue: boolean;
  notifyAiError: boolean;
}

const DEFAULTS: Preferences = {
  defaultLandingPage: "/workspace",
  dateFormat: "relative",
  rememberWorkspace: true,
  density: "comfortable",
  fontSize: "md",
  reducedMotion: false,
  notifySyncComplete: true,
  notifySyncFailure: true,
  notifyConnectionIssue: true,
  notifyAiError: false,
};

function load(): Preferences {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return { ...DEFAULTS };
    return { ...DEFAULTS, ...JSON.parse(raw) } as Preferences;
  } catch {
    return { ...DEFAULTS };
  }
}

function save(prefs: Preferences): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // ignore quota errors
  }
}

// Apply CSS side effects for density and font-size
function applyPrefsToDOM(prefs: Preferences) {
  const root = document.documentElement;
  // Density
  root.setAttribute("data-density", prefs.density);
  // Font size
  root.setAttribute("data-font-size", prefs.fontSize);
  // Reduced motion
  if (prefs.reducedMotion) {
    root.setAttribute("data-reduced-motion", "true");
  } else {
    root.removeAttribute("data-reduced-motion");
  }
}

export function usePreferences() {
  const [prefs, setPrefsState] = useState<Preferences>(load);

  useEffect(() => {
    applyPrefsToDOM(prefs);
  }, [prefs]);

  const setPrefs = useCallback((patch: Partial<Preferences>) => {
    setPrefsState((prev) => {
      const next = { ...prev, ...patch };
      save(next);
      return next;
    });
  }, []);

  const resetPrefs = useCallback(() => {
    localStorage.removeItem(PREFS_KEY);
    setPrefsState({ ...DEFAULTS });
  }, []);

  return { prefs, setPrefs, resetPrefs };
}

// Storage size helper (KB)
export function getLocalStorageUsageKB(): number {
  try {
    let total = 0;
    for (const key of Object.keys(localStorage)) {
      total += (localStorage.getItem(key) ?? "").length * 2; // UTF-16 chars
    }
    return Math.round(total / 1024);
  } catch {
    return 0;
  }
}
