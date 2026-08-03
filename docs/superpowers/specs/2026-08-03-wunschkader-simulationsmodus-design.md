# Wunschkader-Simulationsmodus — Design

## Kontext

User-Feedback (`feedback/current` in Firestore, Item `ac98d1d3`, erstellt 2026-08-03T07:57:48.109Z, `type: "feature"`):
"Wunschlader: Simulationsmodul, autosave aus. Und Änderungen können ganz am Ende Verworfen werden oder gespeichert
werden."

Das steht auf den ersten Blick im Widerspruch zum in der vorherigen Session fertiggestellten Auto-Save-Feature
(`WunschkaderTab.tsx`, Button komplett entfernt, jede Aktion speichert sofort bzw. debounced nach Firestore). Im
Brainstorming (Chat, 2026-08-03) geklärt: kein Rückbau, sondern ein **zuschaltbarer Zusatz-Modus** — Auto-Save bleibt
der Standard für die normale Nutzung, ein neuer expliziter "Planungsmodus" erlaubt Was-wäre-wenn-Sessions mit
Verwerfen/Übernehmen am Ende.

Bestehender Mechanismus (verifiziert gegen den aktuellen Code, `WunschkaderTab.tsx`):

- Jede Mutationsfunktion (`addTarget`, `replaceTarget`, `updateNote`, Bank/Startelf-Toggle, Entfernen) setzt
  `pendingSaveKind.current` auf `"immediate"` oder `"debounced"` (nur `updateNote` für den Notiz-Freitext) **vor**
  dem `setEditState(...)`-Aufruf.
- Ein `useEffect` (Zeile ~345) reagiert auf `editState`-Änderungen: `kind === "immediate"` → `saveTargets(editState)`
  sofort; `kind === "debounced"` → `debouncedSaveTargets()` (nutzt `latestEditStateRef.current` bei Fristablauf,
  stale-Save-Fix aus der letzten Session).
- `saveTargets()` (Zeile ~287) ist die einzige Stelle, die tatsächlich nach Firestore schreibt
  (`setDoc(doc(db,"wunschkader","current"), {targets, updated_at}, {merge:true})`) und danach `onSaved(targets)`
  aufruft (App-Level-Callback, hält `EigenesTeamTab`s Live-Sync aktuell, siehe
  `docs/superpowers/specs/2026-08-01-eigenes-team-wunschkader-live-sync-design.md`).
- Alle Tabs bleiben laut `App.tsx` durchgehend gemountet (nur per CSS-Klasse `hidden` versteckt, kein Unmount beim
  Tab-Wechsel) — lokaler Component-State in `WunschkaderTab` überlebt Tab-Wechsel deshalb bereits heute ohne
  zusätzliches State-Lifting.

Im Brainstorming entschiedene Eckpunkte:

- Modus ist ein reiner **Zusatz**, kein Ersatz für Auto-Save — Normalnutzung bleibt exakt wie heute.
- Alles, was heute Auto-Save auslöst, wird im Modus gesammelt statt sofort gespeichert — **inklusive** Notiz-Text
  (nicht nur Kader-Struktur).
- Verlassen der Seite (Reload/Schließen) mit ungespeicherter Simulation: Browser-`beforeunload`-Warnung. Tab-Wechsel
  innerhalb der App: unproblematisch, da ohnehin kein Unmount stattfindet.
