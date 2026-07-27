"""Baut die Datensaetze fuer die drei Dashboard-Ansichten (Transfermarkt/
Eigenes Team/Ligaanalyse) und rendert eine selbststaendige HTML-Datei -
Daten als JSON inline im <script>-Tag, KEIN externer fetch() einer
JSON-Datei (waere unter file:// durch Browser-CORS blockiert).

Eigener Lauf, unabhaengig von main.py (kein Discord-Versand): ruft
fetcher.run() selbst auf (frischer Snapshot, ueberschreibt den heutigen bei
einem zweiten Lauf am selben Tag - genau das will der 22:30-Uhr-Job) und
market_predictor.predict_market_value_changes() (ML-Prognosen). Die
K-Kalibrierung (player_valuation) wird NICHT taeglich neu gerechnet, nur der
zuletzt gespeicherte Stand gelesen (siehe player_valuation.load_calibration) -
das haelt diesen Lauf schnell/billig, K aendert sich ohnehin langsam.

`python -m src.dashboard_export`
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

from src import db, fetcher, market_predictor, player_valuation
from src.kickbase_client import KickbaseError, get_manager_squad, get_me, login

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "dashboard.html"
WUNSCHKADER_PATH = Path(__file__).resolve().parent.parent / "data" / "wunschkader.json"

# Toleranzband aus MDs/methodik.md, Abschnitt "Fairwert und Signal".
SIGNAL_GOOD = 1.25
SIGNAL_CRITICAL = 0.80


def _k_per_point(market_value, points_avg):
    if not points_avg or market_value is None:
        return None
    return market_value / points_avg


def _valuation(market_value, points_avg, position, calibration):
    """Fairwert/Signal nach MDs/methodik.md, mit dem Positions-K falls
    kalibriert vorhanden - sonst (None, None), Aufrufer zeigt 'nicht
    kalibriert' statt eine falsche Zahl zu raten."""
    kp = _k_per_point(market_value, points_avg)
    if kp is None or calibration is None:
        return None, None
    k = player_valuation.k_for_position(calibration, position)
    if not k:
        return None, None
    return round(points_avg * k), round(k / kp, 2)


def _trend_direction(change_7d) -> str:
    if change_7d is None or change_7d == 0:
        return "flat"
    return "up" if change_7d > 0 else "down"


def _player_row(row: sqlite3.Row, calibration: dict | None, predictions: dict | None) -> dict:
    fairwert, signal = _valuation(row["market_value"], row["average_points"], row["position"], calibration)
    ml_prediction = None
    if predictions is not None:
        ml_prediction = predictions.get("predictions", {}).get(row["player_id"])
    kp = _k_per_point(row["market_value"], row["average_points"])
    return {
        "player_id": row["player_id"],
        "name": row["name"],
        "position": row["position"],
        "team_name": row["team_name"],
        "status_label": row["status_label"],
        "starting_rank": row["starting_rank"],
        "market_value": row["market_value"],
        "market_value_change_7d": row["market_value_change_7d"],
        "market_value_low_92d": row["market_value_low_92d"],
        "market_value_high_92d": row["market_value_high_92d"],
        "trend_direction": _trend_direction(row["market_value_change_7d"]),
        "average_points": row["average_points"],
        "total_points": row["total_points"],
        "cost_per_point": round(kp) if kp else None,
        "fairwert": fairwert,
        "signal": signal,
        "ml_prediction": ml_prediction,
    }


def _build_transfermarkt(market_listings, calibration, predictions, own_available_budget) -> list[dict]:
    rows = []
    for r in market_listings:
        row = _player_row(r, calibration, predictions)
        row.update(
            {
                "price": r["price"],
                "price_delta_pct": r["price_delta_pct"],
                "offering_username": r["offering_username"],
                "is_system_offer": bool(r["is_system_offer"]),
                "pending_offers_count": r["pending_offers_count"],
                "leading_bid_username": r["leading_bid_username"],
                "leading_bid_price": r["leading_bid_price"],
                "is_own_leading_bid": bool(r["is_own_leading_bid"]),
                "affordable": (
                    own_available_budget is not None
                    and r["price"] is not None
                    and r["price"] <= own_available_budget
                ),
            }
        )
        rows.append(row)
    return rows


def _build_eigenes_team(own_squad, calibration, predictions) -> list[dict]:
    return [_player_row(r, calibration, predictions) for r in own_squad]


HYPE_CHANGE_THRESHOLD = 1_500_000
SPEKULATION_FLOOR_PROTECTED = 1_000_000


