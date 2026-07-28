# Phase 6 Sub-Projekt 2 (Wunschkader-Migration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Wunschkader tab from the legacy `index.html` to the new React/Vite/Tailwind `frontend/`, with position-grouped card layout (formation-aware slots + bank section), full editing (add/remove/replace/bench-toggle/save), and two simplified budget-plan formulas (flat 10% markup, no login-bonus).

**Architecture:** Same pattern as the Spekulation pilot (Sub-Projekt 1): a single React component (`WunschkaderTab.tsx`) receives already-fetched Firestore snapshot data as props, holds all edits in local React state, and writes back to Firestore only on an explicit "Speichern" click. No new backend endpoints. Two backend Python functions get a business-logic simplification that affects both the old and new frontend (both read the same Firestore document).

**Tech Stack:** Python 3 (stdlib `unittest`) for the backend task. React 18 + TypeScript + Tailwind CSS (existing `frontend/` project) for the UI tasks — no new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-28-phase6-sub2-wunschkader-design.md` (approved by user) — this plan implements it in full.
- **No `npm install`/`npm run` in this sandbox** (known Windows-DrvFs-mount issue) — verify frontend tasks via manual review + bracket-balance check only (`(){}[]` count script, see Task 2/3/4/5/6 verification steps). Real build/typecheck happens in CI or the user's local Rider/Windows setup.
- Python task IS runnable here: verify with `python3 -m unittest tests.test_dashboard_export -v`.
- **Commits stay local, never pushed** (`NeverPushOnMain` ruleset on this repo) — commit after each task, do not run `git push`.
- The legacy `index.html` Wunschkader tab AND its Eigenes-Team-tab watchlist read the exact same `_build_wunschkader()` output and the exact same Firestore document (`wunschkader/current`) as the new frontend. Every target object written by the new frontend **must** include an explicit `role` key (`"Starter"` or `"Bank/Backup-Option"`) — `_build_wunschkader()` accesses `target["role"]` directly (no `.get()`), so an omitted key raises `KeyError` and breaks the whole pipeline, including the still-live old page.
- German UI text throughout (matches rest of `frontend/`), with proper umlauts (ä/ö/ü/ß), matching the existing convention in `SpekulationTab.tsx`.

---

### Task 1: Backend — flat 10% markup + drop login-bonus from budget plan

**Files:**
- Modify: `src/dashboard_export.py:364-373` (`_estimate_price`)
- Modify: `src/dashboard_export.py:376-447` (`_build_wunschkader`, only the call site at line 423 and the now-dead `markup_rules` local at line 386)
- Modify: `src/dashboard_export.py:450-473` (`_project_login_bonus` — delete entirely)
- Modify: `src/dashboard_export.py:507-551` (`_build_budget_plan`)
- Modify: `src/dashboard_export.py:624-626` (call site in `export()`)
- Test: `tests/test_dashboard_export.py`

**Interfaces:**
- Consumes: nothing new (pure refactor of existing private functions).
- Produces: `_estimate_price(market_value: float | None) -> float | None` (param `markup_rules` removed). `_build_budget_plan(wunschkader: dict, wunschkader_rows: list[dict], own_squad: list, own_budget_exact: float | None) -> dict` (param `fetched_at` removed, return dict no longer has `login_bonus_projection`/`season_start` keys). Both consumed by later frontend tasks only as documented shapes (`BudgetPlan` TypeScript type in Task 2), not called directly from JS.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard_export.py` (new imports + two new test classes). First update the import line near the top of the file:

```python
from src.dashboard_export import (
    _build_alle_spieler,
    _build_budget_plan,
    _build_spekulation,
    _build_transfermarkt,
    _estimate_price,
    _load_wunschkader,
)
```

Then add these test classes (anywhere after the existing `BuildTransfermarktTests` class, before `LoadWunschkaderTests`):

```python
class EstimatePriceTests(unittest.TestCase):
    def test_flat_ten_percent_markup(self):
        self.assertEqual(_estimate_price(10_000_000), 11_000_000)

    def test_returns_none_without_market_value(self):
        self.assertIsNone(_estimate_price(None))

    def test_returns_none_for_zero_market_value(self):
        self.assertIsNone(_estimate_price(0))


class BuildBudgetPlanTests(unittest.TestCase):
    def test_pool_has_no_login_bonus(self):
        wunschkader = {"sell_list": []}

        result = _build_budget_plan(wunschkader, wunschkader_rows=[], own_squad=[], own_budget_exact=1_000_000)

        self.assertEqual(result["pool"], 1_000_000)
        self.assertNotIn("login_bonus_projection", result)
        self.assertNotIn("season_start", result)

    def test_committed_excludes_bank_backup_and_own_targets(self):
        wunschkader = {"sell_list": []}
        wunschkader_rows = [
            {"planned_price": 5_000_000, "role": "Starter", "is_own": False},
            {"planned_price": 3_000_000, "role": "Bank/Backup-Option", "is_own": False},
            {"planned_price": 9_000_000, "role": "Starter", "is_own": True},
        ]

        result = _build_budget_plan(wunschkader, wunschkader_rows, own_squad=[], own_budget_exact=0)

        self.assertEqual(result["committed"], 5_000_000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard_export -v`
Expected: `EstimatePriceTests` fail with `TypeError: _estimate_price() missing 1 required positional argument: 'markup_rules'` (current signature still takes two params), `BuildBudgetPlanTests` fail with `TypeError: _build_budget_plan() missing 1 required positional argument: 'fetched_at'` (current signature still requires it).

- [ ] **Step 3: Simplify `_estimate_price`**

Replace (`src/dashboard_export.py:364-373`):

```python
def _estimate_price(market_value: float | None, markup_rules: dict | None) -> float | None:
    """Marktwert x Aufschlag - Topspieler (Marktwert >= Schwelle) bekommen
    einen hoeheren Aufschlag als der Rest. Live verifiziert 27.07.2026 gegen
    echte Trades (siehe markup_rules.note in wunschkader.json): Kimmich
    (Topspieler) +8,86% ueber Marktwert, Jeltsch (Normalspieler) +4,94%."""
    if not market_value or not markup_rules:
        return None
    threshold = markup_rules.get("topspieler_threshold", 0)
    markup = markup_rules.get("topspieler_markup" if market_value >= threshold else "normal_markup", 0)
    return round(market_value * (1 + markup))
```

with:

```python
def _estimate_price(market_value: float | None) -> float | None:
    """Pauschaler 10%-Aufschlag auf den Marktwert - ersetzt das fruehere
    2-Stufen-Topspieler-System (User-Wunsch 28.07.2026: eine schnell im
    Kopf nachrechenbare Schaetzung statt Praezision)."""
    if not market_value:
        return None
    return round(market_value * 1.10)
```

