# Wunschkader-Simulationsmodus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein zuschaltbarer "Planungsmodus" für `WunschkaderTab`, der Auto-Save für die Dauer der Session aussetzt und alle Änderungen erst am Ende per "Speichern"/"Verwerfen" committed oder verwirft.

**Architecture:** Rein additiver State/Guard in der bestehenden `WunschkaderTab.tsx`-Komponente — ein Boolean-Flag (plus Ref-Spiegel) blockt die einzige Stelle, die tatsächlich nach Firestore schreibt (`saveTargets()`), ohne die bestehenden Mutationsfunktionen oder den Auto-Save-Trigger-Effect anzufassen. Kein neuer Firestore-Pfad, kein neues Schema, keine neuen Dependencies.

**Tech Stack:** React/TypeScript (Vite), bestehendes `useState`/`useRef`/`useEffect`-Muster dieser Datei, Vitest für Regressionslauf.

## Global Constraints

- Keine neuen npm-Dependencies.
- Deutsche UI-Texte, exakt: "Planungsmodus starten", "Planungsmodus aktiv — Änderungen werden erst beim Speichern übernommen", "Speichern", "Verwerfen", "N ungespeicherte Änderungen"/"N ungespeicherte Änderung" (Singular bei 1).
- Kein Rückbau/keine Änderung am bestehenden Auto-Save-Pfad für die Normalnutzung (`saveTargets`, `pendingSaveKind`, `debouncedSaveTargets`, `latestEditStateRef` bleiben strukturell unverändert — nur ein Guard kommt hinzu).
- Keine Backend-/Firestore-Schema-Änderung — derselbe `setDoc(doc(db,"wunschkader","current"), {targets, updated_at}, {merge:true})`-Schreibpfad wie bisher, nur seltener/gebündelter ausgelöst.
- **Keine künstliche Pure-Function-Extraktion nur für Testbarkeit** (Standing-Feedback, siehe [[feedback_avoid_optional_params]]) — die bestehenden äquivalenten Mechanismen in dieser Datei (`pendingSaveKind`-Ref, `saveSeqRef`) sind ebenfalls nicht dediziert unit-getestet, nur über Typecheck/Build/manuellen Test abgesichert. Dieser Plan folgt demselben Muster statt künstlich eine "reine" Reducer-Funktion herauszuschneiden, die es sonst nirgends bräuchte.
- Automatisierte Component-/Playwright-Testabdeckung für dieses Feature ist bewusst **nicht** Teil dieses Plans — die dafür nötige Test-Infrastruktur (Playwright CT, gemockter Firestore) entsteht gerade parallel in einem anderen aktiven Worktree (`docs/superpowers/plans/2026-08-03-playwright-regression-coverage.md`). Ein Regressionstest für den Simulationsmodus ist ein sinnvolles Follow-up, sobald jener Plan abgeschlossen ist — nicht hier duplizieren.
- Push-Policy dieses Repos: direkt auf `main` pushen, sobald alle Tests grün sind (kein Feature-Branch/PR-Umweg nötig, siehe [[project_kickbaseagent_git_workflow]]).
- Vor Merge/Push erneut `git log origin/main --oneline -5` und `git worktree list` prüfen (Race-Condition-Risiko bei parallelen Sessions, siehe [[feedback_check_worktrees_before_fresh_plan_dispatch]]).

---

