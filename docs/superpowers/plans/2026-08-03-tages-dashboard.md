# Tages-Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Neuer Tab "Dashboard" (ganz vorne), der täglichen Handlungsbedarf bündelt: Verkaufen/Kaufen/Investment/Transfer-Feed, plus Kaderlimit-Hinweis.

**Architecture:** Backend ergänzt einen neuen, aus bereits gezogenen Daten abgeleiteten Snapshot-Abschnitt (`recent_transfers`, keine neue Kickbase-API-Anbindung). Frontend bekommt neue reine Ableitungsfunktionen in `derive.ts` (TDD) + eine neue `DashboardTab.tsx`, die zwei bestehende Komponenten (`TransfermarktCard`/`TransfermarktDetailModal`) wiederverwendet statt neu zu bauen.

**Tech Stack:** Python (Backend), React/TypeScript/Vitest (Frontend). Keine neuen Dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-03-tages-dashboard-design.md` — bei Unklarheit dort nachschlagen, dieser Plan ist die Ausführung davon.
- Kein neuer Kickbase-API-Call — `recent_transfers` nutzt ausschließlich den bereits im Heavy-Cron gezogenen `get_activities_feed()`-Ergebnis (`activities`-Variable, `dashboard_export.py`, aktuell nur für `bid_premium.update_and_load()` genutzt).
- Investment-Sektion ignoriert Position komplett, keine Kapital-/Leistbarkeitsfilterung irgendwo in diesem Feature (siehe Spec, Nicht-Ziele).
- Kaderlimit-Hinweis-Text ist NUR "Kader voll (17/17)" — keine Erklärung der Konsequenz.
- Push-Policy dieses Repos: direkt auf `main` pushen, sobald Tests grün (kein PR-Umweg, siehe [[project_kickbaseagent_git_workflow]]).
- Vor Merge/Push `git log origin/main --oneline -5` + `git worktree list` prüfen (siehe [[feedback_check_worktrees_before_fresh_plan_dispatch]]).
- **Undokumentiertes Kickbase-API-Feld**: `get_activities_feed()`s `dt`-Feld-Format (Datum/Zeit pro Activity-Eintrag) ist laut eigenem Docstring (`kickbase_client.py:209`) "UNBESTAETIGT gegen echte Daten" — Task 1 verlangt deshalb explizit einen echten Sandbox-Live-Call VOR dem Schreiben des Zeitfilters, nicht raten.

---

## Task 1: Backend — `_build_recent_transfers()` + Snapshot-Feld + Contract-Test

**Files:**
- Modify: `src/dashboard_export.py` (neue Funktion + Verdrahtung in `export()`/`_assemble_snapshot()`)
- Test: `tests/test_dashboard_export.py`

**Interfaces:**
- Produziert: `_build_recent_transfers(activities: list[dict], players_map: dict, ranking_rows: list[dict], own_user_id: str | None, cutoff_hours: int = 72) -> list[dict]` — jedes Element: `{"player_id": str, "player_name": str, "buyer": str, "seller": str, "price": int, "date": str}` (`buyer`/`seller` sind bereits aufgelöste Namen, `"Kickbase"` bei Systemkauf/-verkauf).
- Neues Snapshot-Feld `recent_transfers: list[dict]` in `_assemble_snapshot()`.

- [ ] **Step 1: Echten Activity-Feed-Sample ziehen und `dt`-Format bestätigen (Sandbox hat Live-Zugriff, siehe HANDOFF.md)**

```bash
GOOGLE_APPLICATION_CREDENTIALS=firebase-service-account.json python3 -c "
from dotenv import load_dotenv
import os, json
load_dotenv()
from src.kickbase_client import login, get_activities_feed
token, league_id = login(os.environ['KICKBASE_EMAIL'], os.environ['KICKBASE_PASSWORD'], os.environ['KICKBASE_LEAGUE_ID'])
activities = get_activities_feed(token, league_id, max_entries=20)
trades = [a for a in activities if a.get('t') == 15]
print(json.dumps(trades[:3], indent=2, ensure_ascii=False))
"
```

Notiere das exakte Format von `dt` (z.B. `"2026-08-02T14:33:00Z"` vs. ohne `Z`/mit Millisekunden) — Step 3 unten
muss dieses Format beim Parsen exakt matchen. Falls `dt` NICHT lexikografisch mit `datetime.isoformat()` vergleichbar
ist (z.B. anderes Trennzeichen), Step 3 entsprechend anpassen (`datetime.datetime.fromisoformat()` statt
String-Vergleich verwenden) statt den hier dokumentierten Ansatz blind zu übernehmen.

- [ ] **Step 2: Failing Test schreiben**

In `tests/test_dashboard_export.py` (neue Testklasse ans Ende der Datei):

```python
class BuildRecentTransfersTests(unittest.TestCase):
    PLAYERS_MAP = {
        "p1": {"player_id": "p1", "name": "Spieler Eins"},
        "p2": {"player_id": "p2", "name": "Spieler Zwei"},
    }
    RANKING_ROWS = [
        {"user_id": "u_self", "name": "Ich"},
        {"user_id": "u_rival", "name": "Rivale"},
    ]

    def test_resolves_player_and_manager_names(self):
        activities = [
            {"t": 15, "dt": "2026-08-03T10:00:00Z", "data": {"pi": "p1", "byr": "u_rival", "slr": "u_self", "trp": 500000}},
        ]
        result = _build_recent_transfers(activities, self.PLAYERS_MAP, self.RANKING_ROWS, own_user_id=None, cutoff_hours=72)
        self.assertEqual(result, [
            {"player_id": "p1", "player_name": "Spieler Eins", "buyer": "Rivale", "seller": "Ich", "price": 500000, "date": "2026-08-03T10:00:00Z"},
        ])

    def test_marks_system_trade_as_kickbase(self):
        activities = [
            {"t": 15, "dt": "2026-08-03T10:00:00Z", "data": {"pi": "p2", "byr": "u_rival", "trp": 300000}},
        ]
        result = _build_recent_transfers(activities, self.PLAYERS_MAP, self.RANKING_ROWS, own_user_id=None, cutoff_hours=72)
        self.assertEqual(result[0]["seller"], "Kickbase")

    def test_excludes_own_trades(self):
        activities = [
            {"t": 15, "dt": "2026-08-03T10:00:00Z", "data": {"pi": "p1", "byr": "u_self", "slr": "u_rival", "trp": 500000}},
        ]
        result = _build_recent_transfers(activities, self.PLAYERS_MAP, self.RANKING_ROWS, own_user_id="u_self", cutoff_hours=72)
        self.assertEqual(result, [])

    def test_excludes_non_trade_activity_types(self):
        activities = [{"t": 22, "dt": "2026-08-03T10:00:00Z", "data": {"bn": 1000}}]
        result = _build_recent_transfers(activities, self.PLAYERS_MAP, self.RANKING_ROWS, own_user_id=None, cutoff_hours=72)
        self.assertEqual(result, [])
