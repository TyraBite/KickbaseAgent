# Wunschkader Auto-Save + Tausendertrennzeichen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two independent, already-clarified frontend quick-wins: (1) real auto-save in `WunschkaderTab.tsx` so discrete changes persist immediately and free-text notes persist debounced, without any manual "Speichern" click; (2) live German thousands-separator formatting on the two market-value filter inputs in `AlleSpielerTab.tsx` so large numbers stay readable while typing.

**Architecture:** These are two unrelated bugfixes in two unrelated components — they are implemented as two independent task groups sharing nothing except the general project conventions (vitest for pure-function unit tests, no component-test harness in this repo). Task Group A (Tasks 1–4) touches `frontend/src/lib/useDebouncedCallback.ts` (new) and `frontend/src/components/WunschkaderTab.tsx`. Task Group B (Tasks 5–6) touches `frontend/src/lib/numberFormat.ts` (new) and `frontend/src/components/AlleSpielerTab.tsx`. The two groups can be executed in parallel by separate subagents; within each group, tasks are sequential.

Both new hooks/helpers follow the existing pattern already used by `frontend/src/lib/useHideOnScroll.ts`: extract the timing/formatting logic into a plain, React-free, directly-testable function, and keep the actual React hook/component as a thin wrapper around it. This matters here specifically because `frontend/vite.config.ts` runs vitest with `environment: "node"` (no jsdom) — there is no way to render a component or a hook in a test in this repo today, so anything that needs a test must be expressible as a pure function.

**Tech Stack:** React 18 + TypeScript (strict), Vite, Tailwind (utility classes, no CSS modules), Firebase Firestore v10 (`setDoc`/`doc`), vitest 2.1 (`environment: "node"`, no `@testing-library/*` installed).

## Global Constraints

