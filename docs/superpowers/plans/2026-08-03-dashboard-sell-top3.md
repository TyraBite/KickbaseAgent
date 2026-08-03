# Dashboard-Verkaufen: immer Top-3 statt Signal-Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die "Verkaufen"-Sektion im Dashboard zeigt immer die 3 eigenen Spieler mit der niedrigsten Prognose 1T (nicht mehr nur die, die den `sellSignal()==='verkaufen'`-Schwellenwert unterschreiten) — auch wenn alle drei Werte positiv sind. Der Badge pro Karte ("Jetzt verkaufen"/"Noch halten"/"Unklar") zeigt weiterhin das echte Signal, damit ein positiver Wert nicht faelschlich als "verkaufen" markiert wird.

**Architecture:** Aenderung ausschliesslich in `buildDashboardSellCandidates()` (`derive.ts`) — von Filter auf Ranking umgestellt, liefert direkt `EigenesTeamRow[]` (inkl. echtem `sell_signal`) statt `PlayerRow[]`. `DashboardTab.tsx` vereinfacht sich dadurch (der bisherige, jetzt fehlerhafte Schritt, der pauschal `sell_signal: "verkaufen"` aufklebte, entfaellt komplett).

## Kontext

Direktes User-Feedback (Chat, 2026-08-03, nach Live-Test des Dashboards): "Es sollten immer die Top3
Verkaufskandidaten angezeigt werden, vor allem wenn der Kader voll ist. Das sind dann die die geringste
Marktwertentwicklung haben, auch wenn diese positiv sein sollte." Im Chat geklaert: Ranking-Metrik ist die
ML-Prognose 1T (`ml_prediction`) — dieselbe Metrik, die auch `sellSignal()` treibt, nicht der bereits realisierte
7-Tage-Trend.

Aktuelle (zu ersetzende) Implementierung (`derive.ts:395-406`):

```ts
export function buildDashboardSellCandidates(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  calibration: Calibration | null,
  mae: number | null
): PlayerRow[] {
  return ownSquadIds
    .map((pid) => players[pid])
    .filter((p): p is PlayerRecord => !!p)
    .map((p) => buildPlayerRow(p, calibration))
    .filter((row) => sellSignal(row.ml_prediction, mae) === "verkaufen");
}
```

`DashboardTab.tsx` klebt aktuell (Zeile ~37-38) pauschal `sell_signal: "verkaufen"` auf jede zurueckgegebene Zeile —
das war bisher richtig, weil die Funktion nur echte "verkaufen"-Faelle zurueckgab. Nach dieser Aenderung waere das
FALSCH (ein Top-3-Kandidat mit positiver Prognose wuerde faelschlich als "Jetzt verkaufen" angezeigt) — deshalb
liefert die Funktion das Signal jetzt selbst mit, `DashboardTab.tsx` klebt nichts mehr auf.

## Task 1: `buildDashboardSellCandidates()` auf Ranking umstellen

**Files:**
- Modify: `frontend/src/lib/derive.ts`
- Test: `frontend/src/lib/derive.test.ts`
- Modify: `frontend/src/components/DashboardTab.tsx`

**Interfaces:**
- Neue Signatur/Rueckgabetyp: `buildDashboardSellCandidates(players, ownSquadIds, calibration, mae):
  EigenesTeamRow[]` (vorher `PlayerRow[]`) — `EigenesTeamRow` bereits vorhanden (`derive.ts`, `PlayerRow &
  {sell_signal?: ...}`).

- [ ] **Step 1: Bestehenden Test durch die neuen Faelle ersetzen**

In `frontend/src/lib/derive.test.ts`, den bestehenden `describe("buildDashboardSellCandidates", ...)`-Block (Zeile
126-135) ersetzen durch:

```ts
describe("buildDashboardSellCandidates", () => {
  const players = {
    p1: { player_id: "p1", name: "A", position: "Sturm", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: -50_000, ml_prediction_3d: -100_000 },
    p2: { player_id: "p2", name: "B", position: "Abwehr", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: 50_000, ml_prediction_3d: 100_000 },
    p3: { player_id: "p3", name: "C", position: "Mittelfeld", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: 10_000, ml_prediction_3d: 20_000 },
    p4: { player_id: "p4", name: "D", position: "Torwart", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: 200_000, ml_prediction_3d: 300_000 },
  };

  it("returns the 3 lowest-Prognose-1T players even when all values are positive", () => {
    const result = buildDashboardSellCandidates(players, ["p1", "p2", "p3", "p4"], null, null);
    expect(result.map((r) => r.player_id)).toEqual(["p1", "p3", "p2"]);
  });

  it("attaches the real sellSignal per row instead of hardcoding 'verkaufen'", () => {
    // mae=30_000: p1 (-50k) klar unter der Schwelle -> "verkaufen", p3 (10k) innerhalb
    // der Ungenauigkeit -> "unklar", p2 (50k) klar darueber -> "halten".
    const result = buildDashboardSellCandidates(players, ["p1", "p2", "p3", "p4"], null, 30_000);
    expect(result.map((r) => r.sell_signal)).toEqual(["verkaufen", "unklar", "halten"]);
  });

  it("returns fewer than 3 rows if fewer than 3 owned players have a prediction", () => {
    const onePlayer = { p1: players.p1 };
    const result = buildDashboardSellCandidates(onePlayer, ["p1"], null, null);
    expect(result.map((r) => r.player_id)).toEqual(["p1"]);
  });

  it("excludes players without a 1T prediction from the ranking", () => {
    const withNull = { ...players, p5: { ...players.p4, player_id: "p5", ml_prediction: null } };
    const result = buildDashboardSellCandidates(withNull, ["p1", "p2", "p3", "p4", "p5"], null, null);
    expect(result.map((r) => r.player_id)).not.toContain("p5");
  });
});
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestaetigen**

Run: `cd frontend && npm run test`
Expected: FAIL (alte Implementierung filtert noch, liefert kein `sell_signal`-Feld, falsche Reihenfolge/Anzahl).

- [ ] **Step 3: `buildDashboardSellCandidates()` neu implementieren**

In `frontend/src/lib/derive.ts`, die bestehende Funktion (Zeile 395-406) ersetzen durch:

```ts
export function buildDashboardSellCandidates(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  calibration: Calibration | null,
  mae: number | null
): EigenesTeamRow[] {
  return ownSquadIds
    .map((pid) => players[pid])
    .filter((p): p is PlayerRecord => !!p)
    .map((p) => buildPlayerRow(p, calibration))
    .filter((row) => row.ml_prediction !== null)
    .sort((a, b) => (a.ml_prediction ?? 0) - (b.ml_prediction ?? 0))
    .slice(0, 3)
    .map((row) => ({ ...row, sell_signal: sellSignal(row.ml_prediction, mae) }));
}
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestaetigen**

Run: `cd frontend && npm run test`
Expected: alle Tests gruen.

- [ ] **Step 5: `DashboardTab.tsx` vereinfachen — die fehlerhafte `sell_signal`-Aufklebung entfernen**

Die bestehende Zeile

```ts
  const sellCandidatesWithSignal: EigenesTeamRow[] = sellCandidates.map((r) => ({ ...r, sell_signal: "verkaufen" as const }));
```

komplett entfernen. Jede weitere Verwendung von `sellCandidatesWithSignal` im Rest der Datei durch `sellCandidates`
ersetzen (die Variable heisst nach dieser Aenderung direkt `sellCandidates`, da `buildDashboardSellCandidates()`
jetzt selbst `EigenesTeamRow[]` mit korrektem `sell_signal` liefert — keine Nachbearbeitung mehr noetig).

- [ ] **Step 6: Typecheck + volle Vitest-Suite + Build**

Run: `cd frontend && npm run typecheck && npm run test -- --run && npm run build`
Expected: alle drei erfolgreich.

- [ ] **Step 7: Manueller Dev-Server-Check**

Dev-Server starten, Dashboard-Tab oeffnen: Verkaufen-Sektion zeigt immer genau 3 Karten (sofern der Kader
mindestens 3 Spieler mit vorhandener Prognose hat), sortiert nach Prognose 1T aufsteigend — auch wenn alle drei
Werte positiv sind. Badge pro Karte zeigt das jeweils korrekte Signal ("Jetzt verkaufen"/"Unklar"/"Noch halten"),
nicht pauschal "Jetzt verkaufen".

- [ ] **Step 8: PR statt Direkt-Push (verbindliche Regel seit 2026-08-03, siehe [[project_kickbaseagent_git_workflow]])**

```bash
git checkout -b dashboard-verkaufen-top3
git add frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts frontend/src/components/DashboardTab.tsx
git commit -m "Dashboard-Verkaufen: immer Top-3 nach Prognose 1T statt Signal-Filter"
git push -u origin dashboard-verkaufen-top3
gh pr create --title "Dashboard-Verkaufen: immer Top-3 nach Prognose 1T" --body "Siehe docs/superpowers/plans/2026-08-03-dashboard-sell-top3.md"
gh pr merge --auto --squash
```

Auf die 4 Required Checks warten (`pytest`, `typecheck-and-unit-tests`, `component-tests`, `e2e-touch-swipe`) —
Auto-Merge greift automatisch, sobald alle gruen sind.

## Verification

- `npm run typecheck`, `npm run test -- --run` (alle Tests inkl. der 4 neuen Faelle), `npm run build`.
- Backend unberuehrt (reine Frontend-Aenderung), Backend-Suite laeuft trotzdem als Required Check auf dem PR mit.
- Manuell wie in Step 7.

## Out of Scope

- Kaufen-/Investment-Sektionen bleiben unveraendert (dieses Feedback betraf ausschliesslich Verkaufen).
- Kein neuer Schwellenwert/Parameter — reines Ranking, keine Konfigurierbarkeit der Top-N-Zahl (fest auf 3).
