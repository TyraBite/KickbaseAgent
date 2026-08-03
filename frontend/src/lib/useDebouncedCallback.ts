import { useEffect, useRef } from "react";

export type DebouncedFunction<Args extends unknown[]> = ((...args: Args) => void) & {
  cancel: () => void;
};

// Reine Timer-Logik ohne React-Abhaengigkeiten - direkt mit vitest fake
// timers testbar (vite.config.ts laeuft mit environment: "node", es gibt
// kein jsdom zum Rendern eines Hooks). Analog zu nextHeaderVisible() in
// useHideOnScroll.ts: der eigentliche Hook unten ist nur ein duenner
// React-Wrapper, der bei jedem Re-Render dieselbe Debounce-Instanz
// wiederverwendet statt eine neue zu erzeugen (sonst wuerde ein laufender
// Timer bei jedem Tastendruck durch eine neue, leere Instanz ersetzt).
export function createDebouncedFunction<Args extends unknown[]>(
  fn: (...args: Args) => void,
  delayMs: number
): DebouncedFunction<Args> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const debounced = ((...args: Args) => {
    if (timeoutId !== null) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
      timeoutId = null;
      fn(...args);
    }, delayMs);
  }) as DebouncedFunction<Args>;

  debounced.cancel = () => {
    if (timeoutId !== null) clearTimeout(timeoutId);
    timeoutId = null;
  };

  return debounced;
}

// React-Hook fuer Callbacks, die erst ~delayMs nach dem letzten Aufruf
// wirklich ausgefuehrt werden sollen (z.B. Firestore-Save nach einer
// Freitext-Eingabe, nicht bei jedem Tastendruck). callbackRef haelt immer
// die aktuellste Callback-Version, ohne die Debounce-Instanz selbst bei
// jedem Render neu zu erzeugen.
export function useDebouncedCallback<Args extends unknown[]>(
  callback: (...args: Args) => void,
  delayMs: number
): (...args: Args) => void {
  const callbackRef = useRef(callback);
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  const debouncedRef = useRef<DebouncedFunction<Args> | null>(null);
  if (debouncedRef.current === null) {
    debouncedRef.current = createDebouncedFunction<Args>((...args) => callbackRef.current(...args), delayMs);
  }

  useEffect(() => {
    const debounced = debouncedRef.current;
    return () => debounced?.cancel();
  }, []);

  return debouncedRef.current;
}
