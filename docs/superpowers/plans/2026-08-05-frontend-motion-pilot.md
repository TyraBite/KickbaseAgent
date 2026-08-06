# Frontend-Motion-Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `framer-motion` in `frontend/` einführen, um Tab-Wechsel, beide Overlay-Modals (`PlayerCompareModal`,
`MobileTabMenu`) und die Wunschkader-Kartenliste zu animieren — ohne bestehende Funktionalität (Autosave,
Simulationsmodus-State-Erhalt, Swipe-Erkennung) zu verändern.

**Architecture:** Ein neues, zentrales `frontend/src/lib/motionVariants.ts` liefert alle Duration/Easing-Werte.
`App.tsx` bekommt eine `AnimatePresence`-gesteuerte Tab-Umschaltung für 8 der 9 Tabs; der Wunschkader-Tab bleibt
aus State-Erhaltungsgründen permanent gemountet und nutzt stattdessen einen eigenen Phasen-State
(`active`/`exiting`/`hidden`) plus CSS-Grid-Stacking für einen sauberen Exit-Fade ohne Scroll-Höhen-Sprung. Beide
Overlay-Modals wechseln von instant sichtbar/unsichtbar auf `AnimatePresence`-gesteuertes Un-/Mounten. Die
Wunschkader-Kartenliste bekommt `layoutId`-Karten für automatische Reorder-Animation plus Stagger beim Laden.

**Tech Stack:** React 18, Vite 5, TypeScript, Tailwind 3 (`darkMode: "media"`), neu: `framer-motion` (`^13.0.0`).

## Global Constraints

- Design ist in `docs/superpowers/specs/2026-08-05-frontend-motion-pilot-design.md` festgelegt und user-approved — bei Widerspruch zwischen Plan und Spec gilt die Spec, Abweichung mit dem User klären, nicht still entscheiden.
- Keine Farb-/Typografie-/Layout-Änderungen — nur Motion.
- Kein Umbau von `useSwipeTabs` auf Echtzeit-Drag-Gesten — die bestehende Schwellenwert-Erkennung nach Release bleibt unverändert, nur die Richtung wird an einen neuen `tabTransition`-State weitergereicht.
- Kein Motion für Transfermarkt-/Alle-Spieler-Kartenlisten oder `components/table.tsx`-Sortier-Tabellen (Phase 2, nicht Teil dieses Plans).
- Kein Drag-and-Drop für Wunschkader-Karten (eigener Folge-Spec).
- `npm install`/`npm run` **niemals im Haupt-Checkout** (`/workspace/work`) ausführen — nur in der isolierten Git-Worktree, die die Ausführungs-Skill für diesen Plan angelegt hat (CLAUDE.md-Sandbox-Regel, Windows-DrvFs-Mount).
- Zeilenenden LF (`.gitattributes`), keine CRLF committen.
- Commits ohne `Co-Authored-By`-Zeile.
- `framer-motion` per Caret-Range in `package.json` (`^13.0.0`) — passend zur bestehenden Konvention dort (die Python-Exact-Pin-Regel aus `CLAUDE.md` gilt nur für `requirements.txt`).
- Jeder neue Test läuft gegen den echten, aktuellen Code (bereits gegen `App.tsx`, `PlayerCompareModal.tsx`, `WunschkaderTab.tsx`, `formations.ts` verifiziert, Stand dieses Plans) — nicht gegen eine angenommene Struktur.

---

## Datei-Übersicht

| Datei | Änderung |
|---|---|
| `frontend/package.json` | `framer-motion` als Dependency |
| `frontend/src/lib/motionVariants.ts` | **neu** — zentrale Variants |
| `frontend/src/lib/motionVariants.test.ts` | **neu** — Vitest für die reine Logik darin |
| `frontend/src/App.tsx` | `MotionConfig`, `tabTransition`-State, `AnimatePresence`-Tab-Rendering, Wunschkader-Phasen-State+Grid-Stack |
| `frontend/src/components/WunschkaderTab.tsx` | `layoutId`-Karten, Stagger, `AnimatePresence` für Add/Remove |
| `frontend/src/components/PlayerCompareModal.tsx` | Backdrop/Panel zu `motion.div` |
| `frontend/src/components/AlleSpielerTab.tsx` | Modal-Call-Site in `AnimatePresence` |
| `frontend/src/components/EigenesTeamTab.tsx` | 2 Modal-Call-Sites in `AnimatePresence` |
| `frontend/tests-e2e/TabSwitchReducedMotion.spec.ts` | **neu** |
| `frontend/tests-e2e/WunschkaderStatePersistsAcrossTabSwitch.spec.ts` | **neu** |
| `frontend/tests-ct/WunschkaderTabCardMotion.ct.tsx` | **neu** |
| `frontend/tests-e2e/MobileMenuReducedMotion.spec.ts` | **neu** |

---

### Task 1: `framer-motion` installieren + zentrale Motion-Variants

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/lib/motionVariants.ts`
- Test: `frontend/src/lib/motionVariants.test.ts`

**Interfaces:**
- Produces: `fadeVariants: Variants`, `slideFadeVariants(direction: 1 | -1): Variants`, `backdropVariants: Variants`, `panelVariants(from: "left" | "center"): Variants`, `staggerContainerVariants: Variants`, `staggerItemVariants: Variants` — alle aus `framer-motion` (`Variants`-Typ).

- [ ] **Step 1: `framer-motion` zu `frontend/package.json` hinzufügen**

In `"dependencies"` (nach `"firebase"`, alphabetisch):

```json
"dependencies": {
  "firebase": "^10.14.1",
  "framer-motion": "^13.0.0",
  "react": "^18.3.1",
  "react-dom": "^18.3.1"
},
```

- [ ] **Step 2: In der Worktree installieren**

Run (in der für diesen Plan angelegten Git-Worktree, NICHT in `/workspace/work`): `npm install`
Expected: `node_modules/framer-motion` existiert, `package-lock.json` aktualisiert sich.

- [ ] **Step 3: `motionVariants.ts` schreiben**

```ts
// frontend/src/lib/motionVariants.ts
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