- [ ] **Step 4: Update the call site and drop the now-dead `markup_rules` local in `_build_wunschkader`**

In `_build_wunschkader` (`src/dashboard_export.py:376-447`), remove line 386 entirely:

```python
    markup_rules = wunschkader.get("markup_rules")
```

And change line 423 from:

```python
            planned_price = _estimate_price(market_value, markup_rules)
```

to:

```python
            planned_price = _estimate_price(market_value)
```

- [ ] **Step 5: Delete `_project_login_bonus` and simplify `_build_budget_plan`**

Delete the entire function at `src/dashboard_export.py:450-473`:

```python
def _project_login_bonus(login_cfg: dict | None, season_start: str | None, fetched_at: str) -> int:
    """Projiziert die verbleibende Login-Praemie bis Saisonstart (nur
    zukuenftige Tage, der heutige/vergangene Betrag steckt schon im
    aktuellen Kontostand). Setzt eine ununterbrochene taegliche
    Login-Streak voraus - reine Schaetzung, siehe login_bonus.note in
    wunschkader.json."""
    if not login_cfg or not login_cfg.get("observed") or not season_start:
        return 0
    observed = sorted(login_cfg["observed"], key=lambda o: o["date"])
    last_date = datetime.date.fromisoformat(observed[-1]["date"])
    amount = observed[-1]["amount"]
    increment = login_cfg.get("daily_increment", 0)
    cap = login_cfg.get("assumed_cap", amount)
    season_start_date = datetime.date.fromisoformat(season_start)
    today = datetime.date.fromisoformat(fetched_at)

    total = 0
    current_date = last_date
    while current_date < season_start_date:
        current_date += datetime.timedelta(days=1)
        amount = min(amount + increment, cap)
        if current_date > today:
            total += amount
    return total
```

Replace `_build_budget_plan` (`src/dashboard_export.py:507-551`), currently:

```python
def _build_budget_plan(
    wunschkader: dict,
    wunschkader_rows: list[dict],
    own_squad: list,
    own_budget_exact: float | None,
    fetched_at: str,
) -> dict:
    own_squad_by_name = {r["name"]: r for r in own_squad}
    sell_rows = [
        {"name": name, "market_value": own_squad_by_name[name]["market_value"]}
        for name in wunschkader.get("sell_list", [])
        if name in own_squad_by_name
    ]
    sell_proceeds = sum((r["market_value"] or 0) for r in sell_rows)

    login_bonus_projection = _project_login_bonus(
        wunschkader.get("login_bonus"), wunschkader.get("season_start"), fetched_at
    )

    cash = own_budget_exact or 0
    pool = cash + sell_proceeds + login_bonus_projection

    # Bank/Backup-Option-Rollen sind nur bedingter Bedarf, nicht fest verplant.
    # Schon im Kader befindliche Ziele (is_own) nicht mitzaehlen - deren Kauf
    # ist bereits im aktuellen Kontostand (cash) abgezogen, sonst wuerde ein
    # per actual_bid dokumentierter historischer Gebotsbetrag (z.B. Stage,
    # Klaus) nach dem erfolgreichen Kauf ein zweites Mal als noch offene
    # Ausgabe gezaehlt (live gefunden 27.07.2026, hat den Fehlbetrag um genau
    # die Summe dieser bereits bezahlten Spieler verfaelscht).
    committed = sum(
        (r["planned_price"] or 0)
        for r in wunschkader_rows
        if r["role"] not in ("Bank/Backup-Option",) and not r["is_own"]
    )

    return {
        "cash": cash,
        "sell_rows": sell_rows,
        "sell_proceeds": sell_proceeds,
        "login_bonus_projection": login_bonus_projection,
        "season_start": wunschkader.get("season_start"),
        "pool": pool,
        "committed": committed,
        "remaining": pool - committed,
    }
```

with:

```python
def _build_budget_plan(
    wunschkader: dict,
    wunschkader_rows: list[dict],
    own_squad: list,
    own_budget_exact: float | None,
) -> dict:
    own_squad_by_name = {r["name"]: r for r in own_squad}
    sell_rows = [
        {"name": name, "market_value": own_squad_by_name[name]["market_value"]}
        for name in wunschkader.get("sell_list", [])
        if name in own_squad_by_name
    ]
    sell_proceeds = sum((r["market_value"] or 0) for r in sell_rows)

    cash = own_budget_exact or 0
    pool = cash + sell_proceeds

    # Bank/Backup-Option-Rollen sind nur bedingter Bedarf, nicht fest verplant.
    # Schon im Kader befindliche Ziele (is_own) nicht mitzaehlen - deren Kauf
    # ist bereits im aktuellen Kontostand (cash) abgezogen, sonst wuerde ein
    # per actual_bid dokumentierter historischer Gebotsbetrag (z.B. Stage,
    # Klaus) nach dem erfolgreichen Kauf ein zweites Mal als noch offene
    # Ausgabe gezaehlt (live gefunden 27.07.2026, hat den Fehlbetrag um genau
    # die Summe dieser bereits bezahlten Spieler verfaelscht).
    committed = sum(
        (r["planned_price"] or 0)
        for r in wunschkader_rows
        if r["role"] not in ("Bank/Backup-Option",) and not r["is_own"]
    )

    return {
        "cash": cash,
        "sell_rows": sell_rows,
        "sell_proceeds": sell_proceeds,
        "pool": pool,
        "committed": committed,
        "remaining": pool - committed,
    }
```

- [ ] **Step 6: Update the call site in `export()`**

In `export()` (`src/dashboard_export.py:624-626`), change:

```python
    budget_plan = (
        _build_budget_plan(
            wunschkader_config, wunschkader_rows, own_squad, own_budget_row["estimated_budget"] if own_budget_row else None, fetched_at
        )
        if wunschkader_config
        else None
    )
```

to:

```python
    budget_plan = (
        _build_budget_plan(
            wunschkader_config, wunschkader_rows, own_squad, own_budget_row["estimated_budget"] if own_budget_row else None
        )
        if wunschkader_config
        else None
    )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_dashboard_export -v`
Expected: all tests pass (14 total: 9 existing + 5 new — 3 methods in `EstimatePriceTests`, 2 methods in `BuildBudgetPlanTests`).

- [ ] **Step 8: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "Wunschkader-Budget: pauschaler 10%-Aufschlag statt 2-Stufen-Markup, Login-Praemie aus Pool-Berechnung entfernt"
```

---

### Task 2: Frontend shared modules — types, formations, extracted UI primitives

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/lib/formations.ts`
- Create: `frontend/src/components/ui.tsx`
- Modify: `frontend/src/components/SpekulationTab.tsx` (remove now-duplicated definitions, import from `ui.tsx` instead)