def _is_hype_gipfel(row: dict) -> bool:
    """Drei Merkmale aus MDs/methodik.md, Abschnitt 'Der Hype-Gipfel':
    starker 7-Tage-Sprung, Marktwert auf dem 92-Tage-Hoch, kein
    Punkteschnitt - Nachrichten-Hype statt Leistungssignal, klassische
    Kaufwarnung (nicht als Spekulationskandidat geeignet)."""
    return bool(
        row.get("market_value_change_7d")
        and row["market_value_change_7d"] > HYPE_CHANGE_THRESHOLD
        and row.get("market_value") is not None
        and row.get("market_value_high_92d") == row.get("market_value")
        and not row.get("average_points")
    )


def _build_spekulation(transfermarkt_rows: list[dict]) -> list[dict]:
    """Kauf-und-Wiederverkauf-Kandidaten: nur Systemangebote (Kickbase
    selbst, Festpreis = Marktwert, kein Verhandlungsaufschlag durch einen
    Mitspieler), positive ML-Prognose, kein Hype-Gipfel-Verdacht.
    ML-Prognose ist nur eine 1-Tages-Vorhersage (Modell wird taeglich neu
    trainiert) - die eigentliche Spekulation stuetzt sich auf den bereits
    laufenden 7-Tage-Trend, nicht allein auf das Modell."""
    rows = []
    for r in transfermarkt_rows:
        if not r.get("is_system_offer"):
            continue
        if not r.get("ml_prediction") or r["ml_prediction"] <= 0 or not r.get("price"):
            continue
        rows.append(
            {
                "name": r["name"],
                "position": r["position"],
                "team_name": r["team_name"],
                "price": r["price"],
                "market_value_change_7d": r["market_value_change_7d"],
                "ml_prediction": r["ml_prediction"],
                "roi_pct": round(r["ml_prediction"] / r["price"] * 100, 1),
                "average_points": r["average_points"],
                "is_hype_gipfel": _is_hype_gipfel(r),
                "near_floor": bool(r["price"] and r["price"] < SPEKULATION_FLOOR_PROTECTED),
            }
        )
    rows.sort(key=lambda r: -r["roi_pct"])
    return rows


def _build_ligaanalyse(token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad) -> list[dict]:
    budgets_by_user = {b["user_id"]: b for b in manager_budget_rows}
    sell_counts: dict[str, int] = {}
    for listing in market_listings:
        uid = listing["offering_user_id"]
        if uid:
            sell_counts[uid] = sell_counts.get(uid, 0) + 1

    rows = []
    for r in ranking_rows:
        user_id = r["user_id"]
        budget_row = budgets_by_user.get(user_id)
        is_self = bool(budget_row and budget_row["is_own_exact"])

        if is_self:
            squad_size = len(own_squad)
            squad_value = sum((p["market_value"] or 0) for p in own_squad)
        else:
            try:
                squad = get_manager_squad(token, league_id, user_id)
                items = squad.get("it", [])
                squad_size = squad.get("nps") or len(items)
                squad_value = sum((item.get("mv") or 0) for item in items)
            except KickbaseError as exc:
                print(f"Warnung: Kader von Manager {r['name']} nicht ladbar: {exc}", file=sys.stderr)
                squad_size, squad_value = None, None

        rows.append(
            {
                "name": r["name"],
                "is_self": is_self,
                "season_placement": r["season_placement"],
                "season_points": r["season_points"],
                "team_value": r["team_value"],
                "matchday_points": r["matchday_points"],
                "recent_matchday_points": r["recent_matchday_points"],
                "estimated_budget": budget_row["estimated_budget"] if budget_row else None,
                "available_budget": budget_row["available_budget"] if budget_row else None,
                "trade_count": budget_row["trade_count"] if budget_row else None,
                "squad_size": squad_size,
                "squad_value": squad_value,
                "sell_count": sell_counts.get(user_id, 0),
            }
        )
    rows.sort(key=lambda row: (row["season_placement"] is None, row["season_placement"] or 0))
    return rows


def _load_wunschkader() -> dict | None:
    """Handgepflegte Zielspieler-Liste (siehe MDs/kaderplan.md fuer die
    Begruendungen), NICHT automatisch generiert - bei jeder Aenderung des
    Kaderplans auch diese Datei nachziehen."""
    if not WUNSCHKADER_PATH.exists():
        return None
    return json.loads(WUNSCHKADER_PATH.read_text(encoding="utf-8"))


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