export const staggerContainerVariants: Variants = {
  initial: {},
  animate: { transition: { staggerChildren: STAGGER_STEP_S } },
};

export const staggerItemVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: FADE_ENTER_S } },
  exit: { opacity: 0, transition: { duration: FADE_EXIT_S } },
};
```

- [ ] **Step 4: Test schreiben**

```ts
// frontend/src/lib/motionVariants.test.ts
import { describe, expect, it } from "vitest";
import { panelVariants, slideFadeVariants } from "./motionVariants";

describe("slideFadeVariants", () => {
  it("startet rechts ausserhalb bei Richtung 1 (naechster Tab)", () => {
    const variants = slideFadeVariants(1);
    expect((variants.initial as { x: number }).x).toBeGreaterThan(0);
  });

  it("startet links ausserhalb bei Richtung -1 (vorheriger Tab)", () => {
    const variants = slideFadeVariants(-1);
    expect((variants.initial as { x: number }).x).toBeLessThan(0);
  });

  it("exit-Richtung ist entgegengesetzt zur enter-Richtung", () => {
    const variants = slideFadeVariants(1);
    const enterX = (variants.initial as { x: number }).x;
    const exitX = (variants.exit as { x: number }).x;
    expect(Math.sign(exitX)).not.toBe(Math.sign(enterX));
  });
});

describe("panelVariants", () => {
  it("liefert einen Slide-von-links fuer 'left'", () => {
    const variants = panelVariants("left");
    expect((variants.initial as { x: number }).x).toBeLessThan(0);
  });

  it("liefert einen Scale-Fade fuer 'center', keinen Slide", () => {
    const variants = panelVariants("center");
    expect(variants.initial).not.toHaveProperty("x");
    expect((variants.initial as { scale: number }).scale).toBeLessThan(1);
  });
});
```

- [ ] **Step 5: Test laufen lassen**

Run: `npm run test -- motionVariants`
Expected: 5 Tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/motionVariants.ts frontend/src/lib/motionVariants.test.ts
git commit -m "feat(frontend): framer-motion + zentrale Motion-Variants"
```

---