```

(Passe die `dt`-Werte/das Parsing im Test an das in Step 1 tatsächlich beobachtete Format an, falls es vom hier
angenommenen `"YYYY-MM-DDTHH:MM:SSZ"` abweicht.)

- [ ] **Step 3: Test laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_dashboard_export.BuildRecentTransfersTests -v`
Expected: FAIL (`NameError: name '_build_recent_transfers' is not defined`)

- [ ] **Step 4: `_build_recent_transfers()` implementieren**

In `src/dashboard_export.py`, direkt vor `_build_ligaanalyse()`:

```python
TRADE_ACTIVITY_TYPE = 15


def _build_recent_transfers(
    activities: list[dict],
    players_map: dict,
    ranking_rows: list[dict],
    own_user_id: str | None,
    cutoff_hours: int = 72,
) -> list[dict]:
    """Transfer-Feed fuers Tages-Dashboard - reine Ableitung aus dem bereits
    fuer bid_premium.py gezogenen Activity-Feed, kein zusaetzlicher
    Kickbase-API-Call. Eigene Trades werden ausgeschlossen (stehen bereits in
    der Verkaufen/Kaufen-Sektion des Dashboards)."""
    names_by_user_id = {r["user_id"]: r["name"] for r in ranking_rows}
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=cutoff_hours)).isoformat()
    result = []
    for entry in activities:
        if entry.get("t") != TRADE_ACTIVITY_TYPE:
            continue
        dt = entry.get("dt", "")
        if dt < cutoff:
            continue
        data = entry.get("data", {})
        player_id = data.get("pi")
        player = players_map.get(player_id)
        if not player:
            continue
        buyer_id = data.get("byr")
        seller_id = data.get("slr")
        if own_user_id and (buyer_id == own_user_id or seller_id == own_user_id):
            continue
        result.append({
            "player_id": player_id,
            "player_name": player["name"],
            "buyer": names_by_user_id.get(buyer_id, "Kickbase") if buyer_id else "Kickbase",
            "seller": names_by_user_id.get(seller_id, "Kickbase") if seller_id else "Kickbase",
            "price": data.get("trp"),
            "date": dt,
        })
    return result
```