def _build_wunschkader(
    wunschkader: dict,
    all_players: list[dict],
    owned_by: dict,
    own_squad_names: set,
    market_by_name: dict,
    calibration: dict | None,
    predictions: dict | None,
) -> list[dict]:
    by_name = {p["name"]: p for p in all_players}
    markup_rules = wunschkader.get("markup_rules")
    rows = []
    for target in wunschkader.get("targets", []):
        name = target["name"]
        live = by_name.get(name)
        is_own = name in own_squad_names

        if is_own:
            status = "Eigener Kader"
        elif name in market_by_name:
            m = market_by_name[name]
            anbieter = "System" if m["is_system_offer"] else m["offering_username"]
            status = f"Markt ({anbieter}, {m['price']:,})"
        elif live and owned_by.get(live["player_id"]):
            status = f"Bei {owned_by[live['player_id']]}"
        elif live:
            status = "Frei"
        else:
            status = "Nicht gefunden"

        market_value = live.get("market_value") if live else None
        points_avg = live.get("points_avg") if live else None
        signal = None
        if live and calibration and market_value and points_avg:
            k = player_valuation.k_for_position(calibration, target["position"])
            if k:
                signal = round(k / (market_value / points_avg), 2)

        if "actual_bid" in target:
            planned_price = target["actual_bid"]
        elif is_own:
            planned_price = 0
        else:
            planned_price = _estimate_price(market_value, markup_rules)

        rows.append(
            {
                "name": name,
                "position": target["position"],
                "role": target["role"],
                "note": target.get("note"),
                "planned_price": planned_price,
                "is_estimate": "actual_bid" not in target and not is_own,
                "status": status,
                "market_value": market_value,
                "points_avg": points_avg,
                "starting_rank": live.get("starting_rank") if live else None,
                "status_code": live.get("status_code") if live else None,
                "signal": signal,
                "ml_prediction": (
                    predictions.get("predictions", {}).get(live["player_id"])
                    if (predictions and live)
                    else None
                ),
            }
        )
    return rows


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
    committed = sum(
        (r["planned_price"] or 0) for r in wunschkader_rows if r["role"] not in ("Bank/Backup-Option",)
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


def _load_snapshot(fetched_at: str):
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    try:
        own_squad = conn.execute(
            "SELECT * FROM own_squad WHERE fetched_at = ? ORDER BY position, name", (fetched_at,)
        ).fetchall()
        market_listings = conn.execute(
            "SELECT * FROM market_listings WHERE fetched_at = ? ORDER BY position, name", (fetched_at,)
        ).fetchall()
        ranking_rows = conn.execute(
            "SELECT * FROM league_ranking WHERE fetched_at = ? ORDER BY season_placement", (fetched_at,)
        ).fetchall()
        manager_budget_rows = conn.execute(
            "SELECT * FROM manager_budgets WHERE fetched_at = ?", (fetched_at,)
        ).fetchall()
        return own_squad, market_listings, ranking_rows, manager_budget_rows
    finally:
        conn.close()


def export() -> Path:
    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)")

    fetched_at = fetcher.run()

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    competition_id = get_me(token, league_id).get("cpi") or "1"

    predictions = market_predictor.predict_market_value_changes()
    calibration = player_valuation.load_calibration()

    own_squad, market_listings, ranking_rows, manager_budget_rows = _load_snapshot(fetched_at)

    own_budget_row = next((b for b in manager_budget_rows if b["is_own_exact"]), None)
    own_available_budget = own_budget_row["available_budget"] if own_budget_row else None

    wunschkader_config = _load_wunschkader()
    wunschkader_rows = []
    if wunschkader_config:
        own_name = own_budget_row["name"] if own_budget_row else None
        all_players = player_valuation.fetch_all_players(token, competition_id)
        owned_by = (
            player_valuation.resolve_ownership(token, league_id, [dict(r) for r in ranking_rows], own_name)
            if own_name
            else {}
        )
        own_squad_names = {r["name"] for r in own_squad}
        market_by_name = {r["name"]: r for r in market_listings}
        wunschkader_rows = _build_wunschkader(
            wunschkader_config, all_players, owned_by, own_squad_names, market_by_name, calibration, predictions
        )

    budget_plan = (
        _build_budget_plan(
            wunschkader_config, wunschkader_rows, own_squad, own_budget_row["estimated_budget"] if own_budget_row else None, fetched_at
        )
        if wunschkader_config
        else None
    )

    transfermarkt_rows = _build_transfermarkt(market_listings, calibration, predictions, own_available_budget)

    data = {
        "fetched_at": fetched_at,
        "own_available_budget": own_available_budget,
        "own_budget_exact": own_budget_row["estimated_budget"] if own_budget_row else None,
        "team_total_value": sum((p["market_value"] or 0) for p in own_squad),
        "calibration": calibration,
        "ml_metrics": predictions["metrics"] if predictions else None,
        "signal_thresholds": {"good": SIGNAL_GOOD, "critical": SIGNAL_CRITICAL},
        "transfermarkt": transfermarkt_rows,
        "eigenes_team": _build_eigenes_team(own_squad, calibration, predictions),
        "ligaanalyse": _build_ligaanalyse(
            token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad
        ),
        "wunschkader": wunschkader_rows,
        "wunschkader_formation": wunschkader_config.get("formation") if wunschkader_config else None,
        "wunschkader_updated_at": wunschkader_config.get("updated_at") if wunschkader_config else None,
        "budget_plan": budget_plan,
        "spekulation": _build_spekulation(transfermarkt_rows),
    }

    html = _render_html(data)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    return OUTPUT_PATH