**Interfaces:**
- Consumes: nothing new.
- Produces: `WunschkaderRow`, `BudgetPlan`, `AlleSpielerRow`, `RawWunschkaderTarget` types (Task 3-6 import these from `../types`). `FORMATIONS`, `FORMATION_KEYS`, `FormationKey`, `POSITIONS`, `Position`, `slotsFor(formation, position)` (Task 3 imports from `../lib/formations`). `Row`, `Badge` (tones `"good" | "warn" | "crit"`), `TeamCrest`, `SignalBadge` (Task 3-4 import from `./ui` — note: relative to `components/`, so `SpekulationTab.tsx`/`WunschkaderTab.tsx` both import as `./ui`).

- [ ] **Step 1: Extend `frontend/src/types.ts`**

Replace the full file content with:

```ts
export interface SpekulationRow {
  name: string;
  position: string;
  team_name: string | null;
  price: number;
  roi_pct: number;
  average_points: number | null;
  market_value_change_7d: number | null;
  market_value_low_92d: number | null;
  market_value_high_92d: number | null;
  ml_prediction: number | null;
  auction_status: string | null;
  auction_urgent: boolean;
  auction_remaining_seconds: number | null;
  auction_expires_at: string | null;
  is_hype_gipfel: boolean;
  near_floor: boolean;
}

export interface WunschkaderRow {
  name: string;
  position: string;
  role: string;
  note: string | null;
  planned_price: number | null;
  is_estimate: boolean;
  is_own: boolean;
  status: string;
  market_value: number | null;
  points_avg: number | null;
  starting_rank: number | null;
  status_code: number | null;
  signal: number | null;
  ml_prediction: number | null;
}

export interface RawWunschkaderTarget {
  name: string;
  position: string;
  role?: string;
  note?: string;
  actual_bid?: number;
}

export interface BudgetPlanSellRow {
  name: string;
  market_value: number | null;
}

export interface BudgetPlan {
  cash: number;
  sell_rows: BudgetPlanSellRow[];
  sell_proceeds: number;
  pool: number;
  committed: number;
  remaining: number;
}

export interface AlleSpielerRow {
  player_id: string;
  name: string;
  position: string;
  team_name: string | null;
  market_value: number | null;
  points_avg: number | null;
  starting_rank: number | null;
  status_label: string | null;
  owner: string;
  fairwert: number | null;
  signal: number | null;
}

export interface SignalThresholds {
  good: number;
  critical: number;
}

export interface DashboardSnapshot {
  spekulation: SpekulationRow[];
  wunschkader: WunschkaderRow[];
  wunschkader_raw: { targets: RawWunschkaderTarget[]; formation?: string | null } | null;
  wunschkader_formation: string | null;
  alle_spieler: AlleSpielerRow[];
  budget_plan: BudgetPlan | null;
  signal_thresholds: SignalThresholds;
  // Weitere Snapshot-Felder (transfermarkt, eigenes_team_split, ...)
  // werden erst in späteren Sub-Projekten typisiert, sobald der jeweilige
  // Tab migriert wird.
  [key: string]: unknown;
}
```

- [ ] **Step 2: Create `frontend/src/lib/formations.ts`**

```ts
// Formations-Notation Verteidigung-Mittelfeld-Sturm (Torwart immer 1,
// nicht Teil der Notation) - Standardkonvention im deutschen Fussball.
export const POSITIONS = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"] as const;
export type Position = (typeof POSITIONS)[number];

export interface FormationSlots {
  Torwart: number;
  Abwehr: number;
  Mittelfeld: number;
  Sturm: number;
}

export const FORMATIONS = {
  "3-4-3": { Torwart: 1, Abwehr: 3, Mittelfeld: 4, Sturm: 3 },
  "4-3-3": { Torwart: 1, Abwehr: 4, Mittelfeld: 3, Sturm: 3 },
  "3-5-2": { Torwart: 1, Abwehr: 3, Mittelfeld: 5, Sturm: 2 },
  "4-4-2": { Torwart: 1, Abwehr: 4, Mittelfeld: 4, Sturm: 2 },
} as const satisfies Record<string, FormationSlots>;

export type FormationKey = keyof typeof FORMATIONS;

export const FORMATION_KEYS = Object.keys(FORMATIONS) as FormationKey[];

export const DEFAULT_FORMATION: FormationKey = "3-4-3";

export function isFormationKey(value: string | null | undefined): value is FormationKey {
  return !!value && value in FORMATIONS;
}

export function slotsFor(formation: string | null | undefined, position: Position): number {
  const key = isFormationKey(formation) ? formation : DEFAULT_FORMATION;
  return FORMATIONS[key][position];
}
```

- [ ] **Step 3: Create `frontend/src/components/ui.tsx`**

Extracted 1:1 from `SpekulationTab.tsx` (`POSITION_ABBR`, `TEAM_ABBR`, `teamAbbr`, `TeamCrest`, `Row`, `Badge`), plus a new `SignalBadge`:

```tsx
import { useState, type ReactNode } from "react";

export const POSITION_ABBR: Record<string, string> = {
  Torwart: "TW",
  Abwehr: "ABW",
  Mittelfeld: "MF",
  Sturm: "ST",
};

// Offizielle 3-Buchstaben-Kuerzel (DFL/TV-Uebertragung, z.B. Sky/Kicker),
// per WebSearch gegengecheckt (siehe Konversation, 2026-07-28). Nach
// team_name geschluesselt (steht schon seit Phase 1 in jeder Zeile, reines
// FE-Mapping ohne Firestore-Push/Cron-Abhaengigkeit) - dient sowohl als
// Fallback-Badge-Text als auch als Wappen-Dateiname (kein team_id noetig,
// das Kuerzel selbst ist schon ASCII-sicher, robuster als der Vereinsname
// mit Sonderzeichen wie "M'gladbach"). Unbekannter Vereinsname faellt auf
// die ersten 3 Buchstaben zurueck.
export const TEAM_ABBR: Record<string, string> = {
  Bayern: "FCB",
  Augsburg: "FCA",
  Bremen: "SVW",
  Dortmund: "BVB",
  Elversberg: "SVE",
  Frankfurt: "SGE",
  Freiburg: "SCF",
  Hamburg: "HSV",
  Hoffenheim: "TSG",
  Köln: "KOE",
  Leipzig: "RBL",
  Leverkusen: "B04",
  "M'gladbach": "BMG",
  Mainz: "M05",
  Paderborn: "SCP",
  Schalke: "S04",
  Stuttgart: "VFB",
  "Union Berlin": "FCU",
};

export function teamAbbr(teamName: string | null): string {
  if (teamName && TEAM_ABBR[teamName]) return TEAM_ABBR[teamName];
  return (teamName ?? "???").slice(0, 3).toUpperCase();
}

// Kickbase liefert selbst keine Logo-URL - Wappen liegen self-hosted unter
// public/crests/{TEAM_ABBR}.svg (vom User zu besorgen). Fehlt eine Datei
// (noch) oder ist der Vereinsname unbekannt, faellt die Kachel auf das
// TV-Kuerzel-Badge zurueck statt ein kaputtes Bild-Icon zu zeigen - Wappen
// koennen nach und nach ergaenzt werden.
export function TeamCrest({ teamName }: { teamName: string | null }) {
  const [failed, setFailed] = useState(false);
  const abbr = teamAbbr(teamName);
  if (!teamName || failed) {
    return (
      <span className="flex h-6 min-w-6 shrink-0 items-center justify-center rounded-md bg-slate-200 px-1 text-[9px] font-semibold tracking-tight text-slate-600 dark:bg-slate-700 dark:text-slate-300">
        {abbr}
      </span>
    );
  }
  return (
    <img
      src={`${import.meta.env.BASE_URL}crests/${abbr}.svg`}
      alt={teamName}
      onError={() => setFailed(true)}
      className="h-6 w-6 shrink-0 rounded-full object-contain"
    />
  );
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-x-3">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-right font-medium tabular-nums text-slate-900 dark:text-slate-100">{children}</dd>
    </div>
  );
}

export function Badge({ tone, children }: { tone: "good" | "warn" | "crit"; children: ReactNode }) {
  const toneClass = {
    good: "bg-brand-100 text-brand-800 dark:bg-brand-950 dark:text-brand-300",
    warn: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    crit: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  }[tone];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${toneClass}`}>{children}</span>;
}