## Task 1: Planungsmodus in WunschkaderTab

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx` (State, Guard, 5 Mutationsfunktionen, 3 neue Funktionen, 1 neuer Effect, UI-Block)

**Interfaces:**
- Konsumiert ausschließlich Bestehendes aus derselben Datei: `EditTarget[]` (Typ bereits vorhanden), `editState`/`setEditState`, `saveTargets(next: EditTarget[])`, `pendingSaveKind` (Ref).
- Produziert nichts, was andere Dateien konsumieren — komplett in sich geschlossen innerhalb `WunschkaderTab.tsx`.

- [ ] **Step 1: Neuen State + Ref direkt nach dem bestehenden `addDialog`-State ergänzen**

In `frontend/src/components/WunschkaderTab.tsx`, direkt nach Zeile 128 (`const [addDialog, setAddDialog] = useState<{ presetPosition: Position | null } | null>(null);`):

```ts
  // Planungsmodus: Auto-Save wird fuer die Dauer der Session ausgesetzt,
  // Aenderungen werden erst per commitSimulation()/discardSimulation() am
  // Ende gespeichert oder verworfen. simulationModeRef ist noetig, weil ein
  // bereits laufender Notiz-Debounce-Timer (debouncedSaveTargets) beim
  // Fristablauf den AKTUELLEN Modus sehen muss, nicht den zum Zeitpunkt des
  // Timer-Starts eingefangenen - gleiches Muster wie latestEditStateRef oben.
  const [simulationMode, setSimulationMode] = useState(false);
  const simulationModeRef = useRef(false);
  simulationModeRef.current = simulationMode;
  const [baseline, setBaseline] = useState<EditTarget[] | null>(null);
  const [pendingChangeCount, setPendingChangeCount] = useState(0);
```

- [ ] **Step 2: Guard ganz am Anfang von `saveTargets()` ergänzen**

Direkt nach `async function saveTargets(next: EditTarget[]) {` (aktuell Zeile 287), vor dem bestehenden Migrations-Check:

```ts
  async function saveTargets(next: EditTarget[]) {
    // Waehrend des Planungsmodus schreibt nichts nach Firestore - weder der
    // Sofort-Pfad (direkter Aufruf aus dem editState-Effect) noch der
    // debounced Notiz-Pfad (debouncedSaveTargets() ruft ebenfalls saveTargets()
    // auf). Ref statt State, damit ein spaet feuernder Debounce-Timer den
    // aktuellen Modus sieht.
    if (simulationModeRef.current) return;
    if (next.some((t) => !t.player_id)) {
```

(Der Rest der Funktion bleibt unveraendert - nur die neue Zeile wird eingefuegt, die bestehende `if (next.some(...))`-Zeile darunter bleibt exakt wie sie ist.)

- [ ] **Step 3: Zaehler-Increment in allen 5 Mutationsfunktionen ergaenzen**

Jede der folgenden Funktionen bekommt direkt nach der bestehenden `pendingSaveKind.current = ...`-Zeile eine neue Zeile `if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);` - die restliche Funktion bleibt unveraendert:

```ts
  function toggleBench(uid: number) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { ...t, role: isBench(t) ? "Starter" : "Bank/Backup-Option" } : t))
    );
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, role: isBench(prev) ? "Starter" : "Bank/Backup-Option" } : prev));
  }

  function removeTarget(uid: number) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) => prev.filter((t) => t._uid !== uid));
    setSelected(null);
  }

  function replaceTarget(uid: number, playerId: string) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) =>
      prev.map((t) => {
        if (t._uid !== uid) return t;
        const { note: _note, ...keep } = t;
        return { ...keep, player_id: playerId };
      })
    );
    setSelected(null);
  }

  function updateNote(uid: number, note: string) {
    pendingSaveKind.current = "debounced";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) => prev.map((t) => (t._uid === uid ? { ...t, note } : t)));
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, note } : prev));
  }

  function addTarget(target: { player_id: string; position: Position; role: string }) {
    pendingSaveKind.current = "immediate";
    if (simulationModeRef.current) setPendingChangeCount((n) => n + 1);
    setEditState((prev) => [
      ...prev,
      { player_id: target.player_id, role: target.role, _uid: prev.length ? Math.max(...prev.map((t) => t._uid)) + 1 : 0 },
    ]);
  }