def _render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__DASHBOARD_DATA__", payload)


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KickbaseAgent Dashboard</title>
<style>
:root {
  color-scheme: light;
  --surface-1: #fcfcfb;
  --page: #f9f9f7;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --gridline: #e1e0d9;
  --border: rgba(11,11,11,0.10);
  --accent: #2a78d6;
  --good: #0ca30c;
  --warning: #fab219;
  --serious: #ec835a;
  --critical: #d03b3b;
  --up: #006300;
  --down: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --gridline: #2c2c2a;
    --border: rgba(255,255,255,0.10);
    --accent: #3987e5;
    --good: #0ca30c;
    --warning: #fab219;
    --serious: #ec835a;
    --critical: #e66767;
    --up: #0ca30c;
    --down: #e66767;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page);
  color: var(--text-primary);
}
header {
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--border);
}
header h1 { margin: 0 0 6px; font-size: 1.3rem; }
#meta { color: var(--text-secondary); font-size: 0.85rem; line-height: 1.5; }
#meta b { color: var(--text-primary); }
nav.tabs {
  display: flex;
  gap: 4px;
  padding: 12px 24px 0;
  border-bottom: 1px solid var(--border);
}
.tab-btn {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.95rem;
  padding: 10px 16px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}
.tab-btn.active { color: var(--text-primary); border-bottom-color: var(--accent); font-weight: 600; }
.tab-btn:hover { color: var(--text-primary); }
main { padding: 16px 24px 40px; overflow-x: auto; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
  background: var(--surface-1);
}
th, td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--gridline);
  text-align: left;
  white-space: nowrap;
}
th {
  color: var(--text-secondary);
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  position: sticky;
  top: 0;
  background: var(--surface-1);
}
th:hover { color: var(--text-primary); }
th.sorted::after { content: " " attr(data-dir); color: var(--accent); }
tbody tr:hover { background: color-mix(in srgb, var(--accent) 6%, transparent); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.muted { color: var(--text-muted); }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}
.pill-good { color: var(--good); background: color-mix(in srgb, var(--good) 14%, transparent); }
.pill-warn { color: var(--warning); background: color-mix(in srgb, var(--warning) 20%, transparent); }
.pill-crit { color: var(--critical); background: color-mix(in srgb, var(--critical) 14%, transparent); }
.trend-up { color: var(--up); font-weight: 600; }
.trend-down { color: var(--down); font-weight: 600; }
.trend-flat { color: var(--text-muted); }
.self-row { font-weight: 600; }
.section-hint { color: var(--text-muted); font-size: 0.8rem; margin: 0 0 10px; }
.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 0 0 12px;
  padding: 8px 12px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.85rem;
}
.filter-bar label { display: flex; align-items: center; gap: 6px; color: var(--text-secondary); }
.filter-bar select {
  font: inherit;
  color: var(--text-primary);
  background: var(--page);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 6px;
}
.budget-plan {
  margin: 0 0 16px;
  padding: 12px 16px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.budget-plan h3 { margin: 0 0 10px; font-size: 0.95rem; }
.budget-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px 16px;
  font-variant-numeric: tabular-nums;
  font-size: 0.9rem;
  margin-bottom: 8px;
}
.budget-grid > div { white-space: nowrap; }
</style>
</head>
<body>
<header>
  <h1>KickbaseAgent Dashboard</h1>
  <div id="meta"></div>
</header>
<nav class="tabs">
  <button class="tab-btn active" data-tab="transfermarkt">Transfermarkt</button>
  <button class="tab-btn" data-tab="team">Eigenes Team</button>
  <button class="tab-btn" data-tab="liga">Ligaanalyse</button>
  <button class="tab-btn" data-tab="wunschkader">Wunschkader</button>
  <button class="tab-btn" data-tab="spekulation">Spekulation</button>
</nav>
<main>
  <section id="tab-transfermarkt" class="tab-panel active"></section>
  <section id="tab-team" class="tab-panel"></section>
  <section id="tab-liga" class="tab-panel"></section>
  <section id="tab-wunschkader" class="tab-panel"></section>
  <section id="tab-spekulation" class="tab-panel"></section>
</main>
<script>
const DATA = __DASHBOARD_DATA__;