// 1:1 Portierung von signalPill() aus der bestehenden index.html - gleiche
// Schwellen (DATA.signal_thresholds), gleiche 3 Zustaende.
export function SignalBadge({
  signal,
  thresholds,
}: {
  signal: number | null | undefined;
  thresholds: { good: number; critical: number };
}) {
  if (signal === null || signal === undefined) {
    return <span className="text-slate-400 dark:text-slate-500">nicht kalibriert</span>;
  }
  const tone = signal > thresholds.good ? "good" : signal < thresholds.critical ? "crit" : "warn";
  const label = signal > thresholds.good ? "unter Fairwert" : signal < thresholds.critical ? "Prämie" : "im Rauschen";
  return (
    <Badge tone={tone}>
      {signal.toFixed(2)} · {label}
    </Badge>
  );
}
```

- [ ] **Step 4: Remove the duplicated definitions from `SpekulationTab.tsx`, import from `./ui` instead**

In `frontend/src/components/SpekulationTab.tsx`, change the import block at the top from:

```tsx
import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { SpekulationRow } from "../types";
import { fmtNum, fmtSigned, formatDurationMs, trendArrow, trendClass } from "../format";
```

to:

```tsx
import { useEffect, useMemo, useState } from "react";
import type { SpekulationRow } from "../types";
import { fmtNum, fmtSigned, formatDurationMs, trendArrow, trendClass } from "../format";
import { Badge, Row, TeamCrest } from "./ui";
```

Delete the `POSITION_ABBR` constant block (lines 21-26):

```tsx
const POSITION_ABBR: Record<string, string> = {
  Torwart: "TW",
  Abwehr: "ABW",
  Mittelfeld: "MF",
  Sturm: "ST",
};
```

Delete the `TEAM_ABBR` constant, `teamAbbr` function, and `TeamCrest` component entirely (the block from the `// Offizielle 3-Buchstaben-Kuerzel...` comment through the end of `TeamCrest`, i.e. lines 263-320 in the current file — from `const TEAM_ABBR: Record<string, string> = {` down to the closing `}` of `TeamCrest`).

Delete the `Row` function (lines 322-329):

```tsx
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-x-3">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-right font-medium tabular-nums text-slate-900 dark:text-slate-100">{children}</dd>
    </div>
  );
}
```

Delete the `Badge` function (lines 331-339):

```tsx
function Badge({ tone, children }: { tone: "good" | "crit"; children: ReactNode }) {
  const toneClass =
    tone === "good"
      ? "bg-brand-100 text-brand-800 dark:bg-brand-950 dark:text-brand-300"
      : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${toneClass}`}>{children}</span>
  );
}
```

The `CardHeader` function keeps using `POSITION_ABBR`/`TeamCrest` unchanged in behavior — only its source changes from module-local to the `./ui` import; no edit needed inside `CardHeader` itself since `POSITION_ABBR` isn't re-imported explicitly in the snippet above (it's only used, not re-exported) — add it to the import line instead: change the `./ui` import from Step 4 to also include `POSITION_ABBR`:

```tsx
import { Badge, POSITION_ABBR, Row, TeamCrest } from "./ui";
```

- [ ] **Step 5: Verify — bracket-balance check on all touched/created files**

Run:

```bash
for f in frontend/src/types.ts frontend/src/lib/formations.ts frontend/src/components/ui.tsx frontend/src/components/SpekulationTab.tsx; do
python3 - "$f" <<'EOF'
import sys
f = sys.argv[1]
s = open(f, encoding="utf-8").read()
print(f, [(a+b, s.count(a), s.count(b)) for a,b in [("(",")"),("{","}"),("[","]")]])
EOF
done
```

Expected: every pair's two counts match for every file.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types.ts frontend/src/lib/formations.ts frontend/src/components/ui.tsx frontend/src/components/SpekulationTab.tsx
git commit -m "Frontend: Wunschkader-Typen + Formations-Modul + gemeinsame UI-Primitive (Row/Badge/TeamCrest/SignalBadge) aus SpekulationTab extrahiert"
```

---

### Task 3: `WunschkaderTab.tsx` — formation-gruppiertes Layout (read-only)

**Files:**
- Create: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `WunschkaderRow`, `RawWunschkaderTarget`, `BudgetPlan`, `AlleSpielerRow`, `SignalThresholds` (from `../types`); `POSITIONS`, `Position`, `FORMATION_KEYS`, `FormationKey`, `DEFAULT_FORMATION`, `slotsFor`, `isFormationKey` (from `../lib/formations`); `Row`, `Badge`, `POSITION_ABBR`, `SignalBadge` (from `./ui`); `fmtNum` (from `../format`).
- Produces: `export default function WunschkaderTab({ data }: { data: DashboardSnapshot }): JSX.Element` — this is the final exported signature; later tasks (4-6) add behavior inside this same file without changing the outer signature. Also produces the internal type `EditTarget = RawWunschkaderTarget & { _uid: number }`, reused by Tasks 4-6.

- [ ] **Step 1: Write the component**

