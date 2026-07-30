# Ligaanalyse-Detailansicht Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Klick auf eine Manager-Karte im Ligaanalyse-Tab (eigene wie gegnerische) öffnet ein Detail-Modal mit kurzem Info-Header + einer nach Position gruppierten Kaderliste — basierend auf `docs/superpowers/specs/2026-07-30-ligaanalyse-detailansicht-design.md`.

**Architecture:** Kein neuer Kickbase-API-Call. `_build_ligaanalyse()` ergänzt pro Row ein Feld `squad_player_ids: list[str]`, gespeist aus Daten, die schon jetzt für die Aggregat-Werte abgerufen werden (`get_manager_squad()` für Gegner, `own_squad` für die eigene Zeile). Das Frontend löst Name/Position/Marktwert/Stammspieler-Status für jede ID über das bereits vorhandene `data.players` auf (players-Map-Pattern: Backend liefert rohe IDs, Ableitung passiert client-seitig).

**Tech Stack:** Python 3.11 (Backend, `src/`), TypeScript/React (Frontend, `frontend/src/`), `unittest` (Backend-Tests). Kein Test-Framework im Frontend — Verifikation über `tsc --noEmit`.

## Global Constraints

- **Vorbedingung (wichtig):** Dieser Plan setzt voraus, dass `docs/superpowers/plans/2026-07-30-gebotsvorschlaege.md` bereits vollständig umgesetzt und gemergt ist — insbesondere dessen Task 7 (`_build_ligaanalyse()` nimmt `players_map` als letzten Parameter, liefert `{"rows": [...], "position_need": {...}}`, `tests/test_dashboard_export.py` enthält bereits die Klasse `BuildLigaanalyseTests` mit den Hilfsmethoden `_players_map()`/`_ranking_row()`). **Vor Task 1 prüfen:** `grep -n "class BuildLigaanalyseTests" tests/test_dashboard_export.py`. Kommt kein Treffer, ist die Vorbedingung nicht erfüllt — dann zuerst den Gebotsvorschläge-Plan fertigstellen/mergen, nicht diesen Task blind gegen die alte Signatur schreiben.
- **Backend-Tests**: `python3 -m unittest discover -s tests -v` aus dem Repo-Root, muss nach Task 1 grün bleiben.
- **Frontend-Verifikation**: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` nach jedem Frontend-Task.
- **Kein Push in dieser Session** — Commits bleiben lokal (Standing-Rule `NeverPushOnMain`), der Repo-Owner pusht selbst.
- **Keine zusätzlichen Spieler-Attribute** (Punkteschnitt, ML-Prognose, Trend) in der Kaderliste — bewusst nicht Teil des Designs (siehe Spec, Out of Scope).
- **Defensive Fallbacks an neuen Frontend-Feldern**: `row.squad_player_ids ?? []` an der Konsumstelle — Lektion aus dem White-Screen-Vorfall (siehe `HANDOFF.md`): ein Frontend-Deploy kann live gehen, bevor der Backend-Cron das neue Feld je geschrieben hat.

---

## Datei-Übersicht

| Datei | Rolle |
|---|---|
| `src/dashboard_export.py` | `_build_ligaanalyse()` ergänzt `squad_player_ids` pro Row |
| `tests/test_dashboard_export.py` | `BuildLigaanalyseTests` um 3 neue Testfälle erweitert |
| `frontend/src/types.ts` | `LigaanalyseRow` bekommt `squad_player_ids: string[]` |
| `frontend/src/lib/derive.ts` | NEU: `groupSquadByPosition()` + `SquadListEntry`-Typ |
| `frontend/src/components/LigaanalyseTab.tsx` | Karte klickbar, neues `LigaanalyseDetailModal` |

---

## Task 1: `_build_ligaanalyse()` — `squad_player_ids` pro Row

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py`

**Interfaces:**
- Produces: `LigaanalyseRow`-Dict bekommt zusätzliches Feld `"squad_player_ids": list[str]`. Konsumiert von Task 2 (Frontend-Typ).

- [ ] **Step 1: Precondition check**

Run: `grep -n "class BuildLigaanalyseTests" tests/test_dashboard_export.py`
Expected: ein Treffer. Kein Treffer → STOP, siehe Global Constraints.