function fmtNum(n) {
  if (n === null || n === undefined) return "–";
  return Math.round(n).toLocaleString("de-DE");
}
function fmtPct(n) {
  if (n === null || n === undefined) return "–";
  return (n > 0 ? "+" : "") + n.toFixed(1) + "%";
}
function fmtSigned(n) {
  if (n === null || n === undefined) return "–";
  return (n > 0 ? "+" : "") + fmtNum(n);
}
function trendCell(row) {
  const arrow = row.trend_direction === "up" ? "▲" : row.trend_direction === "down" ? "▼" : "–";
  const cls = "trend-" + row.trend_direction;
  return `<span class="${cls}">${arrow} ${fmtSigned(row.market_value_change_7d)}</span>`;
}
function signalPill(signal) {
  if (signal === null || signal === undefined) return '<span class="muted">nicht kalibriert</span>';
  const t = DATA.signal_thresholds;
  let cls = "pill-warn", label = "im Rauschen";
  if (signal > t.good) { cls = "pill-good"; label = "unter Fairwert"; }
  else if (signal < t.critical) { cls = "pill-crit"; label = "Praemie"; }
  return `<span class="pill ${cls}">${signal.toFixed(2)} · ${label}</span>`;
}
function mlCell(v) {
  if (v === null || v === undefined) return '<span class="muted">n/v</span>';
  const cls = v > 0 ? "trend-up" : v < 0 ? "trend-down" : "trend-flat";
  return `<span class="${cls}">${fmtSigned(v)}</span>`;
}

function renderMeta() {
  const el = document.getElementById("meta");
  const parts = [];
  parts.push(`Stand: <b>${DATA.fetched_at}</b>`);
  parts.push(`Eigenes Budget: <b>${fmtNum(DATA.own_budget_exact)}</b> (verfuegbar inkl. Ueberziehung: <b>${fmtNum(DATA.own_available_budget)}</b>)`);
  parts.push(`Team-Gesamtwert: <b>${fmtNum(DATA.team_total_value)}</b>`);
  if (DATA.calibration) {
    parts.push(`K-Kalibrierung vom <b>${DATA.calibration.calibrated_at}</b> (n=${DATA.calibration.n}, global K=${fmtNum(DATA.calibration.global_k)})`);
  } else {
    parts.push(`K-Kalibrierung: <b class="muted">nie gelaufen</b> (python -m src.player_valuation)`);
  }
  if (DATA.ml_metrics) {
    parts.push(`ML-Modell: R²=${DATA.ml_metrics.r2}, Richtung korrekt ${DATA.ml_metrics.sign_accuracy}%`);
  } else {
    parts.push(`ML-Modell: <b class="muted">keine Prognose verfuegbar</b>`);
  }
  el.innerHTML = parts.join(" &nbsp;·&nbsp; ");
}

function makeSortable(table, getRows, tbody, renderRow) {
  let sortKey = null, sortDir = 1;
  function draw() {
    let data = getRows().slice();
    if (sortKey) {
      data.sort((a, b) => {
        let av = a[sortKey], bv = b[sortKey];
        if (av === null || av === undefined) av = -Infinity;
        if (bv === null || bv === undefined) bv = -Infinity;
        if (typeof av === "string") return av.localeCompare(bv) * sortDir;
        return (av - bv) * sortDir;
      });
    }
    tbody.innerHTML = data.map(renderRow).join("");
  }
  table.querySelectorAll("th[data-key]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (sortKey === key) { sortDir *= -1; } else { sortKey = key; sortDir = 1; }
      table.querySelectorAll("th").forEach((h) => { h.classList.remove("sorted"); h.removeAttribute("data-dir"); });
      th.classList.add("sorted");
      th.setAttribute("data-dir", sortDir === 1 ? "▲" : "▼");
      draw();
    });
  });
  draw();
  return draw;
}

function buildTable(containerId, columns, getRows, renderRow, hint, filterBarHtml) {
  const container = document.getElementById(containerId);
  const hintHtml = hint ? `<p class="section-hint">${hint}</p>` : "";
  container.innerHTML = `${filterBarHtml || ""}${hintHtml}<table>
    <thead><tr>${columns.map((c) => `<th data-key="${c.key}" class="${c.numeric ? 'num' : ''}">${c.label}</th>`).join("")}</tr></thead>
    <tbody></tbody>
  </table>`;
  const table = container.querySelector("table");
  const tbody = container.querySelector("tbody");
  return makeSortable(table, getRows, tbody, renderRow);
}