### Task 2: `App.tsx` — AnimatePresence-Tab-Wechsel für 8 Tabs + Reduced-Motion-Wrapper

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests-e2e/TabSwitchReducedMotion.spec.ts` (neu)

**Interfaces:**
- Consumes: `fadeVariants`, `slideFadeVariants(direction)` aus `frontend/src/lib/motionVariants.ts` (Task 1).
- Produces: `TabTransition` type (`{ kind: "fade" } | { kind: "slide"; direction: 1 | -1 }`), genutzt in Task 3.

Wunschkader bleibt in diesem Task **unverändert** (weiter simple `hidden`-Klasse) — Task 3 baut darauf die
Grid-Stack-Exit-Animation.

- [ ] **Step 1: Imports ergänzen**

In `frontend/src/App.tsx`, nach den bestehenden Imports:

```tsx
import { AnimatePresence, motion, MotionConfig } from "framer-motion";
import { fadeVariants, slideFadeVariants } from "./lib/motionVariants";
```

- [ ] **Step 2: `TabTransition`-Type + State**

Nach `type LoadState = "loading" | "error" | "ready";` ergänzen:

```tsx
type TabTransition = { kind: "fade" } | { kind: "slide"; direction: 1 | -1 };
```

In `App()`, nach `const [mobileMenuOpen, setMobileMenuOpen] = useState(false);`:

```tsx
const [tabTransition, setTabTransition] = useState<TabTransition>({ kind: "fade" });
```

- [ ] **Step 3: `useSwipeTabs` um Richtungs-Signal erweitern**

Ersetze die bestehende Funktion (Signatur + `onTouchEnd`-Body):

```tsx
function useSwipeTabs(
  activeTab: string,
  setActiveTab: (key: string) => void,
  setTabTransition: (t: TabTransition) => void
) {
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  function onTouchStart(e: ReactTouchEvent<HTMLElement>) {
    touchStart.current = null;
    if (isAnyModalOpen()) return;
    const target = e.target as HTMLElement;
    if (target.closest("[data-swipe-ignore]")) return;
    touchStart.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }

  function onTouchEnd(e: ReactTouchEvent<HTMLElement>) {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start || isAnyModalOpen()) return;

    const dx = e.changedTouches[0].clientX - start.x;
    const dy = e.changedTouches[0].clientY - start.y;
    if (Math.abs(dy) > SWIPE_MAX_VERTICAL_PX || Math.abs(dx) < SWIPE_THRESHOLD_PX) return;

    const activeKeys = TABS.filter((t) => ACTIVE_TABS.has(t.key)).map((t) => t.key);
    const i = activeKeys.indexOf(activeTab);
    const next = dx < 0 ? activeKeys[i + 1] : activeKeys[i - 1];
    if (next) {
      setTabTransition({ kind: "slide", direction: dx < 0 ? 1 : -1 });
      setActiveTab(next);
    }
  }

  return { onTouchStart, onTouchEnd };
}
```

(Einzige Änderung: dritter Parameter `setTabTransition`, plus die zwei neuen Zeilen direkt vor `setActiveTab(next)`
im `if (next)`-Block. Die Schwellenwert-Erkennung selbst ist unverändert.)

- [ ] **Step 4: Call-Site von `useSwipeTabs` anpassen**

```tsx
const { onTouchStart, onTouchEnd } = useSwipeTabs(activeTab, setActiveTab, setTabTransition);
```

- [ ] **Step 5: Desktop-Navleiste auf Fade umstellen**

In der Desktop-`<nav>` (`sm:flex`), der Button-`onClick`:

```tsx
onClick={() => {
  if (!isActive) return;
  setTabTransition({ kind: "fade" });
  setActiveTab(tab.key);
}}
```

(ersetzt `onClick={() => isActive && setActiveTab(tab.key)}`.)

- [ ] **Step 6: Mobile-Menü-Auswahl auf Fade umstellen**

Beim Rendern von `<MobileTabMenu>`:

```tsx
{mobileMenuOpen && (
  <MobileTabMenu
    activeTab={activeTab}
    onSelect={(key) => {
      setTabTransition({ kind: "fade" });
      setActiveTab(key);
    }}
    onClose={() => setMobileMenuOpen(false)}
  />
)}
```

- [ ] **Step 7: `MotionConfig` um den Root-Return wrappen**

```tsx
return (
  <MotionConfig reducedMotion="user">
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      {/* ... unveraendert ... */}
    </div>
  </MotionConfig>
);
```

- [ ] **Step 8: Die 8 Nicht-Wunschkader-Tab-Blöcke durch eine `AnimatePresence`-Renderfunktion ersetzen**

Ersetze im `<main>`-Block die sieben Blöcke für `dashboard`, `spekulation`, `team`, `alle-spieler`,
`transfermarkt`, `liga`, `ml-genauigkeit` **und** den `feedback`-Block (Wunschkader-Block bleibt exakt wie er ist,
unverändert an seiner Stelle stehen lassen):

```tsx
{loadState === "ready" && data && data.players && wunschkader && (
  <div className={activeTab === "wunschkader" ? "" : "hidden"}>
    <WunschkaderTab data={data} wunschkader={wunschkader} onSaved={(targets) => setWunschkader({ targets })} />
  </div>
)}
<AnimatePresence mode="wait">
  {(() => {
      let content: JSX.Element | null = null;
      if (activeTab === "dashboard" && data && data.players && wunschkader) {
        content = <DashboardTab data={data} wunschkader={wunschkader} transfermarktRows={transfermarktRows} now={now} />;
      } else if (activeTab === "spekulation" && data && data.players) {
        content = (
          <SpekulationTab
            rows={spekulationRows}
            now={now}
            mlMetrics={data.ml_metrics}
            mlMetrics3d={data.ml_metrics_3d ?? null}
            bidHistory={data.bid_premium_history ?? []}
            positionNeed={data.position_need ?? {}}
          />
        );
      } else if (activeTab === "team" && data && data.players && wunschkader) {
        content = <EigenesTeamTab data={data} wunschkader={wunschkader} />;
      } else if (activeTab === "alle-spieler" && data && data.players) {
        content = <AlleSpielerTab data={data} />;
      } else if (activeTab === "transfermarkt" && data && data.players) {
        content = <TransfermarktTab data={data} rows={transfermarktRows} now={now} />;
      } else if (activeTab === "liga" && data && data.players) {
        content = <LigaanalyseTab data={data} />;
      } else if (activeTab === "ml-genauigkeit" && data && data.players) {
        content = <MlGenauigkeitTab data={data} />;
      } else if (activeTab === "feedback") {
        content = <FeedbackTab now={now} />;
      }
      return (
        <motion.div
          key={activeTab}
          variants={tabTransition.kind === "fade" ? fadeVariants : slideFadeVariants(tabTransition.direction)}
          initial="initial"
          animate="animate"
          exit="exit"
        >
          {content}
        </motion.div>
      );
  })()}
</AnimatePresence>
```

Es gibt bewusst **keinen** `else if (activeTab === "wunschkader")`-Zweig — `content` bleibt in dem Fall `null`,
der `motion.div` rendert leer (Wunschkader zeigt seinen eigenen Inhalt separat über den unveränderten
`hidden`-Toggle-Block direkt darüber).

`mode="wait"` ist bewusst gewählt (nicht der AnimatePresence-Default `"sync"`): zwei verschiedene Tabs haben
sehr unterschiedliche Höhen, ein Überlappen beim Wechsel zwischen z.B. `dashboard` und `ml-genauigkeit` sähe
sprunghaft aus. Sequenziell (erst raus, dann rein) passt besser zu einem dichten Dashboard als eine Kino-Überblendung.

Der `<AnimatePresence>`-Tag selbst bleibt **immer** gerendert (nie hinter einer Bedingung) — nur sein Kind
(`{...}`) wird bedingt `null`/ein `motion.div`. Würde man `<AnimatePresence>` selbst bedingt rendern, würde React
es beim Wegfallen der Bedingung sofort unmounten, ohne dass die Exit-Animation seines Kindes überhaupt startet.

Während `loadState !== "ready"` liefert die IIFE für die meisten Tabs `content = null` — der `motion.div` rendert
dann leer (kein sichtbarer Unterschied zu vorher, wo der ganze Block gar nicht existierte). Für `feedback` bleibt
`content` unabhängig von `loadState` gesetzt, exakt wie im bisherigen Verhalten (der Feedback-Tab funktioniert
auch ohne geladenen Dashboard-Snapshot).

- [ ] **Step 9: Bestehende Swipe-/Modal-E2E-Tests laufen lassen**

Run: `npm run test:e2e -- SwipeBlockedByModal TouchScrubVsSwipe`
Expected: beide Specs PASS unverändert (funktionales Verhalten identisch, nur jetzt animiert).

- [ ] **Step 10: Neuen Reduced-Motion-Funktionstest schreiben**

```ts
// frontend/tests-e2e/TabSwitchReducedMotion.spec.ts
import { test, expect } from "@playwright/test";
import { touchDrag } from "./touchHelpers";