- No new npm dependencies. Both fixes are implementable with what's already installed (`react`, `firebase`, `vitest`) — do not add `@testing-library/react`, a debounce library, or a number-formatting library.
- Match existing code style exactly: German inline comments explaining *why* (not just what) for anything non-obvious, `dark:` Tailwind variants on every visual element, named constants in `SCREAMING_SNAKE_CASE` at module top for magic numbers (see `MAX_SQUAD_SIZE`, `ML_PREDICTION_THRESHOLDS` in `WunschkaderTab.tsx`).
- Do not touch `src/dashboard_export.py`, `tests/test_dashboard_export.py`, `HANDOFF.md`, or any other file already showing as modified in `git status` — those are pre-existing unrelated changes in this worktree, out of scope for this plan.
- `frontend/src/App.tsx` passes `onSaved={(targets) => setWunschkader({ targets })}` into `WunschkaderTab` today — its signature (`(targets: RawWunschkaderTarget[]) => void`) must not change; Task Group A must keep calling it exactly as before, just from more call sites.
- Debounce delay for the Wunschkader Notiz field: 800ms after the last keystroke (per spec). Auto-dismiss delay for the "Gespeichert" success indicator: 2500ms (not specified exactly by the user, chosen as "brief"; encode as a named constant so it's a one-line change if adjusted later).
- Error messages (write failures, and the pre-existing "Speichern blockiert" migration guard) must stay visible until the user takes another action — never auto-dismiss them.
- After every task: run `npm run typecheck` (from `frontend/`) and fix any error before moving on. This repo has no ESLint configured (`frontend/package.json` has no `lint` script) — `tsc --noEmit` is the only static gate.
- Run all commands from `/workspace/work/.claude/worktrees/gitattributes-normalize/frontend` (the frontend subdirectory) unless stated otherwise. Do not create another git worktree — this repo is already an isolated worktree.

---

## Task Group A: Wunschkader real auto-save

### Task 1: `useDebouncedCallback` hook + pure debounce function

**Files:**
- Create: `frontend/src/lib/useDebouncedCallback.ts`
- Create: `frontend/src/lib/useDebouncedCallback.test.ts`

**Interfaces:**
- Produces: `createDebouncedFunction<Args extends unknown[]>(fn: (...args: Args) => void, delayMs: number): DebouncedFunction<Args>` where `DebouncedFunction<Args> = ((...args: Args) => void) & { cancel: () => void }` — pure, no React, directly testable with vitest fake timers.
- Produces: `useDebouncedCallback<Args extends unknown[]>(callback: (...args: Args) => void, delayMs: number): (...args: Args) => void` — the React hook Task 4 will use to debounce the Wunschkader Notiz save. Returns a stable function reference across re-renders (same identity every render, so it's safe to put in a `useEffect` dependency array).

- [ ] **Step 1: Write the failing test file**

Create `frontend/src/lib/useDebouncedCallback.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createDebouncedFunction } from "./useDebouncedCallback";

describe("createDebouncedFunction", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not call the function before the delay has elapsed", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("a");
    vi.advanceTimersByTime(799);
    expect(fn).not.toHaveBeenCalled();
  });

  it("calls the function once the delay has elapsed", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("a");
    vi.advanceTimersByTime(800);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("a");
  });

  it("resets the timer on repeated calls and only fires once with the last arguments", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("first");
    vi.advanceTimersByTime(500);
    debounced("second");
    vi.advanceTimersByTime(500);
    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(300);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("second");
  });

  it("cancel() prevents a pending call from firing", () => {
    const fn = vi.fn();
    const debounced = createDebouncedFunction(fn, 800);
    debounced("a");
    debounced.cancel();
    vi.advanceTimersByTime(1000);
    expect(fn).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm run test -- useDebouncedCallback.test.ts`
Expected: FAIL — `Failed to resolve import "./useDebouncedCallback"` (file doesn't exist yet).

- [ ] **Step 3: Implement `createDebouncedFunction` and `useDebouncedCallback`**

Create `frontend/src/lib/useDebouncedCallback.ts`:

```ts
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm run test -- useDebouncedCallback.test.ts`
Expected: PASS, 4 tests.

- [ ] **Step 5: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/useDebouncedCallback.ts frontend/src/lib/useDebouncedCallback.test.ts
git commit -m "Wunschkader Auto-Save: useDebouncedCallback-Hook (Basis fuer Notiz-Debounce)"
```

---

### Task 2: Extract `saveTargets`, simplify + structure the save status (button still present)

This task rewrites the status/messaging plumbing without yet wiring auto-save — the "Speichern" button still exists and still saves on click. This keeps the task small and independently verifiable before Task 3 layers auto-save on top.

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Produces: `type SaveStatus = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string }` — Task 3 and Task 4 read/write this via `setSaveStatus`.
- Produces: `async function saveTargets(next: EditTarget[]): Promise<void>` (module-inner function of `WunschkaderTab`, closes over `editState`'s setters/`onSaved`/`db` but takes the array to persist as an explicit argument instead of reading `editState` from closure). Task 3's auto-save effect and Task 4's debounced note-save both call this directly.

- [ ] **Step 1: Read the current file to confirm line numbers haven't drifted**

Read `frontend/src/components/WunschkaderTab.tsx` in full before editing — Task 1 didn't touch it, but always verify against the live file, not this plan's line numbers.

- [ ] **Step 2: Replace the two constants block to add the new dismiss-timing constant**

Find (near the top of the file):

```ts
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };
const ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 };
const MAX_SQUAD_SIZE = 17;
```

Replace with:

```ts
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };
const ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 };
const MAX_SQUAD_SIZE = 17;
// Wie lange die kurze "Gespeichert"-Anzeige nach einem erfolgreichen
// Auto-Save sichtbar bleibt, bevor sie automatisch verschwindet. Fehler
// nutzen diesen Timer NICHT - die bleiben stehen, bis der Nutzer etwas
// tut (User-Feedback f462d415: "ausser es gibt beim Schreiben einen
// Fehler der sollte angezeigt werden").
const SAVE_INDICATOR_DISMISS_MS = 2500;
```

- [ ] **Step 3: Add the `SaveStatus` type**

Directly above `export type EditTarget = RawWunschkaderTarget & { _uid: number };`, add:

```ts
type SaveStatus = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string };
```

So that section reads:

```ts
type SaveStatus = { kind: "idle" } | { kind: "saving" } | { kind: "saved" } | { kind: "error"; message: string };