function renderTransfermarkt() {
  const allRows = DATA.transfermarkt;
  const filters = { position: "all", anbieter: "all" };
  const positions = ["Torwart", "Abwehr", "Mittelfeld", "Sturm"];
  function getRows() {
    return allRows.filter((r) => {
      if (filters.position !== "all" && r.position !== filters.position) return false;
      if (filters.anbieter === "kickbase" && !r.is_system_offer) return false;
      if (filters.anbieter === "mitspieler" && r.is_system_offer) return false;
      return true;
    });
  }
  const columns = [
    { key: "name", label: "Spieler" },
    { key: "position", label: "Pos." },
    { key: "team_name", label: "Verein" },
    { key: "price", label: "Preis", numeric: true },
    { key: "price_delta_pct", label: "Delta%", numeric: true },
    { key: "offering_username", label: "Anbieter" },
    { key: "average_points", label: "Schnitt", numeric: true },
    { key: "cost_per_point", label: "K/Punkt", numeric: true },
    { key: "signal", label: "Signal", numeric: true },
    { key: "market_value_change_7d", label: "Trend 7T", numeric: true },
    { key: "ml_prediction", label: "ML-Prognose", numeric: true },
    { key: "starting_rank", label: "Startelf-Rang", numeric: true },
    { key: "affordable", label: "Leistbar" },
  ];
  const renderRow = (r) => `<tr>
    <td>${r.name}</td>
    <td>${r.position}</td>
    <td>${r.team_name ?? ""}</td>
    <td class="num">${fmtNum(r.price)}</td>
    <td class="num">${fmtPct(r.price_delta_pct)}</td>
    <td>${r.is_system_offer ? '<span class="muted">Kickbase</span>' : (r.offering_username ?? "")}</td>
    <td class="num">${fmtNum(r.average_points)}</td>
    <td class="num">${fmtNum(r.cost_per_point)}</td>
    <td class="num">${signalPill(r.signal)}</td>
    <td class="num">${trendCell(r)}</td>
    <td class="num">${mlCell(r.ml_prediction)}</td>
    <td class="num">${r.starting_rank ?? '<span class="muted">n/v</span>'}</td>
    <td>${r.affordable ? '<span class="pill pill-good">ja</span>' : '<span class="pill pill-crit">nein</span>'}</td>
  </tr>`;
  const filterBar = `<div class="filter-bar">
    <label>Position <select id="tf-filter-position">
      <option value="all">Alle</option>
      ${positions.map((p) => `<option value="${p}">${p}</option>`).join("")}
    </select></label>
    <label>Anbieter <select id="tf-filter-anbieter">
      <option value="all">Alle</option>
      <option value="kickbase">Nur Kickbase</option>
      <option value="mitspieler">Nur Mitspieler</option>
    </select></label>
    <span id="tf-filter-count" class="muted"></span>
  </div>`;

  const redraw = buildTable("tab-transfermarkt", columns, getRows, renderRow,
    "Signal &gt; 1,25 = deutlich unter Fairwert, &lt; 0,80 = Praemie (siehe MDs/methodik.md). Spaltenkopf klicken zum Sortieren.",
    filterBar);

  const container = document.getElementById("tab-transfermarkt");
  const countEl = container.querySelector("#tf-filter-count");
  function updateCount() {
    countEl.textContent = `${getRows().length} von ${allRows.length} Angeboten`;
  }
  container.querySelector("#tf-filter-position").addEventListener("change", (e) => {
    filters.position = e.target.value;
    redraw();
    updateCount();
  });
  container.querySelector("#tf-filter-anbieter").addEventListener("change", (e) => {
    filters.anbieter = e.target.value;
    redraw();
    updateCount();
  });
  updateCount();
}

function renderTeam() {
  const rows = DATA.eigenes_team;
  const columns = [
    { key: "name", label: "Spieler" },
    { key: "position", label: "Pos." },
    { key: "team_name", label: "Verein" },
    { key: "market_value", label: "Marktwert", numeric: true },
    { key: "market_value_change_7d", label: "Trend 7T", numeric: true },
    { key: "market_value_low_92d", label: "Tief 92T", numeric: true },
    { key: "market_value_high_92d", label: "Hoch 92T", numeric: true },
    { key: "average_points", label: "Schnitt", numeric: true },
    { key: "cost_per_point", label: "K/Punkt", numeric: true },
    { key: "signal", label: "Signal", numeric: true },
    { key: "ml_prediction", label: "ML-Prognose", numeric: true },
    { key: "starting_rank", label: "Startelf-Rang", numeric: true },
    { key: "status_label", label: "Status" },
  ];
  const renderRow = (r) => `<tr>
    <td>${r.name}</td>
    <td>${r.position}</td>
    <td>${r.team_name ?? ""}</td>
    <td class="num">${fmtNum(r.market_value)}</td>
    <td class="num">${trendCell(r)}</td>
    <td class="num">${fmtNum(r.market_value_low_92d)}</td>
    <td class="num">${fmtNum(r.market_value_high_92d)}</td>
    <td class="num">${fmtNum(r.average_points)}</td>
    <td class="num">${fmtNum(r.cost_per_point)}</td>
    <td class="num">${signalPill(r.signal)}</td>
    <td class="num">${mlCell(r.ml_prediction)}</td>
    <td class="num">${r.starting_rank ?? '<span class="muted">n/v</span>'}</td>
    <td>${r.status_label ? `<span class="pill pill-warn">${r.status_label}</span>` : ""}</td>
  </tr>`;
  buildTable("tab-team", columns, () => rows, renderRow,
    "Signal/ML-Prognose sind Zusatzsignale, kein Ersatz fuer die Startelf-Recherche (siehe MDs/methodik.md).");
}