test.describe("Tab-Wechsel bleibt unter prefers-reduced-motion funktional", () => {
  test("Klick-Wechsel (Fade) landet auf dem richtigen Tab, keine Konsolenfehler", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Modell-Tracking", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Modell-Tracking");
    expect(consoleErrors).toEqual([]);
  });

  test("Swipe-Wechsel (Slide) landet auf dem richtigen Tab, keine Konsolenfehler", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await mobileNav.getByRole("button", { name: "Spekulation", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Spekulation");

    await page.evaluate(() => window.scrollTo(0, 0));
    const viewport = page.viewportSize();
    if (!viewport) throw new Error("kein Viewport gesetzt");
    const headingBox = await heading.boundingBox();
    if (!headingBox) throw new Error("Ueberschrift hat kein boundingBox()");
    const y = headingBox.y + headingBox.height / 2;
    await touchDrag(page, { x: viewport.width - 20, y }, { x: 20, y });

    await expect(heading).toHaveText("Wunschkader");
    expect(consoleErrors).toEqual([]);
  });
});
```

Hinweis zum Testumfang: dieser Test prüft die **funktionale** Korrektheit unter Reduced-Motion (richtiger
End-Tab, keine Konsolenfehler durch falsch verdrahtete `motion`-Props), nicht ob `x`/`transform` tatsächlich
visuell unbewegt bleibt — Letzteres ist laut Spec/`CLAUDE.md` genau der Fall, den automatisierte Tests
zuverlässig nicht abdecken (siehe Task 6, manueller Smoke-Test).

- [ ] **Step 11: Neuen Test laufen lassen**

Run: `npm run test:e2e -- TabSwitchReducedMotion`
Expected: 2 Tests PASS.

- [ ] **Step 12: Typecheck + vollen Vitest-Lauf**

Run: `npm run typecheck && npm run test`
Expected: beides grün (keine Regressionen in `derive.test.ts` etc.).

- [ ] **Step 13: Commit**

```bash
git add frontend/src/App.tsx frontend/tests-e2e/TabSwitchReducedMotion.spec.ts
git commit -m "feat(frontend): AnimatePresence-Tab-Wechsel fuer 8 Tabs + Reduced-Motion-Wrapper"
```

---

### Task 3: Wunschkader — sauberer Exit via Phasen-State + CSS-Grid-Stack

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests-e2e/WunschkaderStatePersistsAcrossTabSwitch.spec.ts` (neu)

**Interfaces:**
- Consumes: `fadeVariants` aus `motionVariants.ts` (Task 1), `AnimatePresence`/`motion`-Block aus Task 2.
- Produces: `WunschkaderPhase` type (`"active" | "exiting" | "hidden"`) — nur intern in `App.tsx` genutzt, kein
  Export nötig.

- [ ] **Step 1: `WunschkaderPhase`-Type + State**

Nach dem `TabTransition`-Type (Task 2, Step 2):

```tsx
type WunschkaderPhase = "active" | "exiting" | "hidden";
const WUNSCHKADER_EXIT_FALLBACK_MS = 200;
```

In `App()`, nach dem `tabTransition`-State:

```tsx
const [wunschkaderPhase, setWunschkaderPhase] = useState<WunschkaderPhase>(
  activeTab === "wunschkader" ? "active" : "hidden"
);

useEffect(() => {
  setWunschkaderPhase((prev) => {
    if (activeTab === "wunschkader") return "active";
    return prev === "hidden" ? "hidden" : "exiting";
  });
}, [activeTab]);

// Fallback, falls onAnimationComplete durch schnelles wiederholtes
// Tab-Wechseln unterbrochen wird und nicht zuverlaessig einmalig feuert
// (siehe Spec, Abschnitt Fehlerbehandlung) - idempotent, setzt nur das,
// was der Callback ohnehin setzen wuerde.
useEffect(() => {
  if (wunschkaderPhase !== "exiting") return;
  const timeoutId = window.setTimeout(() => {
    setWunschkaderPhase((prev) => (prev === "exiting" ? "hidden" : prev));
  }, WUNSCHKADER_EXIT_FALLBACK_MS);
  return () => window.clearTimeout(timeoutId);
}, [wunschkaderPhase]);
```

- [ ] **Step 2: Wunschkader-Block + AnimatePresence-Block in einen Grid-Stack packen**

Ersetze den Wunschkader-Block aus Task 2 UND den direkt danebenstehenden `{activeTab !== "wunschkader" && (...)}`-Block gemeinsam durch:

