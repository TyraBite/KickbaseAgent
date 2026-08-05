# Frontend-Motion-Pilot (Tab-Wechsel, Modals, Wunschkader) — Design

## Kontext

Nutzerwunsch (Chat, 2026-08-05): FE-Audit mit dem `ui-ux-pro-max`-Skill durchführen und ein Redesign planen, das
`framer-motion` (installiert als Claude-Code-Skill `motion-framer`, npm-Paket `framer-motion`) sinnvoll einsetzt.

### Audit-Befund (gegen den echten Code verifiziert, nicht angenommen)

- Motion im Frontend aktuell: **keine.** Nur Tailwind-`transition-colors`/`transition-transform` (Header
  Hide-on-Scroll in `App.tsx`, Hover-Farbwechsel). Kein `prefers-reduced-motion`-Handling irgendwo im Code.
- Tab-Wechsel (`App.tsx:391-444`): alle datenabhängigen Tabs bleiben permanent im DOM, nur per
  `className={activeTab === X ? "" : "hidden"}` versteckt — kein Enter/Exit.
- `MobileTabMenu` (`App.tsx:147-218`) und `PlayerCompareModal` (`components/PlayerCompareModal.tsx`): beide schon
  heute conditional gerendert (`{mobileMenuOpen && <MobileTabMenu/>}` bzw. Modal-State im Parent), erscheinen/
  verschwinden aber instant, kein Fade/Slide.
- `WunschkaderTab`-Kartenlisten (`components/WunschkaderTab.tsx:498-538`): `grid-cols-[repeat(auto-fill,...)]`,
  Karten geschlüsselt über `t._uid` (stabile numerische Id pro Zielspieler-Eintrag). Kein Stagger, keine
  Reorder-Animation beim Wechsel zwischen Positionsgruppe und Bank.
- `useSwipeTabs` (`App.tsx:109-139`): reine `touchstart`/`touchend`-Schwellenwert-Erkennung, kein Live-Feedback
  während des Wischens, kein `data-swipe-ignore`-Konflikt mit dieser Änderung (bleibt unverändert, siehe unten).
- `ui-ux-pro-max --design-system` ohne `--domain`-Vorgabe traf für die Query "fantasy sports decision-support
  dashboard analytics dark mode data-dense" daneben (schlug "FAQ/Documentation Landing"-Pattern und
  "Exaggerated Minimalism"-Stil vor — beides passt nicht zu einem dichten Analytics-Dashboard). Gezielte
  Nachfrage mit `--domain style`/`--domain product` traf danach **Data-Dense Dashboard** (Style) und
  **Analytics Dashboard** (Produkt-Typ) — beide bestätigen die bestehende Ausrichtung (kompakte Paddings,
  Grid-Layout, Hover-Tooltips), ohne dass ein visueller Umbau (Farben/Typografie) nötig ist. Dieser Spec ändert
  deshalb **nur Motion**, keine Farben/Layout/Typografie.
- `--domain ux` bestätigte `prefers-reduced-motion` als **High-Severity**-Pflichtregel (aktuell 0% Abdeckung) und
  44px-Touch-Ziele (bereits eingehalten, keine Änderung nötig).

### Im Brainstorming (Chat, 2026-08-05) geklärte Eckpunkte