(Passe den `cutoff`/`dt`-Vergleich an, falls Step 1 ein Timestamp-Format ohne verlaessliche lexikografische
Sortierbarkeit findet — dann `datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))` statt String-Vergleich
nutzen.)

- [ ] **Step 5: Test erneut laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_dashboard_export.BuildRecentTransfersTests -v`
Expected: PASS (4/4)

- [ ] **Step 6: In `export()` verdrahten + Contract-Test aktualisieren**

In `src/dashboard_export.py`, am `_assemble_snapshot()`-Aufruf (aktuell nach `ligaanalyse_result = _build_ligaanalyse(...)`):

```python
    own_user_id = own_budget_row["user_id"] if own_budget_row else None
    recent_transfers = _build_recent_transfers(activities, players_map, ranking_rows, own_user_id)

    data = _assemble_snapshot(
        ...,  # bestehende Argumente unveraendert
        recent_transfers=recent_transfers,
    )
```

`_assemble_snapshot()`s Signatur bekommt einen neuen Parameter `recent_transfers` (nach `position_need`), und der
`return`-Dict bekommt eine neue Zeile `"recent_transfers": recent_transfers,`.

In `tests/test_dashboard_export.py::AssembleSnapshotContractTests`: `EXPECTED_KEYS` bekommt `"recent_transfers"`
ergänzt, der Aufruf in `test_returns_exactly_the_expected_top_level_keys` bekommt `recent_transfers=[]` ergänzt.

- [ ] **Step 7: Volle Backend-Suite laufen lassen**

Run: `python3 -m unittest discover -s tests`
Expected: alle Tests grün (226 + 4 neue = 230).

- [ ] **Step 8: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "Dashboard: recent_transfers aus bereits gezogenem Activity-Feed"
```

---

## Task 2: Frontend — reine Ableitungsfunktionen in `derive.ts` (TDD)

**Files:**
- Modify: `frontend/src/lib/derive.ts`
- Test: `frontend/src/lib/derive.test.ts`
- Modify: `frontend/src/types.ts` (neuer Typ + optionales Snapshot-Feld)

**Interfaces:**
- Konsumiert: `PlayerRow`/`TransfermarktRow`/`buildPlayerRow`/`sellSignal` (alle bereits vorhanden, `derive.ts`), `RawWunschkaderTarget` (`types.ts`).
- Produziert: `buildDashboardSellCandidates`, `buildDashboardBuyCandidates`, `buildInvestmentSwaps`,
  `recentTransfersWithin24h` — Signaturen siehe Step 4.

- [ ] **Step 1: `RecentTransferEntry`-Typ + optionales Snapshot-Feld ergänzen**

In `frontend/src/types.ts`, direkt nach der bestehenden `RawWunschkaderTarget`-Interface-Definition (Zeile ~49-...):

```ts
export interface RecentTransferEntry {
  player_id: string;
  player_name: string;
  buyer: string;
  seller: string;
  price: number;
  date: string;
}
```

In `DashboardSnapshot` (Zeile ~170, neben den anderen optionalen Feldern):

```ts
  recent_transfers?: RecentTransferEntry[];
```

- [ ] **Step 2: Failing Tests schreiben**

In `frontend/src/lib/derive.test.ts` (neue `describe`-Blöcke ans Ende):