export type EditTarget = RawWunschkaderTarget & { _uid: number };
```

- [ ] **Step 4: Replace `handleSave` with `saveTargets` + status auto-dismiss effect**

Find:

```ts
  const [saveStatus, setSaveStatus] = useState("");

  async function handleSave() {
    // Absicherung gegen die einmalige Migration (migrate_wunschkader_player_ids.py):
    // solange die noch nicht gegen den aktuellen Firestore-Wunschkader-Doc
    // gelaufen ist, kann _build_wunschkader_targets() (dashboard_export.py)
    // Ziele ohne player_id durchreichen (nur stderr-Warnung, kein Datenverlust
    // serverseitig). Ein Save von hier aus wuerde mit merge:true das gesamte
    // targets-Array ersetzen und damit die name-Felder unwiderruflich
    // wegwerfen, die das Migrationsskript zum Aufloesen braucht - deshalb
    // lieber hart blockieren als stillschweigend Daten verlieren.
    if (editState.some((t) => !t.player_id)) {
      setSaveStatus(
        "Speichern blockiert: mindestens ein Ziel hat keine player_id (Migration noch nicht gelaufen?) — Firestore-Konsole pruefen."
      );
      return;
    }
    setSaveStatus("Speichere…");
    try {
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, updated_at: updatedAt }, { merge: true });
      onSaved(targets);
      setSaveStatus("Gespeichert - überall sofort sichtbar (auch Eigenes Team), kein Reload nötig. Andere Werte wie Marktwerte/ML-Prognosen für ggf. neu hinzugefügte Spieler folgen weiterhin erst mit dem nächsten Pipeline-Lauf.");
    } catch (err) {
      setSaveStatus("Fehler beim Speichern: " + (err as Error).message);
    }
  }
```

Replace with:

```ts
  const [saveStatus, setSaveStatus] = useState<SaveStatus>({ kind: "idle" });

  // Auto-Save macht den expliziten "Speichern"-Moment ueberfluessig - die
  // Erfolgsmeldung darf deshalb nur noch ein kurzer, sich selbst
  // wegraeumender Hinweis sein ("gespeichert reicht", User-Feedback
  // f462d415), keine dauerhafte Statuszeile mehr. Fehler bleiben bewusst
  // stehen (kein Timer in diesem Zweig).
  useEffect(() => {
    if (saveStatus.kind !== "saved") return;
    const timer = setTimeout(() => setSaveStatus({ kind: "idle" }), SAVE_INDICATOR_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [saveStatus]);

  async function saveTargets(next: EditTarget[]) {
    // Absicherung gegen die einmalige Migration (migrate_wunschkader_player_ids.py):
    // solange die noch nicht gegen den aktuellen Firestore-Wunschkader-Doc
    // gelaufen ist, kann _build_wunschkader_targets() (dashboard_export.py)
    // Ziele ohne player_id durchreichen (nur stderr-Warnung, kein Datenverlust
    // serverseitig). Ein Save von hier aus wuerde mit merge:true das gesamte
    // targets-Array ersetzen und damit die name-Felder unwiderruflich
    // wegwerfen, die das Migrationsskript zum Aufloesen braucht - deshalb
    // lieber hart blockieren als stillschweigend Daten verlieren.
    if (next.some((t) => !t.player_id)) {
      setSaveStatus({
        kind: "error",
        message:
          "Speichern blockiert: mindestens ein Ziel hat keine player_id (Migration noch nicht gelaufen?) — Firestore-Konsole pruefen.",
      });
      return;
    }
    setSaveStatus({ kind: "saving" });
    try {
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = next.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
      await setDoc(doc(db, "wunschkader", "current"), { targets, updated_at: updatedAt }, { merge: true });
      onSaved(targets);
      setSaveStatus({ kind: "saved" });
    } catch (err) {
      setSaveStatus({ kind: "error", message: "Fehler beim Speichern: " + (err as Error).message });
    }
  }
```

- [ ] **Step 5: Update the render block to use the new status shape (button still present, still click-driven)**

Find:

```tsx
      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Speichern
        </button>
        {saveStatus && <span className="text-sm text-slate-500 dark:text-slate-400">{saveStatus}</span>}
      </div>
```

Replace with:

```tsx
      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={() => saveTargets(editState)}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Speichern
        </button>
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

- [ ] **Step 6: Typecheck**

Run: `npm run typecheck`
Expected: no errors. (`useEffect` is already imported at the top of this file — no import changes needed for this task.)

- [ ] **Step 7: Run the existing test suite (regression check)**

Run: `npm run test`
Expected: PASS, same 8 tests as before (this task touches no tested logic, this just guards against an accidental break elsewhere).

- [ ] **Step 8: Manual sanity check**

Run: `npm run dev`, open the Wunschkader tab, click "Speichern". Expected: "✓ Gespeichert" appears in emerald and disappears after ~2.5s on its own. Temporarily break it (e.g. comment out the Firestore write) only if you want to eyeball the error path — otherwise trust the code read; do not leave the app in a broken state.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "Wunschkader: Speichern-Status vereinfachen (auto-dismiss Erfolg, persistenter Fehler + Retry)"
```

---

### Task 3: Wire immediate auto-save into the four discrete mutations, remove the manual button

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `saveTargets(next: EditTarget[])` from Task 2.
- Produces: a `pendingSaveKind` ref of type `"immediate" | "debounced" | null` — Task 4 extends the effect that reads it to also handle the `"debounced"` case (Task 4 is the only remaining place that still needs to *set* it to `"debounced"`; this task only ever sets `"immediate"`).

- [ ] **Step 1: Add the `pendingSaveKind` ref and the auto-save effect**

Directly below the `saveTargets` function (added in Task 2), add:

```ts
  // Merkt sich, WELCHE Art Save nach der naechsten editState-Aenderung
  // faellig ist: "immediate" fuer diskrete Aktionen (Ziel hinzufuegen/
  // entfernen/tauschen, Bank-Toggle - kein Freitext, darf sofort schreiben),
  // "debounced" fuer die Notiz (Freitext, siehe Task 4). Ein Ref statt
  // State, weil das Setzen synchron VOR dem setEditState()-Aufruf passieren
  // muss und selbst keinen Re-Render braucht. null bedeutet "editState hat
  // sich aus einem anderen Grund geaendert (z.B. initiales Mount) - nicht
  // speichern", verhindert also einen Auto-Save direkt beim Laden der Seite.
  const pendingSaveKind = useRef<"immediate" | "debounced" | null>(null);

  useEffect(() => {
    if (pendingSaveKind.current !== "immediate") return;
    pendingSaveKind.current = null;
    saveTargets(editState);
  }, [editState]);
```

- [ ] **Step 2: Wire `toggleBench` to set the pending kind before mutating**

Find:

```ts
  function toggleBench(uid: number) {
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { ...t, role: isBench(t) ? "Starter" : "Bank/Backup-Option" } : t))
    );
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, role: isBench(prev) ? "Starter" : "Bank/Backup-Option" } : prev));
  }