```tsx
<div className="grid">
  {wunschkaderPhase !== "hidden" && data && data.players && wunschkader && (
    <motion.div
      style={{ gridArea: "1 / 1" }}
      variants={fadeVariants}
      initial="initial"
      animate={wunschkaderPhase === "active" ? "animate" : "exit"}
      onAnimationComplete={() => {
        setWunschkaderPhase((prev) => (prev === "exiting" ? "hidden" : prev));
      }}
    >
      <WunschkaderTab data={data} wunschkader={wunschkader} onSaved={(targets) => setWunschkader({ targets })} />
    </motion.div>
  )}

  <AnimatePresence mode="wait">
    {(() => {
        /* ... IIFE aus Task 2, Step 8, PLUS ein neuer Fruehausstieg fuer "wunschkader" (siehe Begruendung unten) ... */
        if (activeTab === "wunschkader") return null;
        let content: JSX.Element | null = null;
        if (activeTab === "dashboard" && data && data.players && wunschkader) {
          content = <DashboardTab data={data} wunschkader={wunschkader} transfermarktRows={transfermarktRows} now={now} />;
        } else if (activeTab === "spekulation" && data && data.players) {
          content = (
            <SpekulationTab
              rows={spekulationRows}
              now={now}
              mlMetrics={data.ml_metrics}
              mlMetrics3d={data.ml_metrics_3d ?? null}
              bidHistory={data.bid_premium_history ?? []}
              positionNeed={data.position_need ?? {}}
            />
          );
        } else if (activeTab === "team" && data && data.players && wunschkader) {
          content = <EigenesTeamTab data={data} wunschkader={wunschkader} />;
        } else if (activeTab === "alle-spieler" && data && data.players) {
          content = <AlleSpielerTab data={data} />;
        } else if (activeTab === "transfermarkt" && data && data.players) {
          content = <TransfermarktTab data={data} rows={transfermarktRows} now={now} />;
        } else if (activeTab === "liga" && data && data.players) {
          content = <LigaanalyseTab data={data} />;
        } else if (activeTab === "ml-genauigkeit" && data && data.players) {
          content = <MlGenauigkeitTab data={data} />;
        } else if (activeTab === "feedback") {
          content = <FeedbackTab now={now} />;
        }
        return (
          <motion.div
            key={activeTab}
            style={{ gridArea: "1 / 1" }}
            variants={tabTransition.kind === "fade" ? fadeVariants : slideFadeVariants(tabTransition.direction)}
            initial="initial"
            animate="animate"
            exit="exit"
          >
            {content}
          </motion.div>
        );
    })()}
  </AnimatePresence>
</div>
```

Wie in Task 2: `<AnimatePresence>` bleibt unconditionally gerendert. Anders als in Task 2 gibt die IIFE für
`activeTab === "wunschkader"` jetzt direkt `null` zurück, statt einen `motion.div` mit `content: null` zu
rendern (Task-2-Review-Fund, Minor: mit einem leeren `motion.div` würde `mode="wait"` beim Wechsel zu/von
Wunschkader trotzdem die volle Exit-Dauer auf ein unsichtbares Element warten — reine Verzögerung ohne
optischen Gegenwert. Gibt die IIFE stattdessen `null` zurück, hat `AnimatePresence` an dieser Grenze schlicht
nichts zum Animieren/Abwarten, der Wechsel zu/von Wunschkader bleibt so schnell wie Wunschkaders eigene
Grid-Stack-Animation es vorgibt.).

`gridArea: "1 / 1"` als Inline-`style` statt Tailwind-Arbitrary-Property (`[grid-area:1/1]`) — der Slash in
`1/1` würde sonst mit Tailwinds `/`-Opacity-Modifier-Syntax kollidieren können.

`onAnimationComplete` feuert auch nach dem **Enter** (`animate: "animate"`), deshalb der Guard `prev === "exiting"
? "hidden" : prev` — ein Enter darf die Phase nicht fälschlich auf `"hidden"` setzen.

- [ ] **Step 3: Neuen State-Erhalt-Regressionstest schreiben**

```ts
// frontend/tests-e2e/WunschkaderStatePersistsAcrossTabSwitch.spec.ts
import { test, expect } from "@playwright/test";
import { FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Wunschkader bleibt bei Tab-Wechsel gemountet", () => {
  test("Ungespeicherte Notiz und offenes Detail-Modal ueberleben Wegwechseln und Zurueckwechseln", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Wunschkader");

    const abwehrHeading = page.getByText(/^Abwehr ·/);
    const abwehrGrid = abwehrHeading.locator("xpath=following-sibling::div[1]");
    await abwehrGrid.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();

    const noteField = page.getByLabel("Notiz");
    await expect(noteField).toBeVisible();
    await noteField.fill("Zwischenstand-Test");

    // Wegwechseln, OHNE das Modal zu schliessen oder die Notiz zu speichern.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Dashboard", exact: true }).click();
    await expect(heading).toHaveText("Dashboard");

    // Zurueckwechseln - Wunschkader ist durchgehend gemountet, das
    // Detail-Modal muss deshalb OHNE erneuten Klick noch offen sein.
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    await page.getByRole("navigation").filter({ hasText: "Menü" }).getByRole("button", { name: "Wunschkader", exact: true }).click();
    await expect(heading).toHaveText("Wunschkader");

    await expect(page.getByLabel("Notiz")).toHaveValue("Zwischenstand-Test");
  });
});
```

- [ ] **Step 4: Test laufen lassen**

Run: `npm run test:e2e -- WunschkaderStatePersistsAcrossTabSwitch`
Expected: PASS.

- [ ] **Step 5: Mutation-Check**

Temporär den Wunschkader-Guard in Step 2 von `wunschkaderPhase !== "hidden"` auf `activeTab === "wunschkader"`
ändern (simuliert ein versehentliches Unmounten beim Wegwechseln).
Run: `npm run test:e2e -- WunschkaderStatePersistsAcrossTabSwitch`
Expected: FAIL (Notiz-Feld nicht mehr vorhanden, da `WunschkaderTab` beim Wegwechseln unmounted wurde).
Danach die Änderung zurücknehmen (`wunschkaderPhase !== "hidden"` wiederherstellen) und den Test erneut grün
laufen lassen.

- [ ] **Step 6: Bestehende Wunschkader-/Swipe-Tests laufen lassen**

Run: `npm run test:e2e -- SwipeBlockedByModal TouchScrubVsSwipe WunschkaderStatePersistsAcrossTabSwitch`
Expected: alle PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/tests-e2e/WunschkaderStatePersistsAcrossTabSwitch.spec.ts
git commit -m "feat(frontend): Wunschkader-Exit ueber Phasen-State + CSS-Grid-Stack animiert"
```

---

### Task 4: Wunschkader-Kartenliste — `layoutId`, Stagger, animiertes Add/Remove

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`
- Test: `frontend/tests-ct/WunschkaderTabCardMotion.ct.tsx` (neu)