```ts
describe("buildDashboardSellCandidates", () => {
  const players = {
    p1: { player_id: "p1", name: "A", position: "Sturm", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: -50_000, ml_prediction_3d: -100_000 },
    p2: { player_id: "p2", name: "B", position: "Abwehr", team_name: null, status_code: null, starting_rank: null, market_value: 1_000_000, average_points: 100, ml_prediction: 50_000, ml_prediction_3d: 100_000 },
  };
  it("returns only players with sellSignal 'verkaufen'", () => {
    const result = buildDashboardSellCandidates(players, ["p1", "p2"], null, null);
    expect(result.map((r) => r.player_id)).toEqual(["p1"]);
  });
});

describe("buildDashboardBuyCandidates", () => {
  it("returns transfermarkt rows whose player_id is a wunschkader target", () => {
    const rows = [
      { player_id: "p1", name: "A" } as TransfermarktRow,
      { player_id: "p2", name: "B" } as TransfermarktRow,
    ];
    const targets = [{ player_id: "p2" }] as RawWunschkaderTarget[];
    const result = buildDashboardBuyCandidates(rows, targets);
    expect(result.map((r) => r.player_id)).toEqual(["p2"]);
  });
});

describe("buildInvestmentSwaps", () => {
  const ownRows = [
    { player_id: "own1", name: "Own1", ml_prediction_3d: -300_000 } as PlayerRow,
    { player_id: "own2", name: "Own2", ml_prediction_3d: 100_000 } as PlayerRow,
  ];
  const marketRows = [
    { player_id: "m1", name: "M1", ml_prediction_3d: 400_000 } as TransfermarktRow,
    { player_id: "m2", name: "M2", ml_prediction_3d: -50_000 } as TransfermarktRow,
  ];
  it("pairs worst-owned with best-market when the gap exceeds the strong threshold", () => {
    const result = buildInvestmentSwaps(ownRows, marketRows, 420_000);
    expect(result).toEqual([{ sell: ownRows[0], buy: marketRows[0] }]);
  });
  it("skips a pair whose gap does not reach the threshold", () => {
    const result = buildInvestmentSwaps([{ player_id: "own3", name: "Own3", ml_prediction_3d: 0 } as PlayerRow], marketRows, 420_000);
    expect(result).toEqual([]);
  });
});

describe("recentTransfersWithin24h", () => {
  it("keeps entries within the last 24 hours and drops older ones", () => {
    const now = new Date("2026-08-03T12:00:00Z");
    const entries = [
      { player_id: "p1", player_name: "A", buyer: "X", seller: "Y", price: 1, date: "2026-08-03T10:00:00Z" },
      { player_id: "p2", player_name: "B", buyer: "X", seller: "Y", price: 1, date: "2026-08-01T10:00:00Z" },
    ];
    expect(recentTransfersWithin24h(entries, now).map((e) => e.player_id)).toEqual(["p1"]);
  });
});
```

- [ ] **Step 3: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd frontend && npm run test`
Expected: FAIL (die vier neuen Funktionen existieren noch nicht)

- [ ] **Step 4: Funktionen implementieren**

In `frontend/src/lib/derive.ts`, nach `buildAlleSpielerRows()` (nach Zeile ~393):

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

export function buildDashboardBuyCandidates(
  transfermarktRows: TransfermarktRow[],
  targets: RawWunschkaderTarget[]
): TransfermarktRow[] {
  const targetIds = new Set(targets.map((t) => t.player_id));
  return transfermarktRows.filter((r) => targetIds.has(r.player_id));
}

export interface InvestmentSwap { sell: PlayerRow; buy: TransfermarktRow }

export function buildInvestmentSwaps(
  ownRows: PlayerRow[],
  marketRows: TransfermarktRow[],
  minGap: number
): InvestmentSwap[] {
  const worstOwned = [...ownRows]
    .filter((r) => r.ml_prediction_3d !== null)
    .sort((a, b) => (a.ml_prediction_3d ?? 0) - (b.ml_prediction_3d ?? 0))
    .slice(0, 3);
  const bestMarket = [...marketRows]
    .filter((r) => r.ml_prediction_3d !== null)
    .sort((a, b) => (b.ml_prediction_3d ?? 0) - (a.ml_prediction_3d ?? 0))
    .slice(0, 3);
  const pairs: InvestmentSwap[] = [];
  for (let i = 0; i < Math.min(worstOwned.length, bestMarket.length); i++) {
    const sell = worstOwned[i];
    const buy = bestMarket[i];
    if ((buy.ml_prediction_3d ?? 0) - (sell.ml_prediction_3d ?? 0) >= minGap) {
      pairs.push({ sell, buy });
    }
  }
  return pairs;
}

export function recentTransfersWithin24h(entries: RecentTransferEntry[], now: Date): RecentTransferEntry[] {
  const cutoffMs = now.getTime() - 24 * 60 * 60 * 1000;
  return entries.filter((e) => {
    const t = parseIsoZ(e.date);
    return t !== null && t.getTime() >= cutoffMs;
  });
}
```

