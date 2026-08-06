import type { Variants } from "framer-motion";

// Zentrale Duration/Easing-Werte - jede Komponente importiert von hier statt
// eigene Zahlen zu erfinden (sonst laufen Tab-Wechsel und Modal-Timing
// auseinander). Exit laeuft bewusst kuerzer als Enter ("exit schneller als
// enter" ist eine anerkannte Motion-Faustregel, vermeidet traege wirkende
// UI beim Verlassen eines Zustands).
export const FADE_ENTER_S = 0.18;
export const FADE_EXIT_S = 0.13;
export const SLIDE_DISTANCE_PX = 24;
export const PANEL_SLIDE_DISTANCE_PX = 32;
export const STAGGER_STEP_S = 0.05;

export const fadeVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: FADE_ENTER_S } },
  exit: { opacity: 0, transition: { duration: FADE_EXIT_S } },
};

// direction 1 = naechster Tab (von rechts rein), -1 = vorheriger Tab (von
// links rein) - Vorzeichen kommt 1:1 aus useSwipeTabs' bestehendem
// dx-Vorzeichen, keine neue Richtungslogik.
export function slideFadeVariants(direction: 1 | -1): Variants {
  return {
    initial: { opacity: 0, x: direction * SLIDE_DISTANCE_PX },
    animate: { opacity: 1, x: 0, transition: { duration: FADE_ENTER_S, ease: "easeOut" } },
    exit: { opacity: 0, x: direction * -SLIDE_DISTANCE_PX, transition: { duration: FADE_EXIT_S, ease: "easeIn" } },
  };
}

export const backdropVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: FADE_ENTER_S } },
  exit: { opacity: 0, transition: { duration: FADE_EXIT_S } },
};

// "left" fuer MobileTabMenu (Drawer kommt von links), "center" fuer
// PlayerCompareModal (zentrierte Karte, Scale statt Slide).
export function panelVariants(from: "left" | "center"): Variants {
  if (from === "left") {
    return {
      initial: { opacity: 0, x: -PANEL_SLIDE_DISTANCE_PX },
      animate: { opacity: 1, x: 0, transition: { duration: FADE_ENTER_S, ease: "easeOut" } },
      exit: { opacity: 0, x: -PANEL_SLIDE_DISTANCE_PX, transition: { duration: FADE_EXIT_S, ease: "easeIn" } },
    };
  }
  return {
    initial: { opacity: 0, scale: 0.96 },
    animate: { opacity: 1, scale: 1, transition: { duration: FADE_ENTER_S, ease: "easeOut" } },
    exit: { opacity: 0, scale: 0.96, transition: { duration: FADE_EXIT_S, ease: "easeIn" } },
  };
}

// Jede Kachel steuert ihren eigenen Enter/Exit ueber initial/animate/exit - noetig,
// damit AnimatePresence beim Entfernen einer einzelnen Kachel deren eigenen Exit
// spielt. Das macht sie in Framer Motions Sinn "self-controlling"
// (isControllingVariants() greift), wofuer ein Eltern-`staggerChildren` NICHT mehr
// wirkt (Framer Motion traegt selbst-steuernde Kinder nicht in das
// variantChildren-Set des Elternknotens ein - Live-Review-Fund 2026-08-05: der
// vorherige staggerContainerVariants-Ansatz war dadurch strukturell tot, alle
// Karten kamen gleichzeitig rein). Der Stagger kommt deshalb hier ueber einen
// manuellen Delay pro Karten-Index: `custom={index}` an der jeweiligen motion.div
// uebergeben, `animate` liest diesen Index als Funktions-Custom-Wert (Framer
// Motions "dynamic variants").
export const staggerItemVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: FADE_ENTER_S, delay: index * STAGGER_STEP_S },
  }),
  exit: { opacity: 0, transition: { duration: FADE_EXIT_S } },
};