function renderLiga() {
  const rows = DATA.ligaanalyse;
  const columns = [
    { key: "name", label: "Manager" },
    { key: "season_placement", label: "Platz", numeric: true },
    { key: "season_points", label: "Punkte", numeric: true },
    { key: "team_value", label: "Teamwert", numeric: true },
    { key: "squad_size", label: "Kadergroesse", numeric: true },
    { key: "squad_value", label: "Kaderwert", numeric: true },
    { key: "estimated_budget", label: "Budget", numeric: true },
    { key: "available_budget", label: "Verfuegbar", numeric: true },
    { key: "sell_count", label: "Verkaufsangebote", numeric: true },
  ];
  const renderRow = (r) => `<tr class="${r.is_self ? 'self-row' : ''}">
    <td>${r.name}${r.is_self ? " (ich)" : ""}</td>
    <td class="num">${fmtNum(r.season_placement)}</td>
    <td class="num">${fmtNum(r.season_points)}</td>
    <td class="num">${fmtNum(r.team_value)}</td>
    <td class="num">${fmtNum(r.squad_size)}</td>
    <td class="num">${fmtNum(r.squad_value)}</td>
    <td class="num">${fmtNum(r.estimated_budget)}${r.is_self ? "" : ' <span class="muted">(geschaetzt)</span>'}</td>
    <td class="num">${fmtNum(r.available_budget)}</td>
    <td class="num">${fmtNum(r.sell_count)}</td>
  </tr>`;
  buildTable("tab-liga", columns, () => rows, renderRow,
    "Budgets ausser der eigenen Zeile sind Schaetzungen aus dem Activity-Feed (siehe MDs/methodik.md).");
}

function wunschStatusPill(status) {
  if (status.startsWith("Eigener Kader")) return `<span class="pill pill-good">${status}</span>`;
  if (status.startsWith("Markt")) return `<span class="pill pill-good">${status}</span>`;
  if (status.startsWith("Frei")) return `<span class="pill pill-warn">${status}</span>`;
  if (status.startsWith("Bei")) return `<span class="pill pill-crit">${status}</span>`;
  return `<span class="muted">${status}</span>`;
}

function renderBudgetPlan(bp) {
  if (!bp) return "";
  const sellList = (bp.sell_rows || []).map((r) => `${r.name} (${fmtNum(r.market_value)})`).join(", ") || "keine";
  return `<div class="budget-plan">
    <h3>Budget-Planung</h3>
    <div class="budget-grid">
      <div><span class="muted">Cash</span><br>${fmtNum(bp.cash)}</div>
      <div><span class="muted">+ Verkaufserlöse</span><br>${fmtNum(bp.sell_proceeds)}</div>
      <div><span class="muted">+ Login-Prämie bis ${bp.season_start ?? "?"}</span><br>${fmtNum(bp.login_bonus_projection)}</div>
      <div><span class="muted">= Pool</span><br><b>${fmtNum(bp.pool)}</b></div>
      <div><span class="muted">- Eingeplant</span><br>${fmtNum(bp.committed)}</div>
      <div><span class="muted">= Rest</span><br><b class="${bp.remaining >= 0 ? "trend-up" : "trend-down"}">${fmtSigned(bp.remaining)}</b></div>
    </div>
    <p class="section-hint">Verkauf eingeplant: ${sellList}. Login-Prämie ist eine Schätzung (Deckel unbestätigt, setzt tägliche Streak voraus, siehe MDs/kaderplan.md). "Eingeplant" zählt nur Starter/Backup, nicht die bedingten Bank-Optionen.</p>
  </div>`;
}