**Interfaces:**
- Consumes: `staggerContainerVariants`, `staggerItemVariants` aus `motionVariants.ts` (Task 1).

- [ ] **Step 1: Imports ergänzen**

In `frontend/src/components/WunschkaderTab.tsx`:

```tsx
import { AnimatePresence, motion } from "framer-motion";
import { staggerContainerVariants, staggerItemVariants } from "../lib/motionVariants";
```

- [ ] **Step 2: Positionsgruppen-Grid animieren**

Ersetze im `POSITIONS.map((position) => { ... })`-Block das innere Grid:

```tsx
<motion.div
  className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
  variants={staggerContainerVariants}
  initial="initial"
  animate="animate"
>
  <AnimatePresence>
    {targets.map((t) => {
      const computed = resolvedByPlayerId.get(t.player_id)!;
      return (
        <motion.div
          key={t._uid}
          layoutId={`wunschkader-${t._uid}`}
          variants={staggerItemVariants}
          initial="initial"
          animate="animate"
          exit="exit"
        >
          <TargetCard
            target={t}
            computed={computed}
            thresholds={thresholds}
            clubCount={computed.team_name ? clubCounts[computed.team_name] ?? 0 : 0}
            onSelect={() => setSelected(t)}
          />
        </motion.div>
      );
    })}
  </AnimatePresence>
  {canAdd && <EmptySlotCard onClick={() => setAddDialog({ presetPosition: position })} />}
</motion.div>
```

- [ ] **Step 3: Bank-Grid identisch animieren**

Ersetze im Bank-Block darunter dasselbe Muster (`bench.map` statt `targets.map`, `clubCount={0}`,
`EmptySlotCard onClick={() => setAddDialog({ presetPosition: null })}`):

```tsx
<motion.div
  className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4"
  variants={staggerContainerVariants}
  initial="initial"
  animate="animate"
>
  <AnimatePresence>
    {bench.map((t) => {
      const computed = resolvedByPlayerId.get(t.player_id)!;
      return (
        <motion.div
          key={t._uid}
          layoutId={`wunschkader-${t._uid}`}
          variants={staggerItemVariants}
          initial="initial"
          animate="animate"
          exit="exit"
        >
          <TargetCard target={t} computed={computed} thresholds={thresholds} clubCount={0} onSelect={() => setSelected(t)} />
        </motion.div>
      );
    })}
  </AnimatePresence>
  <EmptySlotCard onClick={() => setAddDialog({ presetPosition: null })} />
</motion.div>
```

Dasselbe `layoutId={`wunschkader-${t._uid}`}`-Schema in beiden Blöcken ist der Punkt: wechselt eine Karte
zwischen Bank und Positionsgruppe (bestehende Buttons, unverändert), erkennt Framer Motion dieselbe `layoutId`
in einem neuen Elternknoten und animiert die Positionsänderung automatisch.

- [ ] **Step 4: Neuen CT-Test schreiben**

```tsx
// frontend/tests-ct/WunschkaderTabCardMotion.ct.tsx
import { test, expect } from "@playwright/experimental-ct-react";
import WunschkaderTab from "../src/components/WunschkaderTab";
import { buildFixtureSnapshot, FIXTURE_PLAYERS } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("Wunschkader-Kartenliste mit Motion-Wrapper", () => {
  test("Klick auf eine Karte oeffnet weiterhin das Detail-Modal", async ({ mount }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await expect(component.getByLabel("Notiz")).toBeVisible();
  });

  test("Entfernen loescht die Karte weiterhin und schreibt korrekt nach Firestore", async ({ mount, page }) => {
    const targets = [{ player_id: FIXTURE_PLAYERS.target.player_id, role: "Starter" }];
    const component = await mount(
      <WunschkaderTab data={buildFixtureSnapshot()} wunschkader={{ targets }} onSaved={() => {}} />
    );

    await component.getByText(FIXTURE_PLAYERS.target.name, { exact: true }).click();
    await component.getByRole("button", { name: "Entfernen" }).click();

    await expect
      .poll(() => page.evaluate(() => (window as any).__ctFirestoreCalls?.length ?? 0))
      .toBe(1);
    await expect(component.getByText(FIXTURE_PLAYERS.target.name, { exact: true })).toHaveCount(0, { timeout: 1000 });
  });
});
```

Der erste Test ist der eigentliche Regressions-Fang für diesen Task: er stellt sicher, dass das Einpacken von
`TargetCard` in einen zusätzlichen `motion.div`-Wrapper (Step 2/3) den `onSelect`-Klick-Pfad nicht versehentlich
verliert — ein plausibler Fehler bei dieser Art JSX-Umbau. Die Motion-Optik selbst (Stagger-Timing,
`layoutId`-Reorder) ist wie in der Spec begründet nicht sinnvoll flackerfrei automatisiert testbar — dafür der
manuelle Smoke-Test in Task 6.

- [ ] **Step 5: Mutation-Check für den ersten Test**

Temporär in Step 2/3 `onSelect={() => setSelected(t)}` aus den `<TargetCard>`-Props entfernen.
Run: `npm run test:ct -- WunschkaderTabCardMotion`
Expected: FAIL ("Klick auf eine Karte..."-Test, da das Detail-Modal nicht mehr öffnet).
Danach `onSelect={() => setSelected(t)}` wiederherstellen und Test erneut grün laufen lassen.

- [ ] **Step 6: Bestehende WunschkaderTab-Tests laufen lassen**

