import { useState } from "react";

export type ViewMode = "cards" | "table";

// Tailwind-sm-Breakpoint (640px) - konsistent mit den `sm:`-Klassen im Rest
// der App. Nur EIN Check beim ersten Mount, kein Resize-Listener (YAGNI) -
// wer waehrend der Session vom Handy zum Desktop wechselt, nutzt den
// manuellen Toggle.
function defaultViewMode(): ViewMode {
  if (typeof window === "undefined") return "table";
  return window.matchMedia("(max-width: 639px)").matches ? "cards" : "table";
}

export function useViewMode(storageKey: string): [ViewMode, (mode: ViewMode) => void] {
  const [viewMode, setViewModeState] = useState<ViewMode>(() => {
    const stored = localStorage.getItem(storageKey);
    return stored === "cards" || stored === "table" ? stored : defaultViewMode();
  });

  function setViewMode(mode: ViewMode) {
    setViewModeState(mode);
    localStorage.setItem(storageKey, mode);
  }

  return [viewMode, setViewMode];
}