- [ ] **Step 2: Write the failing tests**

In `tests/test_dashboard_export.py`, in die bestehende Klasse `BuildLigaanalyseTests` ergänzen (nutzt deren bereits vorhandene Hilfsmethoden `_players_map()` und `_ranking_row()` unverändert):

```python
    def test_self_row_gets_squad_player_ids_from_own_squad(self):
        ranking_rows = [self._ranking_row("u_self", "Ich", ["p1"])]
        budget_rows = [
            {"user_id": "u_self", "is_own_exact": True, "estimated_budget": 1, "available_budget": 1, "trade_count": 0}
        ]

        result = _build_ligaanalyse(
            "tok", "l1", ranking_rows, budget_rows, market_listings=[],
            own_squad=[
                {"player_id": "p1", "market_value": 1, "starting_rank": 1},
                {"player_id": "p4", "market_value": 1, "starting_rank": 2},
            ],
            players_map=self._players_map(),
        )

        self.assertEqual(result["rows"][0]["squad_player_ids"], ["p1", "p4"])

    def test_rival_row_gets_squad_player_ids_from_manager_squad(self):
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p1"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.return_value = {"it": [{"pi": "p2"}, {"pi": "p3"}], "nps": 2}
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertEqual(result["rows"][0]["squad_player_ids"], ["p2", "p3"])

    def test_rival_row_squad_player_ids_empty_on_kickbase_error(self):
        ranking_rows = [self._ranking_row("u1", "Rivale", ["p1"])]
        budget_rows = [{"user_id": "u1", "is_own_exact": False}]

        with patch("src.dashboard_export.get_manager_squad") as mock_squad:
            mock_squad.side_effect = KickbaseError("down")
            result = _build_ligaanalyse(
                "tok", "l1", ranking_rows, budget_rows, market_listings=[], own_squad=[],
                players_map=self._players_map(),
            )

        self.assertEqual(result["rows"][0]["squad_player_ids"], [])
```

Import-Ergänzung am Dateikopf (falls `KickbaseError` dort noch nicht importiert ist):

```python
from src.kickbase_client import KickbaseError
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard_export.BuildLigaanalyseTests -v`
Expected: FAIL (`KeyError: 'squad_player_ids'`) für die drei neuen Tests, Rest weiterhin PASS.

- [ ] **Step 4: Implement**

In `src/dashboard_export.py`, in `_build_ligaanalyse()`:

Im `if is_self:`-Zweig, direkt nach der bestehenden `regular_count = ...`-Zeile ergänzen:

```python
            squad_player_ids = [p["player_id"] for p in own_squad]
```

Im `else:`-Zweig (Gegner), direkt nach der bestehenden Zeile `squad_players = [players_map.get(item.get("pi")) for item in items]` ergänzen:

```python
                squad_player_ids = [item.get("pi") for item in items]
```

Im `except KickbaseError as exc:`-Zweig, die bestehende Zeile

```python
                squad_size, squad_value, regular_count = None, None, None
```

ersetzen durch:

```python
                squad_size, squad_value, regular_count = None, None, None
                squad_player_ids = []
```

Im `rows.append({...})`-Dict, nach dem bestehenden Feld `"regular_count": regular_count,` ergänzen:

```python
                "squad_player_ids": squad_player_ids,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard_export.BuildLigaanalyseTests -v`
Expected: PASS (alle Tests der Klasse)

- [ ] **Step 6: Run full backend suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: grün

- [ ] **Step 7: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: _build_ligaanalyse() liefert squad_player_ids pro Row"
```

---

## Task 2: `types.ts` — `LigaanalyseRow.squad_player_ids`

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Produces: `LigaanalyseRow.squad_player_ids: string[]`. Konsumiert von Task 3 (`derive.ts`) und Task 4 (`LigaanalyseTab.tsx`).

- [ ] **Step 1: Extend the interface**

In `frontend/src/types.ts`, in `LigaanalyseRow` nach `regular_count: number | null;` ergänzen:

```ts
  squad_player_ids: string[];
```

- [ ] **Step 2: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "types.ts: LigaanalyseRow.squad_player_ids"
```

---

## Task 3: `derive.ts` — `groupSquadByPosition()`