Run: `npm run test:ct -- WunschkaderTab`
Expected: `WunschkaderTab.ct.tsx`, `WunschkaderTabAutoSave.ct.tsx`, `WunschkaderTabPlanungsmodus.ct.tsx`,
`WunschkaderTabCardMotion.ct.tsx` alle PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx frontend/tests-ct/WunschkaderTabCardMotion.ct.tsx
git commit -m "feat(frontend): Wunschkader-Kartenliste mit layoutId-Reorder und Stagger"
```

---

### Task 5: PlayerCompareModal + MobileTabMenu — Backdrop/Panel-Animation

**Files:**
- Modify: `frontend/src/components/PlayerCompareModal.tsx`
- Modify: `frontend/src/components/AlleSpielerTab.tsx`
- Modify: `frontend/src/components/EigenesTeamTab.tsx`
- Modify: `frontend/src/components/WunschkaderTab.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests-e2e/MobileMenuReducedMotion.spec.ts` (neu)

**Interfaces:**
- Consumes: `backdropVariants`, `panelVariants(from)` aus `motionVariants.ts` (Task 1).

- [ ] **Step 1: `PlayerCompareModal.tsx` — Backdrop/Panel zu `motion.div`**

Imports ergänzen:

```tsx
import { motion } from "framer-motion";
import { backdropVariants, panelVariants } from "../lib/motionVariants";
```

Die "Spieler nicht gefunden"-Fallback-Rückgabe:

```tsx
return (
  <motion.div
    variants={backdropVariants}
    initial="initial"
    animate="animate"
    exit="exit"
    className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4"
    onClick={onClose}
  >
    <motion.div
      variants={panelVariants("center")}
      initial="initial"
      animate="animate"
      exit="exit"
      onClick={(e) => e.stopPropagation()}
      className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
    >
      <p className="text-sm text-slate-500 dark:text-slate-400">Spieler nicht gefunden.</p>
    </motion.div>
  </motion.div>
);
```

Der Haupt-Return (gleiches Muster, `className`/Inhalt unverändert, nur `div` → `motion.div` mit denselben
`variants`/`initial`/`animate`/`exit`-Props):

```tsx
return (
  <motion.div
    variants={backdropVariants}
    initial="initial"
    animate="animate"
    exit="exit"
    className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4"
    onClick={onClose}
  >
    <motion.div
      variants={panelVariants("center")}
      initial="initial"
      animate="animate"
      exit="exit"
      onClick={(e) => e.stopPropagation()}
      className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
    >
      {/* ... restlicher Inhalt unveraendert ... */}
    </motion.div>
  </motion.div>
);
```

- [ ] **Step 2: 4 Call-Sites in `AnimatePresence` wrappen**

In `frontend/src/components/AlleSpielerTab.tsx` (~Zeile 448):

```tsx
<AnimatePresence>
  {compareWith && (
    <PlayerCompareModal
      playerIdA={row.player_id}
      playerIdB={compareWith}
      players={players}
      calibration={calibration}
      thresholds={thresholds}
      onClose={() => setCompareWith(null)}
    />
  )}
</AnimatePresence>
```

(Import `AnimatePresence` aus `"framer-motion"` ergänzen.)

In `frontend/src/components/EigenesTeamTab.tsx`: **beide** Vorkommen (`PlayerDetailModal`- und
`WatchlistDetailModal`-Funktion, ~Zeile 390 und ~461) identisch mit `<AnimatePresence>{compareWith && (...)}
</AnimatePresence>` wrappen. Import `AnimatePresence` einmal am Dateikopf ergänzen.

In `frontend/src/components/WunschkaderTab.tsx` (~Zeile 866, im `DetailModal`):

```tsx
<AnimatePresence>
  {compareWith && (
    <PlayerCompareModal
      playerIdA={target.player_id}
      playerIdB={compareWith.player_id}
      players={players}
      calibration={calibration}
      thresholds={thresholds}
      onSelectSide={(playerId) => {
        if (playerId !== target.player_id) onReplace(playerId);
        setCompareWith(null);
      }}
      onClose={() => setCompareWith(null)}
    />
  )}