```tsx
import { useMemo, useState } from "react";
import type { AlleSpielerRow, DashboardSnapshot, RawWunschkaderTarget, WunschkaderRow } from "../types";
import { DEFAULT_FORMATION, FORMATION_KEYS, type FormationKey, POSITIONS, type Position, isFormationKey, slotsFor } from "../lib/formations";
import { Badge, POSITION_ABBR, Row, SignalBadge } from "./ui";
import { fmtNum } from "../format";

const MAX_SQUAD_SIZE = 17;

export type EditTarget = RawWunschkaderTarget & { _uid: number };

function isBench(target: RawWunschkaderTarget): boolean {
  return target.role === "Bank/Backup-Option";
}

interface Computed {
  market_value: number | null;
  points_avg: number | null;
  starting_rank: number | null;
  signal: number | null;
}

// 1:1 Logik aus computedFor() in der bestehenden index.html: zuerst die
// serverseitig berechnete Wunschkader-Zeile nehmen (hat Fairwert-Signal
// gegen die eigene Position berechnet), sonst auf die allgemeine
// Alle-Spieler-Liste zurueckfallen (frisch hinzugefuegte Ziele haben noch
// keine Wunschkader-Zeile, bis der naechste Pipeline-Lauf durch ist).
function computedFor(name: string, wunschkader: WunschkaderRow[], alleSpieler: AlleSpielerRow[]): Computed {
  const fromWunschkader = wunschkader.find((r) => r.name === name);
  if (fromWunschkader) {
    return {
      market_value: fromWunschkader.market_value,
      points_avg: fromWunschkader.points_avg,
      starting_rank: fromWunschkader.starting_rank,
      signal: fromWunschkader.signal,
    };
  }
  const live = alleSpieler.find((p) => p.name === name);
  if (!live) return { market_value: null, points_avg: null, starting_rank: null, signal: null };
  return {
    market_value: live.market_value,
    points_avg: live.points_avg,
    starting_rank: live.starting_rank,
    signal: live.signal,
  };
}

export default function WunschkaderTab({ data }: { data: DashboardSnapshot }) {
  const [formation, setFormation] = useState<FormationKey>(
    isFormationKey(data.wunschkader_formation) ? data.wunschkader_formation : DEFAULT_FORMATION
  );
  let nextUid = 0;
  const [editState, setEditState] = useState<EditTarget[]>(() =>
    (data.wunschkader_raw?.targets ?? []).map((t) => ({ ...t, _uid: nextUid++ }))
  );
  const [selected, setSelected] = useState<EditTarget | null>(null);

  const wunschkader = data.wunschkader ?? [];
  const alleSpieler = data.alle_spieler ?? [];
  const budgetPlan = data.budget_plan;
  const thresholds = data.signal_thresholds;

  const byPosition = useMemo(() => {
    const groups: Record<Position, EditTarget[]> = { Torwart: [], Abwehr: [], Mittelfeld: [], Sturm: [] };
    for (const t of editState) {
      if (isBench(t)) continue;
      const pos = (t.position as Position) in groups ? (t.position as Position) : "Sturm";
      groups[pos].push(t);
    }
    return groups;
  }, [editState]);

  const bench = useMemo(() => editState.filter(isBench), [editState]);
  const totalCount = editState.length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          Formation
          <select
            value={formation}
            onChange={(e) => setFormation(e.target.value as FormationKey)}
            className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {FORMATION_KEYS.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>
        {totalCount > MAX_SQUAD_SIZE && (
          <Badge tone="warn">
            {totalCount}/{MAX_SQUAD_SIZE} Kadergröße überschritten
          </Badge>
        )}
      </div>

      {POSITIONS.map((position) => {
        const targets = byPosition[position];
        const slots = slotsFor(formation, position);
        return (
          <div key={position} className="mb-6">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {position} · {targets.length}/{slots} belegt
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
              {targets.map((t) => (
                <TargetCard
                  key={t._uid}
                  target={t}
                  computed={computedFor(t.name, wunschkader, alleSpieler)}
                  thresholds={thresholds}
                  onSelect={() => setSelected(t)}
                />
              ))}
              {Array.from({ length: Math.max(slots - targets.length, 0) }).map((_, i) => (
                <EmptySlotCard key={`empty-${position}-${i}`} />
              ))}
            </div>
          </div>
        );
      })}

      <div className="mb-6">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Bank ({bench.length})
        </div>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
          {bench.map((t) => (
            <TargetCard
              key={t._uid}
              target={t}
              computed={computedFor(t.name, wunschkader, alleSpieler)}
              thresholds={thresholds}
              onSelect={() => setSelected(t)}
            />
          ))}
          <EmptySlotCard />
        </div>
      </div>

      {budgetPlan && <BudgetPlanCard plan={budgetPlan} />}

      {selected && (
        <DetailModal
          target={selected}
          computed={computedFor(selected.name, wunschkader, alleSpieler)}
          thresholds={thresholds}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function TargetCard({
  target,
  computed,
  thresholds,
  onSelect,
}: {
  target: EditTarget;
  computed: Computed;
  thresholds: DashboardSnapshot["signal_thresholds"];
  onSelect: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-brand-400 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/40 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-600"
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[target.position] ?? target.position}</span>
        <span className="font-semibold text-slate-900 dark:text-slate-50">{target.name}</span>
      </div>
      <dl className="space-y-1.5 text-sm">
        <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
        <Row label="Startelf-Rang">{computed.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
        <Row label="Schnitt">{fmtNum(computed.points_avg)}</Row>
        <Row label="Signal">
          <SignalBadge signal={computed.signal} thresholds={thresholds} />
        </Row>
      </dl>
    </div>
  );
}

function EmptySlotCard() {
  return (
    <div className="flex items-center justify-center rounded-2xl border border-dashed border-slate-300 p-4 text-sm text-slate-400 dark:border-slate-700 dark:text-slate-500">
      + Ziel
    </div>
  );
}

function DetailModal({
  target,
  computed,
  thresholds,
  onClose,
}: {
  target: EditTarget;
  computed: Computed;
  thresholds: DashboardSnapshot["signal_thresholds"];
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[target.position] ?? target.position}</span>
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{target.name}</span>
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
        <dl className="space-y-2 text-sm">
          <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
          <Row label="Startelf-Rang">{computed.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Schnitt">{fmtNum(computed.points_avg)}</Row>
          <Row label="Signal">
            <SignalBadge signal={computed.signal} thresholds={thresholds} />
          </Row>
        </dl>
      </div>
    </div>
  );
}

function BudgetPlanCard({ plan }: { plan: NonNullable<DashboardSnapshot["budget_plan"]> }) {
  const remainingTone = plan.remaining >= 0 ? "text-brand-600 dark:text-brand-400" : "text-red-600 dark:text-red-400";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-50">Budget-Planung</h3>
      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Cash</div>
          <div className="font-medium tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.cash)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">+ Verkaufserlöse</div>
          <div className="font-medium tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.sell_proceeds)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">= Pool</div>
          <div className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.pool)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">- Eingeplant</div>
          <div className="font-medium tabular-nums text-slate-900 dark:text-slate-100">{fmtNum(plan.committed)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500 dark:text-slate-400">= Rest</div>
          <div className={`font-semibold tabular-nums ${remainingTone}`}>{fmtNum(plan.remaining)}</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify — bracket-balance check**

Run:

```bash
python3 - "frontend/src/components/WunschkaderTab.tsx" <<'EOF'
import sys
f = sys.argv[1]
s = open(f, encoding="utf-8").read()
print(f, [(a+b, s.count(a), s.count(b)) for a,b in [("(",")"),("{","}"),("[","]")]])
EOF
```

Expected: all three pairs balanced.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "Wunschkader-Tab: formation-gruppiertes Karten-Layout (read-only), Bank-Sektion, Budget-Plan-Kachel ohne Hinweistext"
```