```

- [ ] **Step 4: `enterSimulationMode`/`commitSimulation`/`discardSimulation` ergaenzen**

Direkt nach dem bestehenden `useEffect`, der den Auto-Save auslöst (nach der schließenden `}, [editState, debouncedSaveTargets]);`-Zeile, aktuell Zeile 354), vor `const totalCount = editState.length;`:

```ts
  function enterSimulationMode() {
    setBaseline(editState);
    setPendingChangeCount(0);
    simulationModeRef.current = true;
    setSimulationMode(true);
  }

  async function commitSimulation() {
    // Ref MUSS synchron gesetzt werden, nicht nur ueber setSimulationMode(false) -
    // die Ref-Zuweisung "simulationModeRef.current = simulationMode" oben im
    // Funktionskoerper passiert erst beim naechsten Render, saveTargets() wird
    // aber noch VOR diesem Render aufgerufen und wuerde den Guard sonst
    // faelschlich noch aktiv sehen.
    simulationModeRef.current = false;
    setSimulationMode(false);
    await saveTargets(editState);
    setBaseline(null);
  }

  function discardSimulation() {
    // Verhindert, dass der editState-Effect das gleich folgende Zuruecksetzen
    // auf die Baseline als faelligen Save interpretiert (waere durch den
    // saveTargets()-Guard ohnehin harmlos, macht die Absicht aber explizit
    // statt sich auf die Guard-Reihenfolge zu verlassen).
    pendingSaveKind.current = null;
    simulationModeRef.current = false;
    setSimulationMode(false);
    if (baseline) setEditState(baseline);
    setBaseline(null);
  }
```

- [ ] **Step 5: `beforeunload`-Guard ergaenzen**

Direkt nach den drei Funktionen aus Step 4, weiterhin vor `const totalCount = editState.length;`:

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

- [ ] **Step 6: UI-Block ersetzen**

Der bestehende Block (aktuell Zeilen 385-400):

```tsx
      <div className="mb-6 flex items-center gap-3">
        {saveStatus.kind === "saving" && (
          <span className="text-sm text-slate-500 dark:text-slate-400">Speichere…</span>
        )}
        {saveStatus.kind === "saved" && (
          <span className="text-sm text-emerald-600 dark:text-emerald-400">✓ Gespeichert</span>
        )}
        {saveStatus.kind === "error" && (
          <span className="text-sm text-red-600 dark:text-red-400">
            {saveStatus.message}{" "}
            <button type="button" onClick={() => saveTargets(editState)} className="underline hover:no-underline">
              Erneut versuchen
            </button>
          </span>
        )}
      </div>
```

wird ersetzt durch:

```tsx
      <div className="mb-6 flex flex-wrap items-center gap-3">
        {!simulationMode && (
          <button
            type="button"
            onClick={enterSimulationMode}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Planungsmodus starten
          </button>
        )}
        {simulationMode && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-950/40">
            <span className="font-medium text-amber-800 dark:text-amber-300">
              Planungsmodus aktiv — Änderungen werden erst beim Speichern übernommen
            </span>
            <span className="text-amber-700 dark:text-amber-400">
              {pendingChangeCount} ungespeicherte {pendingChangeCount === 1 ? "Änderung" : "Änderungen"}
            </span>
            <button
              type="button"
              onClick={discardSimulation}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Verwerfen
            </button>
            <button
              type="button"
              onClick={commitSimulation}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
            >
              Speichern
            </button>
          </div>
        )}
        {!simulationMode && saveStatus.kind === "saving" && (
          <span className="text-sm text-slate-500 dark:text-slate-400">Speichere…</span>
        )}
        {!simulationMode && saveStatus.kind === "saved" && (
          <span className="text-sm text-emerald-600 dark:text-emerald-400">✓ Gespeichert</span>
        )}
        {!simulationMode && saveStatus.kind === "error" && (
          <span className="text-sm text-red-600 dark:text-red-400">
            {saveStatus.message}{" "}
            <button type="button" onClick={() => saveTargets(editState)} className="underline hover:no-underline">
              Erneut versuchen
            </button>
          </span>
        )}
      </div>