</AnimatePresence>
```

(`AnimatePresence` ist in dieser Datei bereits seit Task 4 aus `"framer-motion"` importiert — kein zusätzlicher Import nötig.)

- [ ] **Step 3: `MobileTabMenu` (in `App.tsx`) — Backdrop/Panel zu `motion.div`**

```tsx
function MobileTabMenu({ activeTab, onSelect, onClose }: { /* unveraendert */ }) {
  useModalOpenTracking();
  useEffect(() => { /* unveraendert */ }, [onClose]);

  return (
    <motion.div
      variants={backdropVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className="fixed inset-0 z-20 bg-slate-950/50 sm:hidden"
      onClick={onClose}
    >
      <motion.nav
        variants={panelVariants("left")}
        initial="initial"
        animate="animate"
        exit="exit"
        onClick={(e) => e.stopPropagation()}
        className="flex h-full w-72 max-w-[80vw] flex-col gap-1 overflow-y-auto bg-white p-3 shadow-xl dark:bg-slate-950"
      >
        {/* ... restlicher Inhalt unveraendert ... */}
      </motion.nav>
    </motion.div>
  );
}
```

Import in `App.tsx` ergänzen: `backdropVariants`, `panelVariants` zum bestehenden `motionVariants`-Import
(Task 2/3) dazunehmen.

- [ ] **Step 4: Call-Site von `MobileTabMenu` in `AnimatePresence` wrappen**

```tsx
<AnimatePresence>
  {mobileMenuOpen && (
    <MobileTabMenu
      activeTab={activeTab}
      onSelect={(key) => {
        setTabTransition({ kind: "fade" });
        setActiveTab(key);
      }}
      onClose={() => setMobileMenuOpen(false)}
    />
  )}
</AnimatePresence>
```

- [ ] **Step 5: Bestehende Modal-Tests laufen lassen**

Run: `npm run test:ct -- PlayerCompareModal`
Run: `npm run test:e2e -- SwipeBlockedByModal`
Expected: beide PASS unverändert. (Die "Bug F"-E2E-Test-Assertion `await expect(closeButton).toHaveCount(0)`
wartet jetzt zusätzlich die ~130ms Exit-Animation ab, bevor der Button aus dem DOM verschwindet — Playwrights
`expect()` pollt automatisch bis zum Timeout, das ist kein Testumbau nötig, nur etwas mehr Wartezeit.)

- [ ] **Step 6: Neuen Reduced-Motion-Test für das Mobile-Menü schreiben**

```ts
// frontend/tests-e2e/MobileMenuReducedMotion.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Mobile-Menue bleibt unter prefers-reduced-motion funktional", () => {
  test("Oeffnen, Tab waehlen, Menue schliesst sich selbst - keine Konsolenfehler", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await expect(mobileNav).toBeVisible();

    await mobileNav.getByRole("button", { name: "Ligaanalyse", exact: true }).click();
    await expect(mobileNav).toHaveCount(0);

    const heading = page.getByRole("heading", { level: 2 });
    await expect(heading).toHaveText("Ligaanalyse");
    expect(consoleErrors).toEqual([]);
  });

  test("Escape schliesst das Menue", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await page.getByRole("button", { name: "Menü öffnen" }).click();
    const mobileNav = page.getByRole("navigation").filter({ hasText: "Menü" });
    await expect(mobileNav).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(mobileNav).toHaveCount(0);
  });
});
```

- [ ] **Step 7: Neuen Test laufen lassen**

Run: `npm run test:e2e -- MobileMenuReducedMotion`
Expected: 2 Tests PASS.

- [ ] **Step 8: Typecheck + voller Test-Lauf**

Run: `npm run typecheck && npm run test && npm run test:ct && npm run test:e2e`
Expected: alles grün.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/PlayerCompareModal.tsx frontend/src/components/AlleSpielerTab.tsx frontend/src/components/EigenesTeamTab.tsx frontend/src/components/WunschkaderTab.tsx frontend/src/App.tsx frontend/tests-e2e/MobileMenuReducedMotion.spec.ts
git commit -m "feat(frontend): PlayerCompareModal + MobileTabMenu mit Backdrop/Panel-Animation"
```

---

### Task 6: Vollständige Verifikation + manueller Browser-Smoke-Test

**Files:** keine Code-Änderungen erwartet — reine Verifikation. Falls dabei etwas auffällt: zurück zum
jeweiligen Task, dort fixen, nicht hier improvisieren.

- [ ] **Step 1: Vollen Testlauf ausführen**

Run: `npm run typecheck && npm run test && npm run test:ct && npm run test:e2e`
Expected: alles grün, keine Regressionen ggü. dem Stand vor diesem Plan.

- [ ] **Step 2: Dev-Server starten und Build prüfen**

Run: `npm run build`
Expected: Build erfolgreich, keine TypeScript-/Bundling-Fehler durch `framer-motion`.

- [ ] **Step 3: Manueller Live-Smoke-Test im Browser**

Per `run`-Skill oder `npm run dev` in der Worktree, im echten Browser (Desktop- und mobile Emulation)
durchklicken:

1. Tab-Wechsel per Klick (Desktop-Navleiste) — Fade sichtbar, kein Sprung/Flackern.
2. Tab-Wechsel per Swipe (mobile Emulation) — Slide+Fade in Wisch-Richtung.
3. Zu Wunschkader wechseln und wieder weg — Enter-Fade beim Reingehen, Exit-Fade beim Rausgehen (Grid-Stack
   darf keinen Scroll-Höhen-Sprung verursachen).
4. `PlayerCompareModal` öffnen/schließen (z.B. über Alle-Spieler-Tab) — Backdrop-Fade + Panel-Scale.
5. Mobile-Burger-Menü öffnen/schließen — Backdrop-Fade + Drawer-Slide-von-links.
6. Wunschkader: ein Ziel von Bank in eine Positionsgruppe verschieben (bestehender Button) — Karte animiert
   sichtbar an die neue Position, kein Sprung.
7. In den Betriebssystem-/Browser-Einstellungen "Reduce Motion" aktivieren, Schritte 1–5 wiederholen — Inhalte
   wechseln weiterhin korrekt, aber ohne Slide/Scale (nur Fades, wie von Framer Motions `reducedMotion="user"`
   spezifiziert: Transform-/Layout-Animationen deaktiviert, Opacity bleibt).

Nur nach diesem Schritt darf die Umsetzung als fertig gemeldet werden — motion-spezifische Bugs sind laut
`CLAUDE.md` genau der Fall, den die vorherigen automatisierten Tests zuverlässig nicht finden.

- [ ] **Step 4: `HANDOFF.md` aktualisieren**

Falls dieser Plan der letzte offene Punkt aus dem Chat war: kurzen Eintrag zum Motion-Pilot-Abschluss +
Verweis auf die zurückgestellte Folge-Arbeit (Drag-and-Drop-Spec, Phase-2-Rollout für Transfermarkt/Alle-Spieler/
Sortier-Tabellen) ergänzen, nach demselben Muster wie bestehende `HANDOFF.md`-Einträge.

- [ ] **Step 5: Commit (falls `HANDOFF.md` geändert wurde)**

```bash
git add HANDOFF.md
git commit -m "HANDOFF.md: Frontend-Motion-Pilot abgeschlossen, Folge-Arbeit vermerkt"
```