(`parseIsoZ` ist bereits in `derive.ts` vorhanden, gleiche Funktion, die auch der Auktions-Countdown nutzt — kein
neues Datums-Parsing erfinden.) `RecentTransferEntry`/`RawWunschkaderTarget` per Import aus `../types` ergänzen, falls
noch nicht im bestehenden `derive.ts`-Import-Block vorhanden.

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `cd frontend && npm run test`
Expected: alle Tests grün (bestehende 51 + neue 6 = 57).

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: 0 Fehler.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts
git commit -m "Dashboard: reine Ableitungsfunktionen (Verkaufen/Kaufen/Investment/Transfer-Feed-Filter)"
```

---

## Task 3: `TransfermarktCard`/`TransfermarktDetailModal` exportieren

**Files:**
- Modify: `frontend/src/components/TransfermarktTab.tsx`

**Interfaces:**
- Produziert: `export function TransfermarktCard(...)`, `export function TransfermarktDetailModal(...)` — Props
  unverändert (`TransfermarktCard: {row, bidHistory, thresholds, onSelect}`, `TransfermarktDetailModal: {row, mae,
  mae3d, bidHistory, positionNeed, onClose}`).

- [ ] **Step 1: Beide Funktionsdeklarationen mit `export` versehen**

`function TransfermarktCard({` (Zeile 388) → `export function TransfermarktCard({`
`function TransfermarktDetailModal({` (Zeile 283) → `export function TransfermarktDetailModal({`

Keine weitere Änderung — beide Komponenten werden weiterhin genauso von `TransfermarktTab`s eigenem Default-Export
genutzt wie bisher, nur zusätzlich von außen importierbar.

- [ ] **Step 2: Typecheck + Build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: beides erfolgreich (reines Sichtbarkeits-Keyword, keine Verhaltensänderung).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TransfermarktTab.tsx
git commit -m "TransfermarktCard/-DetailModal exportieren fuer Wiederverwendung im Dashboard-Tab"
```

---

## Task 4: `DashboardTab.tsx` (neue Komponente)

**Files:**
- Create: `frontend/src/components/DashboardTab.tsx`

**Interfaces:**
- Konsumiert: `buildDashboardSellCandidates`/`buildDashboardBuyCandidates`/`buildInvestmentSwaps`/
  `recentTransfersWithin24h` (Task 2), `TransfermarktCard`/`TransfermarktDetailModal` (Task 3).
- Produziert: `export default function DashboardTab({ data, wunschkader, transfermarktRows, now }: { data:
  DashboardSnapshot; wunschkader: { targets: RawWunschkaderTarget[] }; transfermarktRows: TransfermarktRow[]; now:
  number }): JSX.Element`

- [ ] **Step 1: Komponente schreiben**

```tsx
import { useState } from "react";
import type { DashboardSnapshot, RawWunschkaderTarget } from "../types";
import {
  buildDashboardBuyCandidates,
  buildDashboardSellCandidates,
  buildInvestmentSwaps,
  buildPlayerRow,
  liveModelMae,
  recentTransfersWithin24h,
  type TransfermarktRow,
} from "../lib/derive";
import { TransfermarktCard, TransfermarktDetailModal } from "./TransfermarktTab";
import { fmtNum, fmtSigned, formatRelativeTime, trendArrow, trendClass } from "../format";
import { PositionBadge, TeamCrest } from "./ui";

const ML_PREDICTION_3D_THRESHOLDS = { flat: 210_000, strong: 420_000 };
const MAX_OWNED_SQUAD_SIZE = 17;

export default function DashboardTab({
  data,
  wunschkader,
  transfermarktRows,
  now,
}: {
  data: DashboardSnapshot;
  wunschkader: { targets: RawWunschkaderTarget[] };
  transfermarktRows: TransfermarktRow[];
  now: number;
}) {
  const mae = liveModelMae(data.ml_metrics);
  const [selected, setSelected] = useState<TransfermarktRow | null>(null);

  const squadFull = data.own_squad_ids.length >= MAX_OWNED_SQUAD_SIZE;

  const sellCandidates = buildDashboardSellCandidates(data.players, data.own_squad_ids, data.calibration, mae);
  const buyCandidates = buildDashboardBuyCandidates(transfermarktRows, wunschkader.targets);

  // Investment betrachtet ALLE eigenen Spieler (nicht nur die sellSignal-
  // gefilterten sellCandidates) - Position/Verkaufssignal spielen hier bewusst
  // keine Rolle, siehe Spec Abschnitt E.
  const ownPlayerRows = data.own_squad_ids
    .map((pid) => data.players[pid])
    .filter((p): p is (typeof data.players)[string] => !!p)
    .map((p) => buildPlayerRow(p, data.calibration));
  const investmentSwaps = buildInvestmentSwaps(ownPlayerRows, transfermarktRows, ML_PREDICTION_3D_THRESHOLDS.strong);

  const recentTransfers = recentTransfersWithin24h(data.recent_transfers ?? [], new Date(now));

  const SellSection = (
    <Section key="verkaufen" title="Verkaufen" emptyText="Aktuell keine Verkaufskandidaten." isEmpty={sellCandidates.length === 0}>
      {sellCandidates.map((r) => (
        <PlayerRowCard key={r.player_id} name={r.name} position={r.position} teamName={r.team_name} marketValue={r.market_value} ml1d={r.ml_prediction} ml3d={r.ml_prediction_3d} />
      ))}
    </Section>
  );

  const BuySection = (
    <Section key="kaufen" title="Kaufen" emptyText="Aktuell keine Wunschkader-Ziele auf dem Markt." isEmpty={buyCandidates.length === 0}>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
        {buyCandidates.map((r) => (
          <TransfermarktCard key={r.player_id} row={r} bidHistory={data.bid_premium_history ?? []} thresholds={data.signal_thresholds} onSelect={() => setSelected(r)} />
        ))}
      </div>
    </Section>
  );

  const InvestmentSection = (
    <Section key="investment" title="Investment" emptyText="Aktuell keine Kapitalanlage-Swaps mit ausreichendem Abstand." isEmpty={investmentSwaps.length === 0}>
      {investmentSwaps.map((pair) => (
        <p key={pair.sell.player_id + pair.buy.player_id} className="text-sm text-slate-700 dark:text-slate-200">
          Verkaufen: {pair.sell.name} (
          <span className={trendClass(pair.sell.ml_prediction_3d)}>{fmtSigned(pair.sell.ml_prediction_3d)}</span>
          ) → Kaufen: {pair.buy.name} (
          <span className={trendClass(pair.buy.ml_prediction_3d)}>{fmtSigned(pair.buy.ml_prediction_3d)}</span>
          )
        </p>
      ))}
    </Section>
  );

  const FeedSection = (
    <Section key="feed" title="Letzte Transfers" emptyText="Keine Transfers in den letzten 24 Stunden." isEmpty={recentTransfers.length === 0}>
      {recentTransfers.map((t) => (
        <p key={t.player_id + t.date} className="text-sm text-slate-700 dark:text-slate-200">
          {t.player_name}: {t.seller} → {t.buyer}, {fmtNum(t.price)} ({formatRelativeTime(t.date, new Date(now))})
        </p>
      ))}
    </Section>
  );

  const sections = squadFull ? [SellSection, BuySection, InvestmentSection, FeedSection] : [BuySection, SellSection, InvestmentSection, FeedSection];

  return (
    <div>
      {squadFull && (
        <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          Kader voll (17/17)
        </div>
      )}
      {sections}
      {selected && (
        <TransfermarktDetailModal
          row={selected}
          mae={mae}
          mae3d={liveModelMae(data.ml_metrics_3d ?? null)}
          bidHistory={data.bid_premium_history ?? []}
          positionNeed={data.position_need ?? {}}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function Section({
  title, emptyText, isEmpty, children,
}: { title: string; emptyText: string; isEmpty: boolean; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h3>
      {isEmpty ? <p className="text-sm text-slate-500 dark:text-slate-400">{emptyText}</p> : <div className="space-y-2">{children}</div>}
    </div>
  );
}

function PlayerRowCard({
  name, position, teamName, marketValue, ml1d, ml3d,
}: { name: string; position: string; teamName: string | null; marketValue: number | null; ml1d: number | null; ml3d: number | null }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 text-sm dark:border-slate-800 dark:bg-slate-900">
      <TeamCrest teamName={teamName} />
      <span className="font-medium text-slate-900 dark:text-slate-50">{name}</span>
      <PositionBadge position={position} />
      <span className="text-slate-500 dark:text-slate-400">{fmtNum(marketValue)}</span>
      <span className={trendClass(ml1d)}>{trendArrow(ml1d, { flat: 20_000, strong: 100_000 })} {fmtSigned(ml1d)}</span>
      <span className={trendClass(ml3d)}>{trendArrow(ml3d, ML_PREDICTION_3D_THRESHOLDS)} {fmtSigned(ml3d)}</span>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: 0 Fehler (inkl. Korrektur des oben markierten Platzhalters).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DashboardTab.tsx
git commit -m "Neue DashboardTab-Komponente (Verkaufen/Kaufen/Investment/Transfer-Feed)"
```

---

## Task 5: In `App.tsx` verdrahten

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Import + TABS/ACTIVE_TABS ergänzen**

```ts
import DashboardTab from "./components/DashboardTab";
```

`TABS` (Zeile 34-43): neuer erster Eintrag `{ key: "dashboard", label: "Dashboard" },` vor `{ key: "team", ... }`.
`ACTIVE_TABS` (Zeile 44-52): `"dashboard"` ergänzen.

- [ ] **Step 2: Default-Fallback-Tab umstellen**

`readStoredActiveTab()` (Zeile 64-67): `return stored && ACTIVE_TABS.has(stored) ? stored : "team";` → `"dashboard"`
statt `"team"`.

- [ ] **Step 3: Render-Block ergänzen**

Direkt vor dem bestehenden `{loadState === "ready" && data && data.players && (<div className={activeTab === "spekulation" ...` Block:

```tsx
        {loadState === "ready" && data && data.players && wunschkader && (
          <div className={activeTab === "dashboard" ? "" : "hidden"}>
            <DashboardTab data={data} wunschkader={wunschkader} transfermarktRows={transfermarktRows} now={now} />
          </div>
        )}
```

- [ ] **Step 4: Typecheck + Build + volle Vitest-Suite**

Run: `cd frontend && npm run typecheck && npm run test && npm run build`
Expected: alle drei erfolgreich.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "Dashboard-Tab in App.tsx verdrahtet (neuer Standard-Tab)"
```

---

## Task 6: Finale Whole-Feature-Verifikation

- [ ] **Step 1: Volle Backend- + Frontend-Suite**

Run: `python3 -m unittest discover -s tests && cd frontend && npm run typecheck && npm run test && npm run build`
Expected: alles grün.

- [ ] **Step 2: Manueller Dev-Server-Test**

Dev-Server starten, "Dashboard"-Tab öffnen (sollte als erster Tab erscheinen und bei neuer Session/gelöschtem
`localStorage` automatisch aktiv sein). Prüfen:
- Kaderlimit-Banner erscheint nur, wenn `own_squad_ids.length >= 17` (aktuellen echten Stand gegenchecken).
- Sektionsreihenfolge stimmt mit dem Kaderlimit-Zustand überein (Kaufen zuerst wenn nicht voll, Verkaufen zuerst wenn voll).
- Verkaufen-Karten zeigen nur Spieler mit tatsächlich fallender Prognose.
- Kaufen-Karten sind klickbar und öffnen dieselbe Detailansicht wie im Transfermarkt-Tab.
- Investment-Paare (falls vorhanden) zeigen plausible Werte; bei keinem Paar über der Schwelle: Empty-State-Text.
- Transfer-Feed zeigt nur Einträge der letzten 24h, keine eigenen Trades.
- Light-/Dark-Mode beider neuer UI-Bereiche (Banner, Karten, Investment-Zeilen) lesbar.

- [ ] **Step 3: HANDOFF.md NICHT in diesem Task anfassen** (separate Dokumentations-Aktualisierung nach Abschluss aller Tasks, außerhalb dieses Plans).