```

Replace with:

```ts
  function toggleBench(uid: number) {
    pendingSaveKind.current = "immediate";
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { ...t, role: isBench(t) ? "Starter" : "Bank/Backup-Option" } : t))
    );
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, role: isBench(prev) ? "Starter" : "Bank/Backup-Option" } : prev));
  }
```

- [ ] **Step 3: Wire `removeTarget`**

Find:

```ts
  function removeTarget(uid: number) {
    setEditState((prev) => prev.filter((t) => t._uid !== uid));
    setSelected(null);
  }
```

Replace with:

```ts
  function removeTarget(uid: number) {
    pendingSaveKind.current = "immediate";
    setEditState((prev) => prev.filter((t) => t._uid !== uid));
    setSelected(null);
  }
```

- [ ] **Step 4: Wire `replaceTarget`**

Find:

```ts
  function replaceTarget(uid: number, playerId: string) {
    setEditState((prev) =>
      prev.map((t) => {
        if (t._uid !== uid) return t;
        const { note: _note, ...keep } = t;
        return { ...keep, player_id: playerId };
      })
    );
    setSelected(null);
  }
```

Replace with:

```ts
  function replaceTarget(uid: number, playerId: string) {
    pendingSaveKind.current = "immediate";
    setEditState((prev) =>
      prev.map((t) => {
        if (t._uid !== uid) return t;
        const { note: _note, ...keep } = t;
        return { ...keep, player_id: playerId };
      })
    );
    setSelected(null);
  }
```

- [ ] **Step 5: Wire `addTarget`**

Find:

```ts
  function addTarget(target: { player_id: string; position: Position; role: string }) {
    setEditState((prev) => [
      ...prev,
      { player_id: target.player_id, role: target.role, _uid: prev.length ? Math.max(...prev.map((t) => t._uid)) + 1 : 0 },
    ]);
  }
```

Replace with:

```ts
  function addTarget(target: { player_id: string; position: Position; role: string }) {
    pendingSaveKind.current = "immediate";
    setEditState((prev) => [
      ...prev,
      { player_id: target.player_id, role: target.role, _uid: prev.length ? Math.max(...prev.map((t) => t._uid)) + 1 : 0 },
    ]);
  }
```

- [ ] **Step 6: Remove the manual "Speichern" button — only the status indicator remains**

Find (this is the block Task 2 last edited):

```tsx
      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={() => saveTargets(editState)}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Speichern
        </button>
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

Replace with (only the button element is removed, everything else is unchanged):

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

Note: this `<div>` can now be empty on initial render (all three conditions false) — that's fine, it just takes no visible height beyond its `mb-6` margin, same as the old `{saveStatus && ...}` guard being falsy.