- **Scope: Pilot, nicht Vollausrollung.** Tab-Wechsel-Infrastruktur (App-weit, da ein gemeinsamer Render-Block),
  beide Overlay-Modals, plus Wunschkader-Kartenliste. Transfermarkt-/Alle-Spieler-Kartenlisten und
  Sortier-Tabellen-Reorder folgen erst nach Live-Check dieses Pilots (siehe „Nicht-Ziele").
- **Motion-Stärke: Standard** (nicht nur „subtil") — Spring-Physics-Feedback bei Swipe-Ergebnis und Stagger beim
  Laden von Kartenlisten sind explizit gewünscht, nicht nur Fades.
- **Wunschkader bleibt permanent gemountet**, alle anderen 8 Tabs wechseln auf echtes Un-/Mounten. Grund: Autosave
  hält den Stand ohnehin persistent — ein Unmount würde nur im **Simulationsmodus**
  (`docs/superpowers/specs/2026-08-03-wunschkader-simulationsmodus-design.md`) unsaved State verlieren. Kein neues
  Risiko gegenüber heute: heute sind ohnehin alle Tabs durchgehend gemountet, dieser Spec ändert daran für
  Wunschkader nichts.
- **Wunschkader-Exit wird sauber animiert** (nicht nur der Enter) — Overlap-Konstruktion über CSS-Grid-Stacking
  statt rohem `position:absolute`, um Scroll-Höhen-Sprünge zu vermeiden (Details unten).
- **Klick (Desktop-Navleiste, Mobile-Menü) → immer nur Fade**, kein Richtungs-Slide. Swipe → Slide+Fade mit
  Richtung aus dem Geste-Delta. Begründung: ein Klick hat keine physische Richtung, die simuliert werden sollte;
  `useSwipeTabs`s Erkennung selbst bleibt unverändert (kein Rewrite auf Echtzeit-Drag — zu hohes
  Regressions-Risiko für einen bereits getesteten, funktionierenden Mechanismus).
- **MobileTabMenu ist Teil des Pilots** (nicht zurückgestellt) — gleiches Backdrop+Panel-Pattern wie
  `PlayerCompareModal`, kaum Mehraufwand, und es ist die auf dem Handy am häufigsten gesehene Overlay-Interaktion.
- **Drag-and-Drop für Wunschkader-Karten ist explizit NICHT Teil dieses Specs.** User-Idee (Karten per Drag
  zwischen Bank/Positionsgruppe verschieben, mit Cap-/Positions-Restriktionen) — eigenständiges
  Interaktionsmodell mit eigenen Randfällen (Touch-Konflikt mit `useSwipeTabs`, Accessibility-Fallback für die
  bereits bestehenden Icon-Buttons, Drop-Validität), verdient einen eigenen Spec+Plan **nach** diesem Pilot,
  aufbauend auf den hier eingeführten `layoutId`-Karten. Nicht von selbst anfangen.

## Nicht-Ziele

- Keine Farb-/Typografie-/Layout-Änderungen — Audit bestätigt die bestehende Data-Dense-Dashboard-Ausrichtung.
- Kein Umbau von `useSwipeTabs` auf Echtzeit-Drag-Gesten — Schwellenwert-Erkennung nach Release bleibt.
- Keine Motion für Transfermarkt-/Alle-Spieler-Kartenlisten und keine Row-Reorder-Animation in
  `components/table.tsx`-Sortier-Tabellen — Phase 2, nach Live-Check dieses Pilots.
- Kein Drag-and-Drop für Wunschkader-Karten (siehe oben) — eigener Folge-Spec.
- Keine Änderung an `MlGenauigkeitTab`-Chart-Interna (Punkte-Auswahl/Tooltip-Positionierung) — unabhängiges Thema.

## Architektur

### Neue Datei: `frontend/src/lib/motionVariants.ts`

Zentrale, wiederverwendbare `framer-motion`-Variants — analog zum bestehenden Prinzip „Ableitung an einer Stelle,
nicht kopiert" aus `derive.ts`. Jede Komponente importiert von hier statt eigene Duration/Easing-Werte zu
erfinden:

- `fadeVariants` — reiner Opacity-Fade (150–200ms), für Klick-ausgelöste Tab-Wechsel.
- `slideFadeVariants(direction: 1 | -1)` — Slide+Fade (200–250ms, `ease: "easeOut"` beim Enter, etwas schneller
  beim Exit — „exit schneller als enter" ist eine anerkannte Motion-Faustregel, vermeidet, dass die UI beim
  Verlassen eines Zustands träge wirkt), für Swipe-ausgelöste Tab-Wechsel.
- `backdropVariants` / `panelVariants` — für beide Overlay-Modals (Backdrop-Fade + Panel-Slide/Scale).
- `staggerContainerVariants` / `staggerItemVariants` — für die Wunschkader-Kartenliste (Container `staggerChildren:
  0.05`).

### Reduced-Motion

`<MotionConfig reducedMotion="user">` einmal um den Root-Return in `App.tsx` — deckt `prefers-reduced-motion` für
alle Kind-Komponenten automatisch ab (Framer-Motion-Bordmittel), kein manuelles Media-Query-Handling pro
Komponente.

### Tab-Wechsel (`App.tsx`)

Neuer State neben `activeTab`:

```ts
type TabTransition = { kind: "fade" } | { kind: "slide"; direction: 1 | -1 };
const [tabTransition, setTabTransition] = useState<TabTransition>({ kind: "fade" });
```

- Klick auf Navleiste/Mobile-Menü-Eintrag: `setTabTransition({ kind: "fade" })` vor `setActiveTab(key)`.
- `useSwipeTabs`s `onTouchEnd`: `setTabTransition({ kind: "slide", direction: dx < 0 ? 1 : -1 })` vor
  `setActiveTab(next)` (Richtung aus dem bestehenden `dx`-Vorzeichen, keine neue Geste-Logik).

Die 8 Nicht-Wunschkader-Tabs wandern in `<AnimatePresence mode="wait">`, gekeyt auf `activeTab` — nur der aktive
Tab ist im DOM. Die aktuell verstreuten `{loadState === "ready" && data && data.players && (<div
className={activeTab === X ? "" : "hidden"}>...)}`-Blöcke werden zu einem `switch`/Lookup, der die passende
Tab-Komponente rendert, gewrappt in `motion.div` mit `variants={tabTransition.kind === "fade" ? fadeVariants :
slideFadeVariants(tabTransition.direction)}`.

Wunschkader bleibt als eigener, permanent gemounteter `motion.div`-Block erhalten. Beide Blöcke liegen auf
`grid-area: 1 / 1` in einem gemeinsamen `display: grid`-Wrapper — die Grid-Zelle sizt sich automatisch auf den
höheren der beiden Blöcke, solange beide sichtbar sind (löst das Scroll-Höhen-Problem eines rohen
`position:absolute`-Overlaps ohne manuelles Höhen-Capturing).

Wunschkader-Sichtbarkeit läuft über einen kleinen Phasen-State statt eines einfachen Booleans:

```ts
type WunschkaderPhase = "active" | "exiting" | "hidden";
```

- Wechsel **zu** Wunschkader: Phase → `"active"`, `motion.div` animiert Enter (Fade+Slide aus
  `panelVariants`-artigen Werten).
- Wechsel **weg von** Wunschkader: Phase → `"exiting"` (bleibt im Grid-Stack, animiert Opacity → 0), nach
  `onAnimationComplete` → Phase `"hidden"` (verlässt den Grid-Stack — `display: none` oder Entfernen aus dem
  Grid-Layout —, damit es die Klick-/Scroll-Fläche des neuen Tabs danach nicht blockiert).
- Der andere Tab (im `AnimatePresence`-Block) startet seinen Enter parallel zum Exit von Wunschkader — beide
  überlappen sich für die Dauer der Exit-Animation (~200ms) im selben Grid-Slot.

### Modals (`PlayerCompareModal`, `MobileTabMenu`)

Beide bereits conditional gerendert (`{mobileMenuOpen && ...}` bzw. State im Parent) — kein Sonderfall wie bei
Wunschkader nötig. Bedingter Render wird zu `<AnimatePresence>{condition && <motion.div ...>}</AnimatePresence>`,
echtes Unmount. `backdropVariants` für den Hintergrund, `panelVariants` für das Panel (`MobileTabMenu`: Slide von
links, passend zum Drawer-von-links-Verhalten; `PlayerCompareModal`: Scale+Fade, zentriert).

### Wunschkader-Kartenliste (`WunschkaderTab.tsx`)

- Jede Karte bekommt `layoutId={`wunschkader-${t._uid}`}` zusätzlich zu `key={t._uid}` — Framer Motion animiert
  automatisch die Positionsänderung, wenn eine Karte zwischen Positionsgruppe und Bank wechselt (bestehende
  Buttons aus Feedback `627985f3`, unverändert in ihrer Funktion).
- Beim ersten Tab-Eintritt (Wunschkader-Phase wird `"active"`): Grid-Wrapper bekommt
  `staggerContainerVariants`, jede Karte `staggerItemVariants` — gestaffelter Fade-In (~40–60ms Versatz pro
  Karte).
- Hinzufügen/Entfernen einer Karte: `AnimatePresence` pro Karte (Fade-Out beim Entfernen statt sofortigem
  Verschwinden).

## Fehlerbehandlung

Kein neuer Fehlerpfad — Motion ist rein präsentational, keine neuen Firestore-Reads/-Writes, kein neuer
Netzwerk-Zugriff. Einzige neue Fehlerquelle: `onAnimationComplete`-Callback für den Wunschkader-Exit-Phasenwechsel
darf nicht hängen bleiben, falls eine Animation durch schnelles wiederholtes Tab-Wechseln unterbrochen wird —
Framer Motion feuert `onAnimationComplete` in diesem Fall nicht zuverlässig einmalig. Absicherung: Phase-Wechsel
zusätzlich über einen `useEffect`, der bei jedem `activeTab`-Wechsel weg von `"wunschkader"` einen Timeout mit der
bekannten Exit-Dauer als Fallback setzt (idempotent, setzt nur, was der Callback ohnehin setzen würde).

## Tests

Nach `CLAUDE.md`-Testmatrix:

- **Playwright CT** (`frontend/tests-ct/`): bestehende Tab-Wechsel- und Wunschkader-Assertions müssen mit
  `AnimatePresence`/Grid-Stack weiter grün sein. Neuer Test: Wunschkader-Targets bleiben erhalten, wenn zu einem
  anderen Tab und zurück gewechselt wird (Kern der Restrukturierung — verdient einen eigenen, expliziten Test statt
  sich auf zufälliges Miterfassen durch bestehende Tests zu verlassen).
- **Reduced-Motion-Test**: `page.emulateMedia({ reducedMotion: "reduce" })` → keine sichtbaren
  Transform-Übergänge (Assertion auf `transform`/`opacity`-Endzustand direkt nach dem State-Wechsel, ohne auf eine
  Transition-Dauer warten zu müssen).
- Motion-Timing/Optik selbst ist laut `CLAUDE.md` genau der Fall, den Unit-/Component-Tests zuverlässig nicht
  finden — vor Abschluss ein echter Browser-Smoke-Test (Tab-Wechsel per Klick UND Swipe, beide Modals,
  Wunschkader-Reorder, Reduced-Motion aktiv/inaktiv) im laufenden Dev-Server.
- Mutation-Check für den neuen State-Erhalt-Test (Fix temporär zurücknehmen → Test muss rot werden).

## Rollout

Kein Backend-/Firestore-Bezug, reine Frontend-Änderung — normaler PR-Workflow (`gh pr create` +
`gh pr merge --auto --squash`), kein erzwungener Heavy-Lauf nötig. Neue Dependency `framer-motion` zu
`frontend/package.json` (Caret-Range, passend zur bestehenden Konvention dort — die Python-Exact-Pin-Regel aus
`CLAUDE.md` gilt für `requirements.txt`, nicht für `package.json`).

## Offene Folge-Arbeit (nicht Teil dieses Specs)

- Drag-and-Drop für Wunschkader-Karten (Bank ↔ Positionsgruppe, mit den 3 Restriktionen: 11-Feldspieler-Cap,
  Positionsgruppen-Cap via `canAddStarter()`, Positions-Match) — eigener Spec, User-Idee vom 2026-08-05.
- Transfermarkt-/Alle-Spieler-Kartenlisten-Stagger, Sortier-Tabellen-Reorder-Animation — Phase 2 nach Live-Check.