**Files:**
- Modify: `frontend/src/lib/derive.ts`

**Interfaces:**
- Consumes: `LigaanalyseRow.squad_player_ids` (Task 2), `DashboardSnapshot.players` (bereits vorhanden).
- Produces: `SquadListEntry`, `groupSquadByPosition(playerIds, players) -> { position: string; entries: SquadListEntry[] }[]`. Konsumiert von Task 4.

- [ ] **Step 1: Implement**

In `frontend/src/lib/derive.ts` ergänzen (Import von `PlayerRecord` aus `../types` prüfen, ist in dieser Datei bereits vorhanden für andere Builder-Funktionen):

```ts
export interface SquadListEntry {
  player_id: string;
  name: string;
  position: string;
  market_value: number | null;
  is_regular: boolean;
}

const SQUAD_POSITION_ORDER = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];

// is_regular-Schwelle (starting_rank 1/2) identisch zum bestehenden
// Ligaanalyse-Hint-Text ("Stammspieler = starting_rank 1 oder 2").
export function groupSquadByPosition(
  playerIds: string[],
  players: Record<string, PlayerRecord>
): { position: string; entries: SquadListEntry[] }[] {
  const entries: SquadListEntry[] = playerIds
    .map((id) => players[id])
    .filter((p): p is PlayerRecord => !!p)
    .map((p) => ({
      player_id: p.player_id,
      name: p.name,
      position: p.position,
      market_value: p.market_value,
      is_regular: p.starting_rank === 1 || p.starting_rank === 2,
    }));

  return SQUAD_POSITION_ORDER.map((position) => ({
    position,
    entries: entries
      .filter((e) => e.position === position)
      .sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0)),
  })).filter((group) => group.entries.length > 0);
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 3: Manual sanity check (kein Test-Framework im Frontend)**

Kurz im Kopf durchgehen: leere `playerIds`-Liste → `[]` zurück (kein Crash, da `.map()`/`.filter()` auf leerem Array sicher sind). ID ohne Treffer in `players` → durch `.filter((p): p is PlayerRecord => !!p)` stillschweigend entfernt.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/derive.ts
git commit -m "derive.ts: groupSquadByPosition() - Kaderliste gruppiert nach Position"
```

---

## Task 4: `LigaanalyseTab.tsx` — Karte klickbar + Detail-Modal

**Files:**
- Modify: `frontend/src/components/LigaanalyseTab.tsx`

**Interfaces:**
- Consumes: `groupSquadByPosition` (Task 3), `LigaanalyseRow.squad_player_ids` (Task 2), `data.players`.

- [ ] **Step 1: Add click state and wire up the card**

Imports ergänzen:

```ts
import { useEffect, useMemo, useState } from "react";
import type { DashboardSnapshot, LigaanalyseRow } from "../types";
import { groupSquadByPosition } from "../lib/derive";
import { Badge, POSITION_ABBR, Row } from "./ui";
import { fmtNum } from "../format";
```

In `LigaanalyseTab`, State ergänzen und an die Karte durchreichen:

```tsx
export default function LigaanalyseTab({ data }: { data: DashboardSnapshot }) {
  const allRows = data.ligaanalyse ?? [];
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LigaanalyseRow | null>(null);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? allRows.filter((r) => r.name.toLowerCase().includes(q)) : allRows;
  }, [allRows, search]);

  return (
    <div>
      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Manager suchen…"
          className="min-w-[200px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
        {visible.map((r) => (
          <LigaanalyseCard key={r.name} row={r} onClick={() => setSelected(r)} />
        ))}
      </div>
      <p className="mt-4 max-w-3xl text-xs text-slate-500 dark:text-slate-400">{HINT}</p>
      {selected && (
        <LigaanalyseDetailModal row={selected} players={data.players} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
```

`LigaanalyseCard` bekommt `onClick`-Prop und gibt es an den Wrapper-`div` weiter:

```tsx
function LigaanalyseCard({ row, onClick }: { row: LigaanalyseRow; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      className={`cursor-pointer rounded-2xl border p-4 shadow-sm transition hover:shadow-md dark:bg-slate-900 ${
        row.is_self ? "border-brand-400 bg-brand-50 dark:border-brand-600 dark:bg-brand-950/30" : "border-slate-200 bg-white dark:border-slate-800"
      }`}
    >
```

