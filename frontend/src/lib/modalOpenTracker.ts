import { useEffect } from "react";

// Schlanker, modul-globaler Zaehler statt Context/Redux - jedes *DetailModal
// ruft useModalOpenTracking() einmal auf, waehrend es gemountet ist (die
// Modals werden ohnehin nur per `{selected && <XModal ... />}` bedingt
// gerendert, Mount/Unmount fallen exakt mit Auf/Zu zusammen). App.tsx prueft
// isAnyModalOpen() synchron beim Swipe-Handling, um ein Wischen im offenen
// Modal nicht versehentlich den Hintergrund-Tab wechseln zu lassen.
let openModalCount = 0;

// `active` (Default true) erlaubt es, den Zaehler auch ohne Unmount des
// Modals zu decrementieren - noetig fuer WunschkaderTab, das permanent
// gemountet bleibt (siehe App.tsx, wunschkaderPhase-Kommentar): dessen
// DetailModal/AddTargetModal bleiben beim Tab-Wechsel offen (React-State
// bleibt erhalten), duerfen aber nicht auf ewig als "offenes Modal" zaehlen
// und damit Swipe-Tab-Wechsel app-weit blockieren, waehrend Wunschkader gar
// nicht der sichtbare Tab ist. Alle anderen ~7 Aufrufer (PlayerCompareModal,
// MobileTabMenu, etc.) nutzen weiterhin den Default und bleiben unveraendert.
export function useModalOpenTracking(active: boolean = true): void {
  useEffect(() => {
    if (!active) return;
    openModalCount += 1;
    return () => {
      openModalCount -= 1;
    };
  }, [active]);
}

export function isAnyModalOpen(): boolean {
  return openModalCount > 0;
}