- [ ] **Step 7: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 8: Run the existing test suite (regression check)**

Run: `npm run test`
Expected: PASS, same tests as before.

- [ ] **Step 9: Manual verification**

Run: `npm run dev`, open the Wunschkader tab:
- Add a target (via an empty slot card) → "✓ Gespeichert" should appear and auto-dismiss, with no button click needed.
- Open a target's detail modal, click "Bank"/"Startelf" toggle → same auto-save behavior.
- Remove a target → same.
- Use "Wechsel" to replace a target → same.
- Confirm there is no "Speichern" button anywhere on the tab anymore.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "Wunschkader: echtes Auto-Save fuer Ziel hinzufuegen/entfernen/tauschen/Bank-Toggle, Speichern-Button entfernt"
```

---

### Task 4: Debounced auto-save for the Notiz textarea

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `useDebouncedCallback` from Task 1 (`frontend/src/lib/useDebouncedCallback.ts`), `pendingSaveKind` ref and the auto-save effect from Task 3.

- [ ] **Step 1: Import `useDebouncedCallback`**

Find the top-of-file import block:

```ts
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { doc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
```

Replace with:

```ts
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { doc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import { useDebouncedCallback } from "../lib/useDebouncedCallback";
```

(`useRef` is added here because Task 3 already introduced `pendingSaveKind = useRef(...)` — if Task 3 already added `useRef` to this import in its own step, skip re-adding it; the end state of this import line either way must include `useEffect, useMemo, useRef, useState, type FormEvent`.)

- [ ] **Step 2: Add the debounced save constant**

Directly below the `SAVE_INDICATOR_DISMISS_MS` constant added in Task 2, add:

```ts
// Wie lange nach dem letzten Tastendruck in der Notiz gewartet wird, bevor
// automatisch gespeichert wird - verhindert einen Firestore-Write pro
// Zeichen (User-Feedback f462d415, "wirkliches Auto-Save").
const NOTE_SAVE_DEBOUNCE_MS = 800;
```

- [ ] **Step 3: Create the debounced save callback and extend the auto-save effect**

Find (added in Task 3):

```ts
  const pendingSaveKind = useRef<"immediate" | "debounced" | null>(null);

  useEffect(() => {
    if (pendingSaveKind.current !== "immediate") return;
    pendingSaveKind.current = null;
    saveTargets(editState);
  }, [editState]);
```

Replace with:

```ts
  const pendingSaveKind = useRef<"immediate" | "debounced" | null>(null);
  const debouncedSaveTargets = useDebouncedCallback(saveTargets, NOTE_SAVE_DEBOUNCE_MS);

  useEffect(() => {
    const kind = pendingSaveKind.current;
    if (kind === null) return;
    pendingSaveKind.current = null;
    if (kind === "immediate") {
      saveTargets(editState);
    } else {
      debouncedSaveTargets(editState);
    }
  }, [editState, debouncedSaveTargets]);
```

- [ ] **Step 4: Wire `updateNote` to the debounced path**

Find:

```ts
  function updateNote(uid: number, note: string) {
    setEditState((prev) => prev.map((t) => (t._uid === uid ? { ...t, note } : t)));
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, note } : prev));
  }
```

Replace with:

```ts
  function updateNote(uid: number, note: string) {
    pendingSaveKind.current = "debounced";
    setEditState((prev) => prev.map((t) => (t._uid === uid ? { ...t, note } : t)));
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, note } : prev));
  }
```

- [ ] **Step 5: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Run the full test suite**

Run: `npm run test`
Expected: PASS, including the 4 new `useDebouncedCallback.test.ts` tests from Task 1.

- [ ] **Step 7: Manual verification**

Run: `npm run dev`, open the Wunschkader tab, open a target's detail modal, type multiple characters quickly into the Notiz field. Expected: no "Speichere…"/"✓ Gespeichert" flicker per keystroke; the save fires once, roughly 800ms after you stop typing. Close and reopen the modal (or reload) to confirm the note persisted.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "Wunschkader: Notiz-Feld debounced auto-speichern (800ms nach letztem Tastendruck)"
```

---

## Task Group B: Thousands separators for the market-value filter in AlleSpielerTab

### Task 5: `numberFormat.ts` — formatting/parsing/cursor helpers

**Files:**
- Create: `frontend/src/lib/numberFormat.ts`
- Create: `frontend/src/lib/numberFormat.test.ts`

