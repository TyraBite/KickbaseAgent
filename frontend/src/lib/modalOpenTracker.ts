import { useEffect } from "react";

// Schlanker, modul-globaler Zaehler statt Context/Redux - jedes *DetailModal
// ruft useModalOpenTracking() einmal auf, waehrend es gemountet ist (die
// Modals werden ohnehin nur per `{selected && <XModal ... />}` bedingt
// gerendert, Mount/Unmount fallen exakt mit Auf/Zu zusammen). App.tsx prueft
// isAnyModalOpen() synchron beim Swipe-Handling, um ein Wischen im offenen
// Modal nicht versehentlich den Hintergrund-Tab wechseln zu lassen.
let openModalCount = 0;

export function useModalOpenTracking(): void {
  useEffect(() => {
    openModalCount += 1;
    return () => {
      openModalCount -= 1;
    };
  }, []);
}

export function isAnyModalOpen(): boolean {
  return openModalCount > 0;
}