(Rest der Funktion unverändert.)

- [ ] **Step 2: Implement `LigaanalyseDetailModal`**

Am Ende der Datei ergänzen (Muster 1:1 von `SpekulationDetailModal` in `SpekulationTab.tsx` übernommen):

```tsx
function LigaanalyseDetailModal({
  row,
  players,
  onClose,
}: {
  row: LigaanalyseRow;
  players: DashboardSnapshot["players"];
  onClose: () => void;
}) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const groups = groupSquadByPosition(row.squad_player_ids ?? [], players);

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{row.name}</span>
            {row.is_self && <Badge tone="good">ich</Badge>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Schließen"
            className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ✕
          </button>
        </div>
        <dl className="mb-4 space-y-1.5 text-sm">
          <Row label="Platz">{fmtNum(row.season_placement)}</Row>
          <Row label="Punkte">{fmtNum(row.season_points)}</Row>
          <Row label={row.is_self ? "Budget" : "Budget (geschätzt)"}>{fmtNum(row.estimated_budget)}</Row>
        </dl>
        {groups.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">Keine Kaderdaten verfügbar.</p>
        ) : (
          <div className="space-y-3">
            {groups.map((group) => (
              <div key={group.position}>
                <p className="mb-1 text-xs font-semibold uppercase text-slate-400 dark:text-slate-500">
                  {POSITION_ABBR[group.position] ?? group.position}
                </p>
                <ul className="space-y-1">
                  {group.entries.map((entry) => (
                    <li key={entry.player_id} className="flex items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-2 text-slate-700 dark:text-slate-200">
                        {entry.name}
                        {entry.is_regular && <Badge tone="good">Stamm</Badge>}
                      </span>
                      <span className="text-slate-500 dark:text-slate-400">{fmtNum(entry.market_value)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 neue Fehler

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LigaanalyseTab.tsx
git commit -m "LigaanalyseTab: Karte klickbar, Detail-Modal mit Kaderliste nach Position"
```

---

## Task 5: Live-Verifikation (manuelle Schritte, kein Code)

**Files:** keine (operative Schritte gegen die echte Produktionsumgebung)

- [ ] **Step 1**: Backend- und Frontend-Commits pushen (User macht das selbst).
- [ ] **Step 2**: `gh workflow run dashboard.yml` (Light reicht — `squad_player_ids` wird bei jedem Lauf frisch aus `get_manager_squad()`/`own_squad` gebaut, keine Backfill-Logik nötig) manuell anstoßen, `gh run watch <run-id> --exit-status` abwarten.
- [ ] **Step 3**: Live prüfen: `dashboard_snapshot/latest`'s `ligaanalyse`-Einträge haben ein `squad_player_ids`-Array mit Spieler-IDs.
- [ ] **Step 4**: Echter Browser-Test durch den User (Sandbox kann kein `npm run dev`): Ligaanalyse-Tab → beliebige Karte (eigene und gegnerische) anklicken → Modal öffnet mit Platz/Punkte/Budget-Header + nach Position gruppierter Kaderliste, Stammspieler mit "Stamm"-Badge markiert. Escape/Klick außerhalb schließt das Modal.

---

## Self-Review-Notiz (bereits durchgeführt)

- **Spec-Abdeckung**: Backend-Feld, Frontend-Ableitung, UI-Platzierung (Karte klickbar + Modal), Edge Cases (leer, Fetch-Fehler, fehlende Spieler-ID) — alle Abschnitte der Spec haben eine Task/einen Step.
- **Platzhalter-Scan**: keine TBD/"analog zu Task N ohne Code" gefunden.
- **Typ-Konsistenz**: `squad_player_ids` gleich benannt zwischen Task 1 (Backend), Task 2 (`types.ts`), Task 3 (`derive.ts`-Parameter) und Task 4 (Konsumstelle). `SquadListEntry`/`groupSquadByPosition` gleich benannt zwischen Task 3 und Task 4.
- **Out of Scope aus der Spec respektiert**: keine zusätzlichen Spieler-Attribute (Punkteschnitt/ML-Prognose/Trend) in der Kaderliste, keine Sortierung/Filterung innerhalb des Modals.