---

### Task 4: Detail-Modal-Aktionen — Bank/Startelf-Toggle, Entfernen, Wechsel-Suche

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `EditTarget`, `isBench` (internal to the file, defined in Task 3). `AlleSpielerRow` (from `../types`, already imported).
- Produces: `scoreReplacementPool`, `suggestReplacements`, `searchReplacementPool` (internal helpers, used again in Task 5's add-flow is NOT needed — only Task 6 might reuse `EditTarget`'s shape, no new cross-task exports beyond what Task 3 already produced). `WunschkaderTab`'s local state gains two setters used by Task 5/6: `setEditState` (already declared in Task 3, now actually used for mutation) — no signature change to the component itself.

- [ ] **Step 1: Add replacement-pool helpers above the `WunschkaderTab` function**

Insert directly after the `computedFor` function (before `export default function WunschkaderTab`):

```tsx
// 1:1 portiert aus scoreReplacementPool()/suggestReplacements()/
// searchReplacementPool() der bestehenden index.html.
function scoreReplacementPool(alleSpieler: AlleSpielerRow[], target: { name: string; position: string; market_value: number | null; points_avg: number | null }) {
  const pool = alleSpieler.filter((p) => p.position === target.position && p.name !== target.name && p.owner === "Frei");
  const mv = target.market_value || 0;
  const pts = target.points_avg || 0;
  return pool
    .map((p) => {
      const mvDist = mv ? Math.abs((p.market_value || 0) - mv) / mv : 0;
      const ptsDist = pts ? Math.abs((p.points_avg || 0) - pts) / pts : 0;
      return { ...p, distance: mvDist + ptsDist };
    })
    .sort((a, b) => a.distance - b.distance);
}

function suggestReplacements(alleSpieler: AlleSpielerRow[], target: { name: string; position: string; market_value: number | null; points_avg: number | null }, count = 3) {
  return scoreReplacementPool(alleSpieler, target).slice(0, count);
}

function searchReplacementPool(alleSpieler: AlleSpielerRow[], target: { name: string; position: string; market_value: number | null; points_avg: number | null }, query: string) {
  const q = query.toLowerCase();
  return scoreReplacementPool(alleSpieler, target)
    .filter((p) => p.name.toLowerCase().includes(q))
    .slice(0, 20);
}
```

- [ ] **Step 2: Wire up mutation handlers in `WunschkaderTab`**

Directly below the line `const bench = useMemo(() => editState.filter(isBench), [editState]);` in the `WunschkaderTab` function body, add:

```tsx
  function toggleBench(uid: number) {
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { ...t, role: isBench(t) ? "Starter" : "Bank/Backup-Option" } : t))
    );
    setSelected((prev) => (prev && prev._uid === uid ? { ...prev, role: isBench(prev) ? "Starter" : "Bank/Backup-Option" } : prev));
  }

  function removeTarget(uid: number) {
    setEditState((prev) => prev.filter((t) => t._uid !== uid));
    setSelected(null);
  }

  function replaceTarget(uid: number, replacement: AlleSpielerRow) {
    setEditState((prev) =>
      prev.map((t) => (t._uid === uid ? { ...t, name: replacement.name, position: replacement.position } : t))
    );
    setSelected(null);
  }
```

- [ ] **Step 3: Pass the handlers and `alleSpieler` down to `DetailModal`, and replace its body**

Change the `DetailModal` render call inside `WunschkaderTab`'s JSX from:

```tsx
      {selected && (
        <DetailModal
          target={selected}
          computed={computedFor(selected.name, wunschkader, alleSpieler)}
          thresholds={thresholds}
          onClose={() => setSelected(null)}
        />
      )}
```

to:

```tsx
      {selected && (
        <DetailModal
          target={selected}
          computed={computedFor(selected.name, wunschkader, alleSpieler)}
          thresholds={thresholds}
          alleSpieler={alleSpieler}
          onClose={() => setSelected(null)}
          onToggleBench={() => toggleBench(selected._uid)}
          onRemove={() => removeTarget(selected._uid)}
          onReplace={(replacement) => replaceTarget(selected._uid, replacement)}
        />
      )}
```

Replace the entire `DetailModal` function (defined in Task 3) with:

```tsx
function DetailModal({
  target,
  computed,
  thresholds,
  alleSpieler,
  onClose,
  onToggleBench,
  onRemove,
  onReplace,
}: {
  target: EditTarget;
  computed: Computed;
  thresholds: DashboardSnapshot["signal_thresholds"];
  alleSpieler: AlleSpielerRow[];
  onClose: () => void;
  onToggleBench: () => void;
  onRemove: () => void;
  onReplace: (replacement: AlleSpielerRow) => void;
}) {
  const [wechselOpen, setWechselOpen] = useState(false);
  const [search, setSearch] = useState("");

  const targetForSearch = { name: target.name, position: target.position, market_value: computed.market_value, points_avg: computed.points_avg };
  const suggestions = suggestReplacements(alleSpieler, targetForSearch);
  const searchResults = search.trim() ? searchReplacementPool(alleSpieler, targetForSearch, search.trim()) : [];

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-4 flex items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400 dark:text-slate-500">{POSITION_ABBR[target.position] ?? target.position}</span>
            <span className="text-base font-semibold text-slate-900 dark:text-slate-50">{target.name}</span>
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
        <dl className="mb-4 space-y-2 text-sm">
          <Row label="Marktwert">{fmtNum(computed.market_value)}</Row>
          <Row label="Startelf-Rang">{computed.starting_rank ?? <span className="text-slate-400 dark:text-slate-500">n/v</span>}</Row>
          <Row label="Schnitt">{fmtNum(computed.points_avg)}</Row>
          <Row label="Signal">
            <SignalBadge signal={computed.signal} thresholds={thresholds} />
          </Row>
        </dl>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onToggleBench}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {isBench(target) ? "In Startelf verschieben" : "Auf Bank verschieben"}
          </button>
          <button
            type="button"
            onClick={() => setWechselOpen((v) => !v)}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Wechsel
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950"
          >
            Entfernen
          </button>
        </div>
        {wechselOpen && (
          <div className="mt-4 border-t border-slate-200 pt-4 dark:border-slate-800">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Vorschläge</div>
            {suggestions.length ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s.player_id}
                    type="button"
                    onClick={() => onReplace(s)}
                    className="rounded-full border border-brand-300 bg-brand-50 px-3 py-1 text-xs text-brand-800 hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300"
                  >
                    {s.name} ({fmtNum(s.market_value)}, Ø{fmtNum(s.points_avg)})
                  </button>
                ))}
              </div>
            ) : (
              <p className="mb-3 text-xs text-slate-400 dark:text-slate-500">Keine freien Alternativen gleicher Position gefunden.</p>
            )}
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Anderen freien Spieler gleicher Position suchen…"
              className="mb-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
            {search.trim() && (
              <div className="flex flex-wrap gap-2">
                {searchResults.length ? (
                  searchResults.map((s) => (
                    <button
                      key={s.player_id}
                      type="button"
                      onClick={() => onReplace(s)}
                      className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                    >
                      {s.name} ({fmtNum(s.market_value)}, Ø{fmtNum(s.points_avg)})
                    </button>
                  ))
                ) : (
                  <span className="text-xs text-slate-400 dark:text-slate-500">Keine Treffer.</span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify — bracket-balance check**

Run the same check command as Task 3 Step 2 against `frontend/src/components/WunschkaderTab.tsx`. Expected: all balanced.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "Wunschkader-Tab: Detail-Modal-Aktionen (Bank/Startelf-Toggle, Entfernen, Wechsel-Suche)"
```

---

### Task 5: Hinzufügen — leerer Positions-Slot + genereller Bank-Button

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`

**Interfaces:**
- Consumes: `EditTarget`, `Position`, `POSITIONS` (already imported/defined by Task 3).
- Produces: `AddTargetModal` component (internal, not exported outside the file — Task 6 does not need it directly).

- [ ] **Step 1: Add an `addTarget` handler in `WunschkaderTab`**

Directly below the `replaceTarget` function added in Task 4 Step 2, add:

```tsx
  function addTarget(target: { name: string; position: Position; role: string }) {
    setEditState((prev) => [...prev, { ...target, _uid: prev.length ? Math.max(...prev.map((t) => t._uid)) + 1 : 0 }]);
  }
```

- [ ] **Step 2: Add local state for the add-dialog and wire up `EmptySlotCard`**

In `WunschkaderTab`, directly below `const [selected, setSelected] = useState<EditTarget | null>(null);`, add:

```tsx
  const [addDialog, setAddDialog] = useState<{ presetPosition: Position | null } | null>(null);
```

Change every `<EmptySlotCard key={...} />` usage to pass an `onClick`. First, in the per-position loop (Task 3's `POSITIONS.map` block), change:

```tsx
              {Array.from({ length: Math.max(slots - targets.length, 0) }).map((_, i) => (
                <EmptySlotCard key={`empty-${position}-${i}`} />
              ))}
```

to:

```tsx
              {Array.from({ length: Math.max(slots - targets.length, 0) }).map((_, i) => (
                <EmptySlotCard key={`empty-${position}-${i}`} onClick={() => setAddDialog({ presetPosition: position })} />
              ))}
```

Then, in the Bank section, change:

```tsx
          <EmptySlotCard />
```

to:

```tsx
          <EmptySlotCard onClick={() => setAddDialog({ presetPosition: null })} />
```

Update the `EmptySlotCard` function itself (defined in Task 3) from:

```tsx
function EmptySlotCard() {
  return (
    <div className="flex items-center justify-center rounded-2xl border border-dashed border-slate-300 p-4 text-sm text-slate-400 dark:border-slate-700 dark:text-slate-500">
      + Ziel
    </div>
  );
}
```

to:

```tsx
function EmptySlotCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center justify-center rounded-2xl border border-dashed border-slate-300 p-4 text-sm text-slate-400 hover:border-brand-400 hover:text-brand-600 dark:border-slate-700 dark:text-slate-500 dark:hover:border-brand-600 dark:hover:text-brand-400"
    >
      + Ziel
    </button>
  );
}
```

- [ ] **Step 3: Render `AddTargetModal` conditionally at the end of `WunschkaderTab`'s JSX**

Directly below the `{selected && (<DetailModal .../>)}` block, add:

```tsx
      {addDialog && (
        <AddTargetModal
          presetPosition={addDialog.presetPosition}
          onAdd={addTarget}
          onClose={() => setAddDialog(null)}
        />
      )}