**Interfaces:**
- Produces: `formatThousands(value: string): string` — strips non-digits, returns the German-grouped string (`"500000"` → `"500.000"`), or `""` for no digits.
- Produces: `parseThousands(value: string): number` — strips non-digits and parses, or `NaN` for no digits (mirrors the existing `Number(x) || default` fallback idiom already used at the AlleSpielerTab call sites).
- Produces: `digitCountBefore(value: string, index: number): number` — counts digit characters in `value` before `index`.
- Produces: `cursorIndexForDigitCount(formatted: string, digitCount: number): number` — inverse of the above: the character index in `formatted` right after its `digitCount`-th digit (or `formatted.length` if it has fewer digits than that).

These four are used together by Task 6 to reformat a market-value input on every keystroke while keeping the text cursor at the same logical digit position (not jumping to the end).

- [ ] **Step 1: Write the failing test file**

Create `frontend/src/lib/numberFormat.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { cursorIndexForDigitCount, digitCountBefore, formatThousands, parseThousands } from "./numberFormat";

describe("formatThousands", () => {
  it("returns an empty string for empty input", () => {
    expect(formatThousands("")).toBe("");
  });

  it("inserts German thousands separators", () => {
    expect(formatThousands("500000")).toBe("500.000");
    expect(formatThousands("5000000")).toBe("5.000.000");
  });

  it("leaves small numbers without a separator", () => {
    expect(formatThousands("12")).toBe("12");
  });

  it("strips non-digit characters before formatting (idempotent on already-formatted input)", () => {
    expect(formatThousands("500.000")).toBe("500.000");
  });

  it("returns an empty string when there are no digits at all", () => {
    expect(formatThousands("abc")).toBe("");
  });
});

describe("parseThousands", () => {
  it("parses a formatted value back to a plain number", () => {
    expect(parseThousands("500.000")).toBe(500_000);
    expect(parseThousands("5.000.000")).toBe(5_000_000);
  });

  it("returns NaN for an empty string", () => {
    expect(parseThousands("")).toBeNaN();
  });

  it("returns NaN when there are no digits", () => {
    expect(parseThousands("abc")).toBeNaN();
  });
});

describe("digitCountBefore", () => {
  it("counts only digit characters before the given index", () => {
    expect(digitCountBefore("500.000", 0)).toBe(0);
    expect(digitCountBefore("500.000", 3)).toBe(3);
    expect(digitCountBefore("500.000", 4)).toBe(3);
  });
});

describe("cursorIndexForDigitCount", () => {
  it("returns 0 for a digit count of 0 or less", () => {
    expect(cursorIndexForDigitCount("500.000", 0)).toBe(0);
  });

  it("places the cursor right after the nth digit, skipping over separators", () => {
    expect(cursorIndexForDigitCount("500.000", 3)).toBe(3);
    expect(cursorIndexForDigitCount("500.000", 4)).toBe(5);
  });

  it("returns the string length when the digit count matches the total available digits", () => {
    expect(cursorIndexForDigitCount("500.000", 6)).toBe(7);
  });

  it("falls back to the string end if there are fewer digits than requested", () => {
    expect(cursorIndexForDigitCount("50", 6)).toBe(2);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm run test -- numberFormat.test.ts`
Expected: FAIL — `Failed to resolve import "./numberFormat"`.

- [ ] **Step 3: Implement the helpers**

Create `frontend/src/lib/numberFormat.ts`:

```ts
// Hilfsfunktionen fuer Tausenderpunkte in Zahlen-Eingabefeldern (die
// Marktwert-Min/Max-Filter in AlleSpielerTab.tsx). <input type="number">
// lehnt Punkte als Tausendertrennzeichen als ungueltiges Zeichen ab -
// deshalb formatieren wir hier reine Ziffern-Strings manuell fuer ein
// type="text"-Feld mit inputMode="numeric" (behaelt die numerische
// Mobil-Tastatur, User-Feedback d390f441).

// Entfernt alles Nicht-Ziffern und formatiert das Ergebnis mit
// de-DE-Tausenderpunkten (z.B. "500000" -> "500.000"). Leerer String bleibt
// leer, damit ein Feld waehrend des Tippens leer sein darf (siehe
// AlleSpielerTab.tsx - marketValueMinInput/marketValueMaxInput haelt
// genau deshalb einen String statt einer Number).
export function formatThousands(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits === "") return "";
  return Number(digits).toLocaleString("de-DE");
}

// Kehrt formatThousands() um: entfernt die Punkte (und jedes andere
// Nicht-Ziffern-Zeichen) wieder und liefert die reine Zahl. Leerer/
// ungueltiger Input liefert NaN, damit bestehende "Number(x) || default"-
// Fallback-Stellen unveraendert weiterfunktionieren (NaN ist falsy).
export function parseThousands(value: string): number {
  const digits = value.replace(/\D/g, "");
  return digits === "" ? NaN : Number(digits);
}

// Zaehlt Ziffern vor `index` in `value` - die "logische" Cursor-Position
// unabhaengig von eingestreuten Formatierungspunkten. Wird zusammen mit
// cursorIndexForDigitCount() genutzt, um den Cursor nach dem Neu-Formatieren
// an derselben logischen Stelle zu halten (sonst springt er beim Tippen ans
// Feldende).
export function digitCountBefore(value: string, index: number): number {
  let count = 0;
  for (let i = 0; i < index && i < value.length; i++) {
    if (/\d/.test(value[i])) count++;
  }
  return count;
}

// Kehrt digitCountBefore() um: findet die Zeichen-Position in `formatted`
// direkt nach der `digitCount`-ten Ziffer. Faellt auf das Stringende zurueck,
// falls `formatted` weniger Ziffern enthaelt als `digitCount` (z.B. wenn der
// Nutzer eine Ziffer geloescht hat).
export function cursorIndexForDigitCount(formatted: string, digitCount: number): number {
  if (digitCount <= 0) return 0;
  let seen = 0;
  for (let i = 0; i < formatted.length; i++) {
    if (/\d/.test(formatted[i])) {
      seen++;
      if (seen >= digitCount) return i + 1;
    }
  }
  return formatted.length;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm run test -- numberFormat.test.ts`
Expected: PASS, 13 tests.

- [ ] **Step 5: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/numberFormat.ts frontend/src/lib/numberFormat.test.ts
git commit -m "AlleSpieler: numberFormat-Helfer fuer Tausenderpunkte (format/parse/Cursor)"
```

---

### Task 6: Switch the two market-value inputs to live-formatted text inputs

**Files:**
- Modify: `frontend/src/components/AlleSpielerTab.tsx`

**Interfaces:**
- Consumes: `formatThousands`, `parseThousands`, `digitCountBefore`, `cursorIndexForDigitCount` from `frontend/src/lib/numberFormat.ts` (Task 5).

**Chosen approach:** live reformatting on every keystroke (not format-on-blur). The original feedback is specifically about the numbers being hard to read *while entering them* ("Beim Eintragen der Filter... ist es sehr schwierig die Zahlen zu lesen") — format-on-blur would only show separators once the user is done typing, which is exactly when the readability problem no longer applies. `digitCountBefore`/`cursorIndexForDigitCount` exist to keep the text cursor at the same logical digit position after each reformat, otherwise it would jump to the end of the field after every keystroke.

**Known accepted limitation:** if the user positions the cursor immediately after an inserted separator dot and presses Backspace, nothing visibly changes on that first press (the dot carries no digit of its own) — a second Backspace then removes the digit before it. This is called out in a code comment; fixing it fully would require detecting and skipping over the separator on delete, which is more complexity than this quick win warrants.

- [ ] **Step 1: Read the current file to confirm line numbers haven't drifted**

Read `frontend/src/components/AlleSpielerTab.tsx` in full before editing.

- [ ] **Step 2: Update the top-of-file react import**

Find:

```ts
import { useEffect, useMemo, useRef, useState } from "react";
```

Replace with:

```ts
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
```

- [ ] **Step 3: Import the new helpers**

Find:

```ts
import { buildAlleSpielerRows, normalizeSearchText, type AlleSpielerRow } from "../lib/derive";
```

Replace with:

```ts
import { buildAlleSpielerRows, normalizeSearchText, type AlleSpielerRow } from "../lib/derive";
import { cursorIndexForDigitCount, digitCountBefore, formatThousands, parseThousands } from "../lib/numberFormat";
```

- [ ] **Step 4: Format the initial input values and switch parsing to `parseThousands`**

Find (keep the existing explanatory comment above this block untouched — it documents why these are strings, not numbers, and that reasoning still holds):

```ts
  const [marketValueMinInput, setMarketValueMinInput] = useState(String(500_000));
  const [marketValueMaxInput, setMarketValueMaxInput] = useState(String(maxMarketValue));
  const marketValueMin = marketValueMinInput.trim() === "" ? 500_000 : Number(marketValueMinInput) || 500_000;
  const marketValueMax = marketValueMaxInput.trim() === "" ? maxMarketValue : Number(marketValueMaxInput) || maxMarketValue;