```

(Klassen 1:1 aus bestehenden Buttons in derselben Datei übernommen — sekundärer Button-Stil von Zeile 915, primärer Button-Stil von Zeile 922; amber-Töne aus `Badge`s `warn`-Tone in `ui.tsx`.)

- [ ] **Step 7: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: 0 Fehler.

- [ ] **Step 8: Vitest-Regressionslauf**

Run: `cd frontend && npm run test`
Expected: weiterhin alle 6 Testdateien / 51 Tests grün (keine neuen Testdateien in diesem Task, reine Regression — siehe Global Constraints zur bewussten Nicht-Erweiterung der Unit-Test-Abdeckung).

- [ ] **Step 9: Build**

Run: `cd frontend && npm run build`
Expected: erfolgreich, keine neuen Warnungen außer der bereits bekannten, unabhängigen Chunk-Size-Warnung.

- [ ] **Step 10: Manueller Dev-Server-Test**

Dev-Server starten (`npm run dev` im `frontend/`-Verzeichnis, oder die `run`-Skill dieses Projekts nutzen), Wunschkader-Tab öffnen:

1. "Planungsmodus starten" klicken → amber Banner erscheint, "Planungsmodus starten"-Button verschwindet.
2. Ein Ziel hinzufügen → Zähler zeigt "1 ungespeicherte Änderung", Browser-DevTools-Netzwerk-Tab (Filter auf `firestore.googleapis.com`/`Write`) zeigt **keinen** neuen Write.
3. Bank/Startelf-Toggle bei einem bestehenden Ziel klicken → Zähler auf "2 ungespeicherte Änderungen", weiterhin kein Write.
4. Notiz bei einem Ziel ändern, > 800ms warten (Notiz-Debounce-Zeit) → Zähler auf "3 ungespeicherte Änderungen", weiterhin kein Write (bestätigt, dass auch der debounced Pfad blockt).
5. "Verwerfen" klicken → Banner verschwindet, Zielliste zeigt wieder exakt den Stand von vor Schritt 1 (das eben hinzugefügte Ziel ist wieder weg, Bank/Startelf-Status und Notiz wieder wie vorher).
6. "Planungsmodus starten" erneut klicken, ein Ziel hinzufügen, "Speichern" klicken → Banner verschwindet, normale "✓ Gespeichert"-Anzeige erscheint kurz, Netzwerk-Tab zeigt **genau einen** neuen Write mit dem erwarteten Endzustand (das hinzugefügte Ziel ist jetzt Teil des `targets`-Arrays im Write-Payload).
7. Tab zu "Eigenes Team" wechseln und zurück zu "Wunschkader" (App unmountet Tabs nicht, siehe Architektur) → falls während Schritt 6 noch eine Simulation offen gewesen wäre, müsste sie hier erhalten geblieben sein; da bereits gespeichert, hier nur bestätigen, dass der Tab-Wechsel keinen Fehler wirft.
8. Mit einer erneut gestarteten, ungespeicherten Simulation einen echten Reload versuchen (F5/Cmd+R) → Browser zeigt die native "Änderungen verwerfen?"-Warnung.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "Wunschkader: Planungsmodus (Auto-Save aus, Speichern/Verwerfen am Ende)"
```

## Self-Review (durchgeführt beim Schreiben dieses Plans)

- **Spec-Abdeckung**: alle Punkte aus dem Spec (`docs/superpowers/specs/2026-08-03-wunschkader-simulationsmodus-design.md`) sind in Task 1 abgedeckt — State/Ref, Guard, Zähler, enter/commit/discard, `beforeunload`, UI. Der im Spec-Self-Review bereits gefundene und korrigierte Ref-Bug (`simulationModeRef.current = false` synchron in `commitSimulation()`) ist in Step 4 korrekt übernommen.
- **Placeholder-Scan**: keine TBD/TODO, jeder Step enthält vollständigen, copy-paste-fähigen Code.
- **Typ-Konsistenz**: `EditTarget[]` (Baseline-Typ) matched den bestehenden `editState`-Typ exakt, keine neuen Typen eingeführt, die an anderer Stelle abweichend benannt werden könnten.