```

- [ ] **Step 4: Implement `AddTargetModal`**

Add this function at the end of the file (after `BudgetPlanCard`), and add `type FormEvent` to the existing `react` import at the top (change `import { useMemo, useState } from "react";` to `import { useMemo, useState, type FormEvent } from "react";`):

```tsx
function AddTargetModal({
  presetPosition,
  onAdd,
  onClose,
}: {
  presetPosition: Position | null;
  onAdd: (target: { name: string; position: Position; role: string }) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [position, setPosition] = useState<Position>(presetPosition ?? "Sturm");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    onAdd({
      name: trimmed,
      position: presetPosition ?? position,
      role: presetPosition ? "Starter" : "Bank/Backup-Option",
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-950/50 px-4" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900"
      >
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-50">
          Ziel hinzufügen{presetPosition ? ` (${presetPosition})` : ""}
        </h3>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Name"
          autoFocus
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        {!presetPosition && (
          <select
            value={position}
            onChange={(e) => setPosition(e.target.value as Position)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Abbrechen
          </button>
          <button
            type="submit"
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            Hinzufügen
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Verify — bracket-balance check**

Run the same check command as Task 3 Step 2 against `frontend/src/components/WunschkaderTab.tsx`. Expected: all balanced.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx
git commit -m "Wunschkader-Tab: Hinzufuegen ueber leeren Positions-Slot (Position vorbelegt) und generischen Bank-Button"
```

---

### Task 6: Speichern (Firestore) + Tab in App.tsx aktivieren

**Files:**
- Modify: `frontend/src/components/WunschkaderTab.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `db` (from `../firebase`), `doc`/`setDoc` (from `firebase/firestore`).
- Produces: none further (terminal task for this sub-project — `WunschkaderTab` is now feature-complete and wired into `App`).

- [ ] **Step 1: Add Firestore imports and a save handler to `WunschkaderTab.tsx`**

Change the top of `frontend/src/components/WunschkaderTab.tsx` from:

```tsx
import { useMemo, useState, type FormEvent } from "react";
import type { AlleSpielerRow, DashboardSnapshot, RawWunschkaderTarget, WunschkaderRow } from "../types";
```

to:

```tsx
import { useMemo, useState, type FormEvent } from "react";
import { doc, setDoc } from "firebase/firestore";
import { db } from "../firebase";
import type { AlleSpielerRow, DashboardSnapshot, RawWunschkaderTarget, WunschkaderRow } from "../types";
```

Directly below the `addTarget` function (added in Task 5 Step 1), add:

```tsx
  const [saveStatus, setSaveStatus] = useState("");

  async function handleSave() {
    setSaveStatus("Speichere…");
    try {
      const updatedAt = new Date().toISOString().slice(0, 10);
      const targets = editState.map(({ _uid, ...rest }) => rest);
      await setDoc(doc(db, "wunschkader", "current"), { targets, formation, updated_at: updatedAt }, { merge: true });
      setSaveStatus("Gespeichert. Änderungen erscheinen im nächsten Pipeline-Lauf (~2h).");
    } catch (err) {
      setSaveStatus("Fehler beim Speichern: " + (err as Error).message);
    }
  }
```

- [ ] **Step 2: Render the Speichern button**

In `WunschkaderTab`'s JSX, directly above the `{POSITIONS.map((position) => {` block, add:

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

- [ ] **Step 3: Activate the Wunschkader tab in `App.tsx`**

Replace the full content of `frontend/src/App.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { onAuthStateChanged, type User } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { auth, db } from "./firebase";
import Login from "./components/Login";
import SpekulationTab from "./components/SpekulationTab";
import WunschkaderTab from "./components/WunschkaderTab";
import type { DashboardSnapshot } from "./types";

type LoadState = "loading" | "error" | "ready";

const TABS = [
  { key: "transfermarkt", label: "Transfermarkt" },
  { key: "spekulation", label: "Spekulation" },
  { key: "team", label: "Eigenes Team" },
  { key: "wunschkader", label: "Wunschkader" },
  { key: "alle-spieler", label: "Alle Spieler" },
  { key: "liga", label: "Ligaanalyse" },
  { key: "ml-genauigkeit", label: "ML-Genauigkeit" },
];

// Sub-Projekt 1+2: Spekulation und Wunschkader sind migriert, alle anderen
// Tabs bleiben bis zu ihrem eigenen Sub-Projekt (siehe Phase-6-Plan) deaktiviert.
const ACTIVE_TABS = new Set(["spekulation", "wunschkader"]);

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [data, setData] = useState<DashboardSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState("spekulation");

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), []);

  useEffect(() => {
    if (!user) return;
    setLoadState("loading");
    getDoc(doc(db, "dashboard_snapshot", "latest"))
      .then((snap) => {
        if (!snap.exists()) {
          setErrorMessage("Noch kein Dashboard-Snapshot vorhanden. Bitte später erneut versuchen.");
          setLoadState("error");
          return;
        }
        setData(snap.data() as DashboardSnapshot);
        setLoadState("ready");
      })
      .catch((err) => {
        setErrorMessage("Fehler beim Laden: " + err.message);
        setLoadState("error");
      });
  }, [user]);

  // Erster Auth-Check läuft noch (verhindert Login-Formular-Aufflackern).
  if (user === undefined) return null;
  if (!user) return <Login />;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200 bg-white px-6 py-4 dark:border-slate-800 dark:bg-slate-950">
        <h1 className="flex items-center gap-2.5 text-lg font-semibold text-slate-900 dark:text-slate-50">
          <span className="inline-block h-3 w-3 rounded-full bg-brand-500 shadow-md shadow-brand-500/50" />
          KickbaseAgent
          <span className="font-normal text-slate-400 dark:text-slate-500">Dashboard</span>
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-800 dark:bg-brand-950 dark:text-brand-300">
            Preview
          </span>
        </h1>
      </header>
      <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-6 dark:border-slate-800 dark:bg-slate-950">
        {TABS.map((tab) => {
          const isActive = ACTIVE_TABS.has(tab.key);
          const isSelected = tab.key === activeTab;
          return (
            <button
              key={tab.key}
              type="button"
              disabled={!isActive}
              onClick={() => isActive && setActiveTab(tab.key)}
              className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm transition-colors ${
                isSelected
                  ? "border-brand-500 font-semibold text-slate-900 dark:text-slate-50"
                  : isActive
                    ? "border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-50"
                    : "cursor-not-allowed border-transparent text-slate-400 dark:text-slate-600"
              }`}
            >
              {tab.label}
              {!isActive && <span className="ml-1 text-xs">(bald)</span>}
            </button>
          );
        })}
      </nav>
      <main className="px-6 py-6">
        {loadState === "loading" && (
          <p className="text-sm text-slate-500 dark:text-slate-400">Lade Daten…</p>
        )}
        {loadState === "error" && (
          <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
        )}
        {loadState === "ready" && data && activeTab === "spekulation" && <SpekulationTab rows={data.spekulation ?? []} />}
        {loadState === "ready" && data && activeTab === "wunschkader" && <WunschkaderTab data={data} />}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Verify — bracket-balance check on both files**

Run:

```bash
for f in frontend/src/components/WunschkaderTab.tsx frontend/src/App.tsx; do
python3 - "$f" <<'EOF'
import sys
f = sys.argv[1]
s = open(f, encoding="utf-8").read()
print(f, [(a+b, s.count(a), s.count(b)) for a,b in [("(",")"),("{","}"),("[","]")]])
EOF
done
```

Expected: all balanced in both files.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WunschkaderTab.tsx frontend/src/App.tsx
git commit -m "Wunschkader-Tab: Speichern per setDoc verdrahtet, zweiter aktiver Tab in App.tsx"
```

---

## Final Verification (after all 6 tasks)

- [ ] `python3 -m unittest tests.test_dashboard_export -v` — all tests green.
- [ ] Bracket-balance check on every touched/created frontend file (`frontend/src/types.ts`, `frontend/src/lib/formations.ts`, `frontend/src/components/ui.tsx`, `frontend/src/components/SpekulationTab.tsx`, `frontend/src/components/WunschkaderTab.tsx`, `frontend/src/App.tsx`) — all balanced.
- [ ] `git log --oneline -8` shows 6 new local commits, none pushed.
- [ ] Tell the user: real verification (`npm run dev`, formation switching, add/remove/wechsel/bench-toggle/save, old `index.html` Wunschkader tab + Eigenes-Team-watchlist still rendering correctly) must happen on their own machine — this sandbox cannot run `npm install`/`npm run` (Windows-DrvFs-mount issue) or a real browser.
