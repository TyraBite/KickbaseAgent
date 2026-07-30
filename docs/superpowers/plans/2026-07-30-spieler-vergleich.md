# Spieler-Vergleichsansicht Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine geteilte `PlayerCompareModal`-Komponente, die zwei Spieler im Detail nebeneinander vergleicht (inkl. "wer ist besser"-Hervorhebung), mit Einstiegspunkten aus Wunschkader (Ersatzspieler-Suche), Eigenes Team und Alle Spieler - basierend auf `docs/superpowers/specs/2026-07-30-spieler-vergleich-design.md`.

**Architecture:** `PlayerCompareModal` nimmt zwei `player_id`s + `players`/`calibration` (nicht den ganzen Snapshot - schlankere Props, passt zum bestehenden Muster in SpekulationTab/TransfermarktTab) und baut für beide Seiten über die schon bestehende `buildPlayerRow()` (`derive.ts`) dieselben Felder. Ein neuer, geteilter `PlayerNamePicker` (einfache Namenssuche über ALLE Spieler, keine Distanz-Gewichtung wie Wunschkaders bestehende Ersatzspieler-Suche) wird an drei Stellen wiederverwendet: als "Vergleichen mit…"-Trigger in Eigenes-Team/Alle-Spieler, UND als "Wechseln"-Trigger innerhalb des offenen Vergleichs selbst (pro Seite austauschen, ohne das Modal zu schließen).

**Tech Stack:** TypeScript/React (`frontend/src/`). Kein Test-Framework im Frontend - Verifikation über `tsc --noEmit` + manueller Browser-Test durch den User.

## Global Constraints

- Nur 2 Spieler gleichzeitig, kein Mehrfach-Vergleich.
- Transfermarkt/Spekulation sind NICHT Teil dieses Plans (siehe Spec, Out of Scope) - `PlayerCompareModal`/`PlayerNamePicker` aber so gebaut, dass eine spätere Erweiterung dort nur eine zusätzliche Wiring-Stelle braucht.
- Keine Persistierung eines Vergleichs - rein transientes UI-Fenster.
- `PlayerCompareModal` kennt NICHTS von Wunschkader-spezifischen Konzepten (kein `AlleSpielerRow`, kein `onReplace`) - der optionale `onSelectSide`-Callback liefert nur eine rohe `player_id` zurück, die Interpretation (was "auswählen" bedeutet) bleibt beim Aufrufer.
- Frontend-Verifikation: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` nach jedem Task.
- Kein Push in dieser Session (Standing-Rule `NeverPushOnMain`) - Repo-Owner pusht selbst.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `frontend/src/components/PlayerNamePicker.tsx` | NEU - geteilte Namenssuche über alle Spieler (3x wiederverwendet) |
| `frontend/src/components/PlayerCompareModal.tsx` | NEU - der eigentliche Zwei-Spalten-Vergleich mit Hervorhebung + Seiten-Wechsel |
| `frontend/src/components/WunschkaderTab.tsx` | Ersatzspieler-Vorschlag/Suche öffnet jetzt Vergleich statt sofort zu tauschen; `onReplace`/`replaceTarget` vereinfacht auf `playerId: string` |
| `frontend/src/components/EigenesTeamTab.tsx` | Bestehendes Detail-Modal bekommt "Vergleichen mit…" |
| `frontend/src/components/AlleSpielerTab.tsx` | Bekommt ein neues, schlankes Detail-Modal (gab's bisher nicht) MIT "Vergleichen mit…" |

---

## Task 1: `PlayerNamePicker.tsx` — geteilte Namenssuche

**Files:**
- Create: `frontend/src/components/PlayerNamePicker.tsx`

**Interfaces:**
- Consumes: `Record<string, PlayerRecord>` (aus `data.players`, überall schon vorhanden).
- Produces: `PlayerNamePicker({ players, excludePlayerId, onSelect }) `. Konsumiert von Task 2 (Wechseln-Trigger), Task 4, Task 5 (Vergleichen-mit-Trigger).

- [ ] **Step 1: Implement**

```tsx
import { useState } from "react";
import type { PlayerRecord } from "../types";
import { fmtNum } from "../format";

const MAX_RESULTS = 20;