- Kein Diff/Änderungs-Übersicht vor Speichern/Verwerfen — nur zwei Buttons + ein einfacher Zähler ("N ungespeicherte
  Änderungen").

## Nicht-Ziele

- Kein Rückbau von Auto-Save für die Normalnutzung.
- Keine Persistenz der Simulation über einen echten Reload hinweg (kein `localStorage`, kein Firestore-Draft-Doc) —
  nur In-Memory React-State, geschützt durch die `beforeunload`-Warnung. Wer trotzdem neu lädt, verliert die
  Simulation bewusst (User-Entscheidung im Brainstorming).
- Keine Änderungs-/Diff-Anzeige vor dem Commit.
- Keine Mehrfach-Simulationen/Branches (kein "Szenario A vs. Szenario B") — genau eine aktive Simulation zur Zeit,
  wie eine feature-branch-lose Arbeitskopie.
- `EigenesTeamTab` zeigt während der Simulation bewusst weiterhin den zuletzt gespeicherten Stand, nicht die
  simulierten Änderungen — ergibt sich automatisch daraus, dass `onSaved()`/Firestore-Write erst beim Übernehmen
  passiert, keine gesonderte Logik nötig.

## Architektur

**Neuer State** (in `WunschkaderTab`, dort wo `editState`/`saveStatus` bereits leben):

```ts
const [simulationMode, setSimulationMode] = useState(false);
const simulationModeRef = useRef(false);
simulationModeRef.current = simulationMode;

const [baseline, setBaseline] = useState<EditTarget[] | null>(null);
const [pendingChangeCount, setPendingChangeCount] = useState(0);
```

`simulationModeRef` existiert aus demselben Grund wie das bestehende `latestEditStateRef`: ein bereits laufender
Debounce-Timer (Notiz-Save) darf beim Fristablauf den *aktuellen* Modus sehen, nicht den zum Zeitpunkt des
Timer-Starts eingefangenen.

**Guard in `saveTargets()`** (ganz am Anfang der Funktion, vor der bestehenden `player_id`-Migrations-Absicherung):

```ts
if (simulationModeRef.current) return;
```

Das genügt, um **beide** Auslösewege (`saveTargets(editState)` direkt aus dem `useEffect`, und
`debouncedSaveTargets()` → `saveTargets(latestEditStateRef.current)` nach Fristablauf) abzudecken, ohne die
bestehende Effect-/Mutation-Logik überhaupt anzufassen. Kein Firestore-Write, kein `onSaved()`-Aufruf, solange der
Modus aktiv ist — die Mutationsfunktionen selbst (`addTarget` etc.) bleiben unverändert, sie ändern weiterhin nur
`editState`.

**Zähler**: jede der bestehenden Mutationsfunktionen bekommt eine Zeile ergänzt (`if (simulationModeRef.current)
setPendingChangeCount((n) => n + 1);`), direkt neben dem bestehenden `pendingSaveKind.current = ...`. Ein simpler
Zähler statt Diff, wie entschieden — zählt Aktionen, nicht Netto-Änderungen (ein Hinzufügen+Entfernen desselben
Ziels zeigt "2", nicht "0"). Bewusst so belassen, kosmetische Ungenauigkeit ohne Funktionsfolgen.

**Modus betreten** (Toggle-Button "Planungsmodus"):

```ts
function enterSimulationMode() {
  setBaseline(editState);
  setPendingChangeCount(0);
  setSimulationMode(true);
}
```

**Übernehmen** ("Speichern"-Button, nur sichtbar/aktiv während `simulationMode`):

```ts
async function commitSimulation() {
  // Ref MUSS synchron gesetzt werden, nicht nur ueber setSimulationMode(false) -
  // die Ref-Zuweisung "simulationModeRef.current = simulationMode" passiert erst
  // beim naechsten Render, saveTargets() wird aber noch VOR diesem Render
  // aufgerufen und wuerde den Guard sonst faelschlich noch aktiv sehen.
  simulationModeRef.current = false;
  setSimulationMode(false);
  await saveTargets(editState); // bestehende Funktion, unveraendert
  setBaseline(null);
}
```

**Verwerfen** ("Verwerfen"-Button):

```ts
function discardSimulation() {
  setEditState(baseline!);
  setBaseline(null);
  setSimulationMode(false);
  pendingSaveKind.current = null; // verhindert, dass der editState-Effect diese Restore-Aenderung als Save interpretiert
}
```

`pendingSaveKind.current = null` ist nötig, weil das Zurücksetzen von `editState` denselben `useEffect` triggert,
der normalerweise Saves auslöst — ohne den expliziten Reset würde ein zufällig noch gesetzter
`pendingSaveKind`-Wert vom letzten Simulationsschritt (der ja wegen des Guards in `saveTargets()` nie tatsächlich
gespeichert hat) beim Verwerfen einen unerwarteten Save auf den *alten* (Baseline-)Stand auslösen. Da `saveTargets()`
ohnehin während `simulationMode` blockt, wäre das harmlos, aber unnötig — der Reset macht die Absicht explizit statt
sich auf die Guard-Reihenfolge zu verlassen.

**`beforeunload`-Guard** (neuer `useEffect`, analog zum bestehenden `useModalOpenTracking()`-Muster in derselben
Datei):

```ts
useEffect(() => {
  if (!simulationMode || pendingChangeCount === 0) return;
  function handler(e: BeforeUnloadEvent) {
    e.preventDefault();
  }
  window.addEventListener("beforeunload", handler);
  return () => window.removeEventListener("beforeunload", handler);
}, [simulationMode, pendingChangeCount]);
```

**UI**: Toggle-Button oben in `WunschkaderTab` (neben der bestehenden Kopfzeile). Solange `simulationMode` aktiv:
sichtbarer Banner/Rahmen um die Zielliste ("Planungsmodus aktiv — Änderungen werden erst beim Speichern
übernommen"), Zähler ("N ungespeicherte Änderungen"), zwei Buttons "Speichern"/"Verwerfen" statt des Toggles. Der
bestehende `saveStatus`-Toast (saving/saved/error) bleibt unverändert — er feuert während der Simulation ohnehin
nicht (kein `saveTargets()`-Aufruf pro Aktion), erst beim Übernehmen einmalig, exakt wie ein normaler Sofort-Save
heute.

## Verification

- Neue Unit-Tests für die reine Zähler-/Guard-Logik, wo isolierbar (z.B. falls `pendingChangeCount`-Inkrement in eine
  kleine testbare Helper-Funktion ausgelagert wird statt inline in jeder Mutationsfunktion — Implementierungsdetail,
  vom Implementierungsplan zu entscheiden).
- Playwright-Component-Test (die Test-Infrastruktur dafür entsteht gerade parallel in einem anderen Worktree,
  `docs/superpowers/plans/2026-08-03-playwright-regression-coverage.md`): Modus an → 3 Aktionen (Ziel hinzufügen,
  Notiz ändern, Bank-Toggle) → bestätigen, dass **kein** Firestore-Write passiert ist (gemockter Firestore, keine
  `setDoc`-Calls) → Verwerfen → bestätigen `editState` == Baseline. Zweiter Testfall: Modus an → 1 Aktion →
  Übernehmen → bestätigen genau 1 `setDoc`-Call mit dem erwarteten Endzustand.
- Manuell: `beforeunload`-Warnung bei einem echten Reload-Versuch mit offener Simulation prüfen (automatisiert nur
  schwer zuverlässig testbar).
- `npm run typecheck`, `npm run build`, volle Vitest-Suite grün. Backend unberührt (reine Frontend-Änderung).

## Out of Scope (bewusst)

- Diff-/Änderungs-Übersicht vor dem Commit (siehe Nicht-Ziele).
- Mehrere parallele Simulationen/Szenarien.
- Persistenz über einen echten Reload hinweg.
- Sichtbarkeit simulierter Änderungen in `EigenesTeamTab` vor dem Commit.
