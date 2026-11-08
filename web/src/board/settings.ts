import { useEffect, useState } from "react";
import type { SttMode } from "../lib/stt";
import type { Profile } from "../lib/types";

export interface Settings {
  voice: string;
  speakOnSelect: boolean;
  sttMode: SttMode;
  profile: Profile;
}

const KEY = "adaptiboard-settings";

const DEFAULTS: Settings = {
  voice: "en-US-AriaNeural",
  speakOnSelect: true,
  sttMode: "auto",
  profile: { name: "", family: [], likes: [], notes: "" },
};

function load(): Settings {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "{}");
    if (s.sttV !== 2) delete s.sttMode; // older saves pinned "browser": move them to "auto"
    return { ...DEFAULTS, ...s, profile: { ...DEFAULTS.profile, ...(s.profile || {}) } };
  } catch {
    return DEFAULTS;
  }
}

export function useSettings() {
  const [settings, setSettings] = useState<Settings>(load);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...settings, sttV: 2 }));
    } catch {
      /* private mode: settings just won't persist */
    }
  }, [settings]);
  const update = (patch: Partial<Settings>) => setSettings((s) => ({ ...s, ...patch }));
  return [settings, update] as const;
}