export default function PlayerNamePicker({
  players,
  excludePlayerId,
  onSelect,
}: {
  players: Record<string, PlayerRecord>;
  excludePlayerId?: string;
  onSelect: (playerId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const results = q
    ? Object.values(players)
        .filter((p) => p.player_id !== excludePlayerId && p.name.toLowerCase().includes(q))
        .slice(0, MAX_RESULTS)
    : [];

  return (
    <div>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Spieler suchen…"
        className="mb-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      {q && (
        <div className="flex flex-wrap gap-2">
          {results.length ? (
            results.map((p) => (
              <button
                key={p.player_id}
                type="button"
                onClick={() => onSelect(p.player_id)}
                className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {p.name} ({fmtNum(p.market_value)})
              </button>
            ))
          ) : (
            <span className="text-xs text-slate-400 dark:text-slate-500">Keine Treffer.</span>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PlayerNamePicker.tsx
git commit -m "PlayerNamePicker: geteilte Namenssuche ueber alle Spieler"
```

---

## Task 2: `PlayerCompareModal.tsx` — der Vergleich selbst

**Files:**
- Create: `frontend/src/components/PlayerCompareModal.tsx`

**Interfaces:**
- Consumes: `PlayerNamePicker` (Task 1), `buildPlayerRow()` (`derive.ts`, bereits vorhanden).
- Produces: `PlayerCompareModal({ playerIdA, playerIdB, players, calibration, thresholds, onSelectSide, onClose })`. Konsumiert von Task 3-5.

- [ ] **Step 1: Implement**

```tsx
import { useEffect, useState, type ReactNode } from "react";
import type { Calibration, PlayerRecord } from "../types";
import { buildPlayerRow, type PlayerRow } from "../lib/derive";
import { Badge, POSITION_ABBR, SignalBadge, TeamCrest } from "./ui";
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
import { useModalOpenTracking } from "../lib/modalOpenTracker";
import PlayerNamePicker from "./PlayerNamePicker";

const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };

type Side = "a" | "b";
type Winner = Side | null;

function better(a: number | null, b: number | null, lowerIsBetter = false): Winner {
  if (a === null || b === null || a === b) return null;
  const aWins = lowerIsBetter ? a < b : a > b;
  return aWins ? "a" : "b";
}

function betterFitness(a: string | null, b: string | null): Winner {
  const aFit = !a;
  const bFit = !b;
  if (aFit === bFit) return null;
  return aFit ? "a" : "b";
}

function CompareRow({ label, valueA, valueB, winner }: { label: string; valueA: ReactNode; valueB: ReactNode; winner: Winner }) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-slate-100 py-2 text-sm last:border-0 dark:border-slate-800/60">
      <div className={`text-right ${winner === "a" ? "font-semibold text-brand-600 dark:text-brand-400" : "text-slate-700 dark:text-slate-200"}`}>
        {valueA}
      </div>
      <div className="whitespace-nowrap text-center text-xs text-slate-400 dark:text-slate-500">{label}</div>
      <div className={`text-left ${winner === "b" ? "font-semibold text-brand-600 dark:text-brand-400" : "text-slate-700 dark:text-slate-200"}`}>
        {valueB}
      </div>
    </div>
  );
}

export default function PlayerCompareModal({
  playerIdA,
  playerIdB,
  players,
  calibration,
  thresholds,
  onSelectSide,
  onClose,
}: {
  playerIdA: string;
  playerIdB: string;
  players: Record<string, PlayerRecord>;
  calibration: Calibration | null;
  thresholds: { good: number; critical: number };
  onSelectSide?: (playerId: string) => void;
  onClose: () => void;
}) {
  const [idA, setIdA] = useState(playerIdA);
  const [idB, setIdB] = useState(playerIdB);
  const [switching, setSwitching] = useState<Side | null>(null);

  useModalOpenTracking();
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const playerA = players[idA];
  const playerB = players[idB];
  if (!playerA || !playerB) {
    // Sollte praktisch nie vorkommen (IDs kommen immer aus data.players),
    // aber ohne diesen Guard wuerde buildPlayerRow() auf undefined crashen.
    return (
      <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
        <div onClick={(e) => e.stopPropagation()} className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900">
          <p className="text-sm text-slate-500 dark:text-slate-400">Spieler nicht gefunden.</p>
        </div>
      </div>
    );
  }

  const rowA: PlayerRow = buildPlayerRow(playerA, calibration);
  const rowB: PlayerRow = buildPlayerRow(playerB, calibration);

  function renderName(row: PlayerRow, side: Side) {
    return (
      <div className="flex flex-col items-center gap-1 text-center">
        <div className="flex items-center gap-1.5">
          <TeamCrest teamName={row.team_name} />
          <span className="font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
        </div>
        <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
        <button
          type="button"
          onClick={() => setSwitching(side)}
          className="text-xs text-brand-600 hover:underline dark:text-brand-400"
        >
          Wechseln
        </button>
        {onSelectSide && (
          <button
            type="button"
            onClick={() => onSelectSide(side === "a" ? idA : idB)}
            className="mt-1 rounded-full border border-brand-300 bg-brand-50 px-3 py-1 text-xs text-brand-800 hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300"
          >
            Diesen als Ersatz wählen
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="grid flex-1 grid-cols-2 gap-4">
            {renderName(rowA, "a")}
            {renderName(rowB, "b")}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>

        {switching && (
          <div className="mb-4 rounded-xl border border-slate-200 p-3 dark:border-slate-800">
            <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
              Ersetze Seite {switching === "a" ? "links" : "rechts"} durch…
            </p>
            <PlayerNamePicker
              players={players}
              excludePlayerId={switching === "a" ? idB : idA}
              onSelect={(id) => {
                if (switching === "a") setIdA(id);
                else setIdB(id);
                setSwitching(null);
              }}
            />
          </div>
        )}

        <div>
          <CompareRow
            label="ML-Prognose"
            valueA={<span className={trendClass(rowA.ml_prediction)}>{trendArrow(rowA.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(rowA.ml_prediction)}</span>}
            valueB={<span className={trendClass(rowB.ml_prediction)}>{trendArrow(rowB.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(rowB.ml_prediction)}</span>}
            winner={better(rowA.ml_prediction, rowB.ml_prediction)}
          />
          <CompareRow
            label="Signal"
            valueA={<SignalBadge signal={rowA.signal} thresholds={thresholds} />}
            valueB={<SignalBadge signal={rowB.signal} thresholds={thresholds} />}
            winner={better(rowA.signal, rowB.signal)}
          />
          <CompareRow
            label="Marktwert"
            valueA={fmtNum(rowA.market_value)}
            valueB={fmtNum(rowB.market_value)}
            winner={better(rowA.market_value, rowB.market_value, true)}
          />
          <CompareRow
            label="Startelf-Rang"
            valueA={rowA.starting_rank ?? "n/v"}
            valueB={rowB.starting_rank ?? "n/v"}
            winner={better(rowA.starting_rank, rowB.starting_rank, true)}
          />
          <CompareRow
            label="Fitness"
            valueA={<Badge tone={rowA.status_label ? "crit" : "good"}>{rowA.status_label ?? "Fit"}</Badge>}
            valueB={<Badge tone={rowB.status_label ? "crit" : "good"}>{rowB.status_label ?? "Fit"}</Badge>}
            winner={betterFitness(rowA.status_label, rowB.status_label)}
          />
          <CompareRow
            label="Schnitt"
            valueA={fmtNum(rowA.average_points)}
            valueB={fmtNum(rowB.average_points)}
            winner={better(rowA.average_points, rowB.average_points)}
          />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 3: Manual sanity check (kein Test-Framework im Frontend)**

Kurz im Kopf durchgehen: `better(null, 5)` → `null` (kein Crash, kein Highlight) ✓. `better(5, 5)` → `null` (Gleichstand, kein Highlight) ✓. `betterFitness(null, "Verletzt")` → `"a"` (kein Label = fit = besser) ✓. Beide Seiten dieselbe `player_id` → `rowA`/`rowB` identisch, alle `better()`-Aufrufe geben `null` zurück (kein Highlight, kein Crash) ✓.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PlayerCompareModal.tsx
git commit -m "PlayerCompareModal: Zwei-Spalten-Vergleich mit Besser-Hervorhebung und Seiten-Wechsel"
```

---

## Task 3: `WunschkaderTab.tsx` — Ersatzspieler-Suche öffnet Vergleich

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `PlayerCompareModal` (Task 2).
- Produces: `onReplace`/`replaceTarget` vereinfacht auf `(playerId: string) => void` (vorher `(replacement: AlleSpielerRow) => void` - nur `.player_id` wurde je verwendet).

- [ ] **Step 1: Simplify `replaceTarget` and the `onReplace` prop type**

In `frontend/src/components/WunschkaderTab.tsx`:

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

Call-Site (Zeile mit `onReplace={(replacement) => replaceTarget(selected._uid, replacement)}`) anpassen:

```tsx
          onReplace={(playerId) => replaceTarget(selected._uid, playerId)}
```

`DetailModal`'s Props-Typ anpassen:

```ts
  onReplace: (playerId: string) => void;
```

- [ ] **Step 2: Add compare state and wire the suggestion/search chips to open it instead of replacing directly**

Im `DetailModal`-Funktionskörper (nach `const [search, setSearch] = useState("");`) ergänzen:

```ts
  const [compareWith, setCompareWith] = useState<AlleSpielerRow | null>(null);
```

Die beiden bestehenden `onClick={() => onReplace(s)}`-Stellen (Zeile ~523 Vorschläge-Chips UND Zeile ~547 Suchergebnis-Chips) ändern auf:

```tsx
                    onClick={() => setCompareWith(s)}
```

(beide Stellen identisch ändern - Vorschlag-Chip UND Suchergebnis-Chip)

- [ ] **Step 3: Render `PlayerCompareModal` as a sibling when a comparison target is set**

Die Komponente rendert aktuell `return (<div className="fixed inset-0 ...">...</div>);` als einziges Wurzel-Element. Da `PlayerCompareModal` selbst ein eigenes `fixed inset-0`-Overlay ist, wird es NICHT in diesen bestehenden `div` genestet, sondern als Sibling danebengestellt - das `return` bekommt dafür einen Fragment-Wrapper:

```tsx
  return (
    <>
      <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
        {/* ... gesamter bestehender Inhalt dieses divs UNVERAENDERT ... */}
      </div>
      {compareWith && (
        <PlayerCompareModal
          playerIdA={target.player_id}
          playerIdB={compareWith.player_id}
          players={players}
          calibration={calibration}
          thresholds={thresholds}
          onSelectSide={(playerId) => {
            onReplace(playerId);
            setCompareWith(null);
          }}
          onClose={() => setCompareWith(null)}
        />
      )}
    </>
  );
```

(Nur die äußerste `return`-Klammerung ändert sich - das bestehende `<div className="fixed inset-0 ...">`...`</div>` bleibt inhaltlich exakt wie es ist, nur um `<>`/`</>` UND den neuen `{compareWith && (...)}`-Block ergänzt.)

- [ ] **Step 4: Thread `players`/`calibration` into `DetailModal` and add the import**

`DetailModal`'s Props-Interface ergänzen:

```ts
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
```

Am Aufruf von `<DetailModal ... />` (im übergeordneten `WunschkaderTab`) ergänzen: `players={data.players}` und `calibration={data.calibration}`.

Import ergänzen:

```ts
import PlayerCompareModal from "./PlayerCompareModal";
```

- [ ] **Step 5: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "WunschkaderTab: Ersatzspieler-Klick oeffnet Vergleich statt sofort zu tauschen, onReplace vereinfacht auf playerId"
```

---

## Task 4: `EigenesTeamTab.tsx` — "Vergleichen mit…" im bestehenden Detail-Modal

**Files:**
- Modify: `frontend/src/components/EigenesTeamTab.tsx`

**Interfaces:**
- Consumes: `PlayerNamePicker` (Task 1), `PlayerCompareModal` (Task 2).

**Wichtiger Befund beim Gegenchecken:** `DetailModalShell`s `children` landen direkt in einem `<dl>` (siehe `ui.tsx::Row` - rendert echte `<dt>`/`<dd>`). Ein rohes `<button>` dort reinzuhängen wäre ungültiges HTML (ein `dl` darf nur `dt`/`dd`/`div`/script-artige Kinder haben). `DetailModalShell` bekommt deshalb zuerst einen neuen optionalen `footer`-Prop, der NACH dem `</dl>` (aber noch innerhalb der Karte) gerendert wird - beide Detail-Modals nutzen ihn für den neuen Button.

- [ ] **Step 1: Add an optional `footer` prop to `DetailModalShell`**

In `frontend/src/components/EigenesTeamTab.tsx`, Zeile 239 (`function DetailModalShell({ header, onClose, children }: ...)`) ändern zu:

```tsx
function DetailModalShell({
  header,
  footer,
  onClose,
  children,
}: {
  header: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  useEscapeClose(onClose);
  useModalOpenTracking();
  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          {header}
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2 text-sm">{children}</dl>
        {footer}
      </div>
    </div>
  );
}
```

(Nur `footer` ist neu - Rest 1:1 wie zuvor.)

- [ ] **Step 2: Add compare state, the trigger button (via `footer`), and the sibling `PlayerCompareModal` to `PlayerDetailModal`**

`PlayerDetailModal`s Props (Zeile 265) um `players`/`calibration` erweitern und State ergänzen:

```tsx
function PlayerDetailModal({
  row,
  thresholds,
  mae,
  players,
  calibration,
  onClose,
}: {
  row: EigenesTeamRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
  const [comparing, setComparing] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  return (
    <>
      <DetailModalShell
        onClose={onClose}
        header={
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={row.team_name} />
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
          </div>
        }
        footer={
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setComparing((v) => !v)}
              className="text-xs text-brand-600 hover:underline dark:text-brand-400"
            >
              Vergleichen mit…
            </button>
            {comparing && (
              <div className="mt-2">
                <PlayerNamePicker players={players} excludePlayerId={row.player_id} onSelect={setCompareWith} />
              </div>
            )}
          </div>
        }
      >
        {row.sell_signal && (
          <Row label="Empfehlung">
            <Badge tone={row.sell_signal === "halten" ? "good" : "warn"}>
              {row.sell_signal === "halten" ? "Noch halten" : "Jetzt verkaufen"}
            </Badge>
          </Row>
        )}
        <MlPredictionRow value={row.ml_prediction} mae={mae} />
        <Row label="Trend 7T">
          <span className={trendClass(row.market_value_change_7d)}>
            {trendArrow(row.market_value_change_7d, TREND_7D_THRESHOLDS)} {fmtSigned(row.market_value_change_7d)}
          </span>
        </Row>
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <StatusLabelRow value={row.status_label} />
        <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
        <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
        <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
      </DetailModalShell>
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
    </>
  );
}
```

(Kein `onSelectSide` hier - der Vergleich bleibt in Eigenes Team rein informativ, siehe Spec. Der bisherige `<DetailModalShell>`-Rumpf, Zeilen 286-307, ist unverändert - nur `footer` ist neu und der `return` bekommt einen Fragment-Wrapper.)

- [ ] **Step 3: Repeat for `WatchlistDetailModal`**

Dieselbe Erweiterung (Props `players`/`calibration`, `comparing`/`compareWith`-State, `footer` mit Button+Picker, Fragment-Wrapper, sibling `PlayerCompareModal` ohne `onSelectSide`) 1:1 auch in `WatchlistDetailModal` (Zeile 311) ergänzen - identisches Muster, andere Row-Typ (`WatchlistRow` statt `EigenesTeamRow`, hat aber ebenfalls `player_id`), bestehender `<DetailModalShell>`-Rumpf (Zeilen 333-339) bleibt unverändert:

```tsx
function WatchlistDetailModal({
  row,
  thresholds,
  mae,
  players,
  calibration,
  onClose,
}: {
  row: WatchlistRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  mae: number | null;
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
  const [comparing, setComparing] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  return (
    <>
      <DetailModalShell
        onClose={onClose}
        header={
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={row.team_name} />
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
          </div>
        }
        footer={
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setComparing((v) => !v)}
              className="text-xs text-brand-600 hover:underline dark:text-brand-400"
            >
              Vergleichen mit…
            </button>
            {comparing && (
              <div className="mt-2">
                <PlayerNamePicker players={players} excludePlayerId={row.player_id} onSelect={setCompareWith} />
              </div>
            )}
          </div>
        }
      >
        <Row label="Verfügbarkeit">{row.status ?? "—"}</Row>
        <Row label="Signal">
          <SignalBadge signal={row.signal} thresholds={thresholds} />
        </Row>
        <MlPredictionRow value={row.ml_prediction} mae={mae} />
        <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
        <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
        <StatusLabelRow value={row.status_label} />
        <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
      </DetailModalShell>
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
    </>
  );
}
```

(Referenz für den unveränderten `<DetailModalShell>`-Rumpf: aktuell endet die Komponente nach `<Row label="Schnitt">` mit einer schließenden `</DetailModalShell>` - genauer Rumpf oben bereits vollständig wiedergegeben, keine weiteren Zeilen in der aktuellen Fassung.)

- [ ] **Step 4: Wire the new props at both call sites and add imports**

Am Aufruf von `<PlayerDetailModal ... />` (Zeile 91) und `<WatchlistDetailModal ... />` (Zeile 94) ergänzen: `players={data.players}` und `calibration={data.calibration}`.

Imports ergänzen (nach der bestehenden `Row`/`ui`-Import-Zeile):

```ts
import PlayerNamePicker from "./PlayerNamePicker";
import PlayerCompareModal from "./PlayerCompareModal";
```

- [ ] **Step 5: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/EigenesTeamTab.tsx
git commit -m "EigenesTeamTab: Vergleichen-mit-Button in beiden Detail-Modals, DetailModalShell bekommt footer-Slot"
```

---

## Task 5: `AlleSpielerTab.tsx` — neues Detail-Modal MIT "Vergleichen mit…"

**Files:**
- Modify: `frontend/src/components/AlleSpielerTab.tsx`

**Interfaces:**
- Consumes: `PlayerNamePicker` (Task 1), `PlayerCompareModal` (Task 2). `AlleSpielerRow` (bereits vorhanden, hat alle 6 Vergleichsfelder via `PlayerRow`).

- [ ] **Step 1: Add row-click state, imports, and the new detail modal**

Bestehende Importzeilen (Zeile 4 und 6) erweitern:

```ts
import { Badge, POSITION_ABBR, Row, SignalBadge, TeamCrest } from "./ui";
```

```ts
import { fmtNum, fmtSigned, trendArrow, trendClass } from "../format";
```

Neue Imports ergänzen:

```ts
import PlayerNamePicker from "./PlayerNamePicker";
import PlayerCompareModal from "./PlayerCompareModal";
```

Im Komponenten-Body (nach den bestehenden Filter-States) ergänzen:

```ts
  const [selected, setSelected] = useState<AlleSpielerRow | null>(null);
```

`<SortableTable columns={columns} rows={visible} rowKey={...} />` (die bestehende Tabellen-Zeile) um `onRowClick={setSelected}` ergänzen (Prop existiert schon in `table.tsx`, siehe Nutzung in anderen Tabs).

Am Ende der Komponente (vor dem letzten schließenden `</div>`) ergänzen:

```tsx
      {selected && (
        <AlleSpielerDetailModal
          row={selected}
          thresholds={thresholds}
          players={data.players}
          calibration={data.calibration}
          onClose={() => setSelected(null)}
        />
      )}
```

- [ ] **Step 2: Implement `AlleSpielerDetailModal`**

Am Ende der Datei ergänzen (Feld-Set/Reihenfolge identisch zu EigenesTeamTab, ML-Prognose-Schwellen dafür lokal definiert, da bisher in dieser Datei nicht gebraucht):

```tsx
const ML_PREDICTION_THRESHOLDS = { flat: 20_000, strong: 100_000 };

function AlleSpielerDetailModal({
  row,
  thresholds,
  players,
  calibration,
  onClose,
}: {
  row: AlleSpielerRow;
  thresholds: DashboardSnapshot["signal_thresholds"];
  players: DashboardSnapshot["players"];
  calibration: DashboardSnapshot["calibration"];
  onClose: () => void;
}) {
  const [comparing, setComparing] = useState(false);
  const [compareWith, setCompareWith] = useState<string | null>(null);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <TeamCrest teamName={row.team_name} />
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[row.position] ?? row.position}</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="flex h-11 w-11 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2 text-sm">
          <Row label="Verfügbarkeit">
            <Badge tone={ownerTone(row.owner)}>{row.owner}</Badge>
          </Row>
          <Row label="Startelf-Rang">{row.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Fitness">
            <Badge tone={row.status_label ? "crit" : "good"}>{row.status_label ?? "Fit"}</Badge>
          </Row>
          <Row label="Schnitt">{fmtNum(row.average_points)}</Row>
          <Row label="Signal">
            <SignalBadge signal={row.signal} thresholds={thresholds} />
          </Row>
          <Row label="Marktwert">{fmtNum(row.market_value)}</Row>
          <Row label="ML-Prognose">
            <span className={trendClass(row.ml_prediction)}>
              {trendArrow(row.ml_prediction, ML_PREDICTION_THRESHOLDS)} {fmtSigned(row.ml_prediction)}
            </span>
          </Row>
        </dl>
        <button
          type="button"
          onClick={() => setComparing((v) => !v)}
          className="mt-3 text-xs text-brand-600 hover:underline dark:text-brand-400"
        >
          Vergleichen mit…
        </button>
        {comparing && (
          <div className="mt-2">
            <PlayerNamePicker players={players} excludePlayerId={row.player_id} onSelect={setCompareWith} />
          </div>
        )}
      </div>
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
    </div>
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AlleSpielerTab.tsx
git commit -m "AlleSpielerTab: neues Detail-Modal (gab's bisher nicht) inkl. Vergleichen-mit-Button"
```

---

## Task 6: Browser-Verifikation (manuell, kein Code)

**Files:** keine

- [ ] **Step 1**: Alle Commits pushen (User macht das selbst).
- [ ] **Step 2**: Echter Browser-Test durch den User (Sandbox kann kein `npm run dev`):
  - Wunschkader: ein Ziel öffnen, "Wechsel" → auf einen Vorschlag klicken → Vergleich öffnet sich statt direkt zu tauschen. "Diesen als Ersatz wählen" auf einer Seite klicken → Ziel wird ersetzt, beide Modals schließen.
  - Im offenen Vergleich: "Wechseln" auf einer Seite → Namenssuche → anderen Spieler wählen → nur diese Seite tauscht, Modal bleibt offen.
  - Eigenes Team: einen Spieler öffnen → "Vergleichen mit…" → Namenssuche → Vergleich öffnet sich, KEIN "Diesen als Ersatz wählen"-Button sichtbar (rein informativ).
  - Alle Spieler: eine Zeile anklicken → neues Detail-Modal öffnet sich (gab's bisher nicht) → "Vergleichen mit…" testen wie oben.
  - Stichprobe Hervorhebung: zwei Spieler mit klar unterschiedlichem Marktwert vergleichen, prüfen dass der GÜNSTIGERE grün hervorgehoben wird (nicht der teurere).

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: geteilte Komponente, 3 Einstiegspunkte (inkl. des neu entdeckten Alle-Spieler-Modal-Bedarfs), Seiten-Wechsel im offenen Vergleich, Tausch-Auslöser via `onSelectSide`, Besser-Hervorhebung inkl. Marktwert (niedriger besser) - alle Abschnitte der finalen Spec haben eine Task.
- **Platzhalter-Scan**: keine TBD/"analog zu Task N ohne Code" gefunden.
- **Typ-Konsistenz**: `PlayerCompareModal`/`PlayerNamePicker`-Props identisch benannt zwischen allen 3 Wiring-Tasks (`players`/`calibration`/`thresholds`/`onSelectSide`/`onClose`). `onReplace`/`replaceTarget`s Signatur-Vereinfachung (Task 3) ist in sich konsistent (Call-Site + Props-Typ + Implementierung alle auf `playerId: string` umgestellt).
- **Wiederverwendung verifiziert**: `buildPlayerRow()` (schon vorhanden, keine Duplikation der Signal-/Fairwert-Berechnung), `POSITION_ABBR`/`TeamCrest`/`SignalBadge`/`Badge`/`Row` (alle aus `ui.tsx`, keine neuen Parallel-Komponenten), Modal-Grundgerüst (Escape-Handler, `useModalOpenTracking()`, 44px-Close-Button) folgt exakt dem in dieser Session etablierten Muster.
- **Gegen den echten Code verifiziert (nicht nur die Spec)**: alle betroffenen Dateien (`WunschkaderTab.tsx`, `EigenesTeamTab.tsx`, `AlleSpielerTab.tsx`, `ui.tsx`, `derive.ts`, `types.ts`, `format.ts`, `table.tsx`) vor dem Schreiben der Tasks direkt gelesen, nicht nur aus der Session-Erinnerung übernommen. Dabei zwei echte Bugs im ersten Entwurf gefunden und korrigiert: (1) `DetailModalShell`s `children` landen direkt in einem `<dl>` - ein rohes `<button>` dort wäre ungültiges HTML, daher bekommt die Shell jetzt einen `footer`-Prop statt den Button einfach anzuhängen; (2) `PlayerCompareModal` als zusätzliches `fixed inset-0`-Overlay braucht in `WunschkaderTab.tsx`s `DetailModal` einen Fragment-Wrapper um den bestehenden `return`, sonst wäre es fälschlich in den bestehenden Overlay-`div` genestet gewesen.
