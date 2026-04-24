import { useEffect, useState } from "react";

const KEY = "lexquest_settings";

export type PersistedSettings = {
  prompt: string;
  negativePrompt: string | null;
  style?: string;
  cfg_scale: number;
  steps: number;
  num_variants: number;
  width: number;
  height: number;
  character_preset: string | null;
  lora_preset: string | null;
};

const DEFAULT_SETTINGS: PersistedSettings = {
  prompt: "",
  negativePrompt: null,
  style: "comic",
  cfg_scale: 7,
  steps: 9,
  num_variants: 4,
  width: 640,
  height: 480,
  character_preset: null,
  lora_preset: null,
};

export function usePersistedSettings() {
  const [settings, setSettings] = useState<PersistedSettings>(() => {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      try {
        const merged = { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
        if (merged.steps === 20) {
          merged.steps = DEFAULT_SETTINGS.steps;
        }
        return merged;
      } catch {
        return DEFAULT_SETTINGS;
      }
    }
    return DEFAULT_SETTINGS;
  });

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(settings));
  }, [settings]);

  const setPrompt = (prompt: string) => setSettings((prev) => ({ ...prev, prompt }));
  const setNegativePrompt = (negativePrompt: string | null) =>
    setSettings((prev) => ({ ...prev, negativePrompt }));

  return {
    settings,
    setSettings,
    setPrompt,
    setNegativePrompt,
    prompt: settings.prompt,
  };
}