```

Replace with:

```ts
  const [marketValueMinInput, setMarketValueMinInput] = useState(formatThousands(String(500_000)));
  const [marketValueMaxInput, setMarketValueMaxInput] = useState(() => formatThousands(String(maxMarketValue)));
  const marketValueMin = marketValueMinInput.trim() === "" ? 500_000 : parseThousands(marketValueMinInput) || 500_000;
  const marketValueMax = marketValueMaxInput.trim() === "" ? maxMarketValue : parseThousands(marketValueMaxInput) || maxMarketValue;
```

- [ ] **Step 5: Add the `MarketValueInput` local component**

Find:

```ts
const selectClass =
  "rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

function RankFilter({
```

Replace with:

```ts
const selectClass =
  "rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

// type="text" + inputMode="numeric" statt type="number", weil ein nativer
// Zahlen-Input Punkte als Tausendertrennzeichen als ungueltiges Zeichen
// ablehnt (User-Feedback d390f441: Nullen beim Eintragen schwer lesbar).
// Formatiert bei jedem Tastendruck neu (nicht erst beim Blur), weil genau
// das Tippen selbst laut Feedback das Problem ist. digitCountBefore()/
// cursorIndexForDigitCount() (lib/numberFormat.ts) halten den Cursor dabei
// an der gleichen "logischen" Ziffer-Position, sonst wuerde er nach jedem
// Zeichen ans Feldende springen. Bekannte kleine Einschraenkung: Backspace
// direkt auf einem frisch eingefuegten Punkt loescht beim ersten Druck
// nichts sichtbares (der Punkt traegt keine eigene Ziffer) - ein zweiter
// Backspace entfernt dann die Ziffer davor.
function MarketValueInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (raw: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingCursorRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (pendingCursorRef.current !== null && inputRef.current) {
      inputRef.current.setSelectionRange(pendingCursorRef.current, pendingCursorRef.current);
      pendingCursorRef.current = null;
    }
  }, [value]);

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value;
    const cursorBefore = e.target.selectionStart ?? raw.length;
    const digitsBefore = digitCountBefore(raw, cursorBefore);
    const formatted = formatThousands(raw);
    pendingCursorRef.current = cursorIndexForDigitCount(formatted, digitsBefore);
    onChange(formatted);
  }

  return (
    <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
      {label}
      <input
        ref={inputRef}
        type="text"
        inputMode="numeric"
        value={value}
        onChange={handleChange}
        className="w-32 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
    </label>
  );
}

function RankFilter({
```

- [ ] **Step 6: Replace the two raw number inputs with `MarketValueInput`**

Find:

```tsx
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Marktwert min
          <input
            type="number"
            min={500_000}
            step={100_000}
            value={marketValueMinInput}
            onChange={(e) => setMarketValueMinInput(e.target.value)}
            className="w-32 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Marktwert max
          <input
            type="number"
            min={500_000}
            step={100_000}
            value={marketValueMaxInput}
            onChange={(e) => setMarketValueMaxInput(e.target.value)}
            className="w-32 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </label>
```

Replace with:

```tsx
        <MarketValueInput label="Marktwert min" value={marketValueMinInput} onChange={setMarketValueMinInput} />
        <MarketValueInput label="Marktwert max" value={marketValueMaxInput} onChange={setMarketValueMaxInput} />
```

- [ ] **Step 7: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 8: Run the full test suite**

Run: `npm run test`
Expected: PASS, including the 13 new `numberFormat.test.ts` tests from Task 5.

- [ ] **Step 9: Manual verification**

Run: `npm run dev`, open the "Alle Spieler" tab:
- Clear the "Marktwert min" field completely → it should go empty (not snap to a default while you're still typing), matching the pre-existing behavior.
- Type `500000` into "Marktwert min" digit by digit → it should show `500.000` with dots appearing live as you type, cursor staying right after the digit you just typed (not jumping to the end).
- Type `5000000` into "Marktwert max" → `5.000.000`.
- Confirm the filter still actually filters the list (i.e. `marketValueMin`/`marketValueMax` are parsed correctly from the dotted display value).
- Delete digits from the middle of a formatted value and confirm the result renumbers correctly (e.g. `500.000` minus one digit → `50.000`).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/AlleSpielerTab.tsx
git commit -m "AlleSpieler: Marktwert-Filter mit Tausenderpunkten live waehrend des Tippens"
```
