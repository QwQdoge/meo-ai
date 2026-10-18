import { useEffect, useState } from "react";

export type BrowserPreferences = {
  general: { enter_to_send: boolean };
  appearance: { theme: "system" | "light" | "dark"; reduce_motion: boolean };
};
const storageKey = "meo:browser-preferences:v1";
const changed = "meo:browser-preferences-changed";
const defaults: BrowserPreferences = {
  general: { enter_to_send: true },
  appearance: { theme: "system", reduce_motion: false },
};
export function readBrowserPreferences(): BrowserPreferences {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (
      typeof value?.general?.enter_to_send === "boolean" &&
      ["system", "light", "dark"].includes(value?.appearance?.theme) &&
      typeof value?.appearance?.reduce_motion === "boolean"
    ) {
      // Only device interaction settings belong in ordinary browser storage.
      return {
        general: { enter_to_send: value.general.enter_to_send },
        appearance: {
          theme: value.appearance.theme,
          reduce_motion: value.appearance.reduce_motion,
        },
      };
    }
  } catch {
    /* An unavailable store still allows defaults; writes report failure. */
  }
  return structuredClone(defaults);
}
export function applyAppearance(value: BrowserPreferences) {
  document.documentElement.dataset.theme = value.appearance.theme;
  document.documentElement.dataset.reduceMotion = String(
    value.appearance.reduce_motion,
  );
}
export function saveBrowserPreferences(value: BrowserPreferences) {
  localStorage.setItem(storageKey, JSON.stringify(value));
  applyAppearance(value);
  window.dispatchEvent(new Event(changed));
}
export function useBrowserPreferences() {
  const [value, setValue] = useState(readBrowserPreferences);
  useEffect(() => {
    const refresh = () => {
      const next = readBrowserPreferences();
      setValue(next);
      applyAppearance(next);
    };
    refresh();
    window.addEventListener(changed, refresh);
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) refresh();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(changed, refresh);
      window.removeEventListener("storage", onStorage);
    };
  }, []);
  return value;
}