function renderWunschkader() {
  const rows = DATA.wunschkader;
  if (!rows || !rows.length) {
    document.getElementById("tab-wunschkader").innerHTML =
      '<p class="section-hint">Kein Wunschkader hinterlegt (data/wunschkader.json fehlt oder ist leer).</p>';
    return;
  }
  const columns = [
    { key: "position", label: "Pos." },
    { key: "name", label: "Spieler" },
    { key: "role", label: "Rolle" },
    { key: "status", label: "Status" },
    { key: "market_value", label: "Marktwert", numeric: true },
    { key: "planned_price", label: "Geplant", numeric: true },
    { key: "points_avg", label: "Schnitt", numeric: true },
    { key: "signal", label: "Signal", numeric: true },
    { key: "ml_prediction", label: "ML-Prognose", numeric: true },
    { key: "starting_rank", label: "Rang", numeric: true },
    { key: "note", label: "Notiz" },
  ];
  const renderRow = (r) => `<tr>
    <td>${r.position}</td>
    <td>${r.name}</td>
    <td>${r.role}</td>
    <td>${wunschStatusPill(r.status)}</td>
    <td class="num">${fmtNum(r.market_value)}</td>
    <td class="num">${fmtNum(r.planned_price)}${r.is_estimate ? ' <span class="muted">(gesch.)</span>' : ""}</td>
    <td class="num">${fmtNum(r.points_avg)}</td>
    <td class="num">${signalPill(r.signal)}</td>
    <td class="num">${mlCell(r.ml_prediction)}</td>
    <td class="num">${r.starting_rank ?? '<span class="muted">n/v</span>'}</td>
    <td class="muted">${r.note ?? ""}</td>
  </tr>`;
  const formation = DATA.wunschkader_formation ? ` (${DATA.wunschkader_formation})` : "";
  const updated = DATA.wunschkader_updated_at ? `, Stand ${DATA.wunschkader_updated_at}` : "";
  buildTable("tab-wunschkader", columns, () => rows, renderRow,
    `Ziel-Kader${formation}${updated} - siehe MDs/kaderplan.md fuer die volle Begruendung. ` +
    "Status: gruen = sofort erreichbar/schon im Kader, gelb = frei (wartet auf Marktauftauchen), rot = bei einem Gegner. " +
    '"(gesch.)" = geschaetzter Preis (Marktwert + Aufschlag), sonst echtes/platziertes Gebot.',
    renderBudgetPlan(DATA.budget_plan));
}

function renderSpekulation() {
  const rows = DATA.spekulation;
  if (!rows || !rows.length) {
    document.getElementById("tab-spekulation").innerHTML =
      '<p class="section-hint">Aktuell keine Spekulations-Kandidaten mit positiver ML-Prognose auf dem Markt.</p>';
    return;
  }
  const columns = [
    { key: "name", label: "Spieler" },
    { key: "position", label: "Pos." },
    { key: "team_name", label: "Verein" },
    { key: "price", label: "Preis", numeric: true },
    { key: "market_value_change_7d", label: "Trend 7T", numeric: true },
    { key: "ml_prediction", label: "ML-Prognose", numeric: true },
    { key: "roi_pct", label: "Rendite%", numeric: true },
    { key: "average_points", label: "Schnitt", numeric: true },
  ];
  const renderRow = (r) => `<tr>
    <td>${r.name}${r.is_hype_gipfel ? ' <span class="pill pill-crit">Hype-Gipfel</span>' : ""}${r.near_floor ? ' <span class="pill pill-good">Boden-Schutz</span>' : ""}</td>
    <td>${r.position}</td>
    <td>${r.team_name ?? ""}</td>
    <td class="num">${fmtNum(r.price)}</td>
    <td class="num">${fmtSigned(r.market_value_change_7d)}</td>
    <td class="num">${mlCell(r.ml_prediction)}</td>
    <td class="num">${r.roi_pct.toFixed(1)}%</td>
    <td class="num">${fmtNum(r.average_points)}</td>
  </tr>`;
  buildTable("tab-spekulation", columns, () => rows, renderRow,
    "Kauf-und-Wiederverkauf-Kandidaten, nur Systemangebote (Festpreis = Marktwert, kein Mitspieler-Aufschlag), positive ML-Prognose, sortiert nach Rendite%. " +
    '"Hype-Gipfel" (rot) = Warnung aus MDs/methodik.md: starker 7-Tage-Sprung + 92-Tage-Hoch + kein Punkteschnitt, meist Nachrichten-Hype statt echtes Signal - NICHT zum Kauf geeignet. ' +
    '"Boden-Schutz" (gruen) = Preis unter 1 Mio., nahe am 500k-Mindestwert, begrenztes Abwaertsrisiko. ' +
    "ML-Prognose ist nur eine 1-Tages-Vorhersage - Spekulation stuetzt sich auf den laufenden Trend, nicht allein aufs Modell.");
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
  });
});

renderMeta();
renderTransfermarkt();
renderTeam();
renderLiga();
renderWunschkader();
renderSpekulation();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    try:
        path = export()
        print(f"Dashboard geschrieben: {path}")
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Dashboard-Export fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
