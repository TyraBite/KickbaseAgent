"""Baut den Datensatz fuer die drei Dashboard-Ansichten (Transfermarkt/
Eigenes Team/Ligaanalyse) - komplett berechnetes dict (Joins/ML/Fairwert
schon gemischt). Seit Phase 2 (siehe
docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md)
KEIN HTML-Rendering mehr hier: index.html ist ein hand-gepflegter,
statischer Shell (Login + Firebase-Auth + einmaliges getDoc), der dieses
dict live aus Firestore (dashboard_snapshot/latest) liest, statt es inline
gebacken zu bekommen. export() schreibt das dict nur noch (FIRESTORE_ENABLED-
gated, wie fetcher.py) nach Firestore und gibt es zurueck.

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
import os
import sqlite3
import sys
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src import db, fetcher, firestore_db, market_predictor, player_valuation
from src.kickbase_client import KickbaseError, get_manager_squad, get_me, login, status_label

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


def _parse_iso_z(raw: str | None) -> datetime.datetime | None:
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        return None


def _format_duration(hours: float) -> str:
    hours = max(hours, 0)
    if hours >= 24:
        days = int(hours // 24)
        rest_h = int(hours % 24)
        return f"{days}d {rest_h}h"
    minutes = int(round((hours % 1) * 60))
    return f"{int(hours)}h {minutes}m"


# Sentinel fuer "kein Ablauf ermittelbar" - muss eine grosse ENDLICHE Zahl
# sein (kein None/Infinity): der Sortier-Comparator im Dashboard behandelt
# null/undefined als -Infinity, wuerde "kein Zeitlimit" sonst faelschlich
# ganz nach oben sortieren, obwohl das Gegenteil von dringend ist.
# JSON.stringify(Infinity) waere ausserdem kein gueltiges JSON.
_NO_EXPIRY_SENTINEL_SECONDS = 9_999_999

NEXT_MARKET_VALUE_UPDATE_HOUR = 22
BERLIN_TZ = ZoneInfo("Europe/Berlin")


def _next_update_cutoff(now: datetime.datetime) -> datetime.datetime:
    """Naechstes Kickbase-Marktwert-Update (22 Uhr Europe/Berlin, DST-sicher
    - Sommerzeit verschiebt den UTC-Offset, ein hartcodierter Versatz waere
    im Winter falsch). Danach aendert sich der Marktwert ohnehin wieder,
    Auktionen die VOR diesem Zeitpunkt ablaufen sind fuer die aktuelle
    Kaufentscheidung am dringendsten."""
    local_now = now.astimezone(BERLIN_TZ)
    cutoff_local = local_now.replace(
        hour=NEXT_MARKET_VALUE_UPDATE_HOUR, minute=0, second=0, microsecond=0
    )
    if local_now >= cutoff_local:
        cutoff_local += datetime.timedelta(days=1)
    return cutoff_local.astimezone(datetime.timezone.utc)


def _auction_status(listed_at, expires_at, expiry_is_estimate, now: datetime.datetime) -> tuple[str, float]:
    """Kickbase liefert bei Systemangeboten IMMER ein 'exs'-Feld (Sekunden bis
    Ablauf, live bestaetigt 27.07.2026 u.a. an Stage) - fetcher._compute_expiry
    wandelt das schon in ein exaktes expires_at um (expiry_is_estimate=False).
    Nur bei Mitspieler-Angeboten (die 'exs' nie liefern) bleibt die
    mpst-Tage-Schaetzung ab 'dt' die einzige Naeherung - als 'geschaetzt'
    gekennzeichnet, damit sie nicht mit der echten Restzeit verwechselt wird.

    Gibt (label, remaining_seconds) zurueck - remaining_seconds fuers
    Sortieren nach echter Restzeit statt alphabetisch nach dem Anzeigetext."""
    if not expires_at:
        listed = _parse_iso_z(listed_at)
        if listed is None:
            return "unbekannt", _NO_EXPIRY_SENTINEL_SECONDS
        age_hours = (now - listed).total_seconds() / 3600
        return (
            f"kein Zeitlimit ermittelbar (gelistet seit {_format_duration(age_hours)})",
            _NO_EXPIRY_SENTINEL_SECONDS,
        )
    expires = _parse_iso_z(expires_at)
    if expires is None:
        return "unbekannt", _NO_EXPIRY_SENTINEL_SECONDS
    remaining_seconds = (expires - now).total_seconds()
    if remaining_seconds <= 0:
        return "Frist abgelaufen", remaining_seconds
    remaining_hours = remaining_seconds / 3600
    suffix = " (geschätzt)" if expiry_is_estimate else ""
    return f"läuft ab in {_format_duration(remaining_hours)}{suffix}", remaining_seconds


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


def _build_transfermarkt(market_listings, calibration, predictions, own_available_budget, now=None) -> list[dict]:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff_seconds = (_next_update_cutoff(now) - now).total_seconds()
    rows = []
    for r in market_listings:
        row = _player_row(r, calibration, predictions)
        is_system_offer = bool(r["is_system_offer"])
        auction_status, auction_remaining_seconds = _auction_status(
            r["listed_at"], r["expires_at"], bool(r["expiry_is_estimate"]), now
        )
        row.update(
            {
                "price": r["price"],
                "price_delta_pct": r["price_delta_pct"],
                "offering_username": r["offering_username"],
                "is_system_offer": is_system_offer,
                "pending_offers_count": r["pending_offers_count"],
                "leading_bid_username": r["leading_bid_username"],
                "leading_bid_price": r["leading_bid_price"],
                "is_own_leading_bid": bool(r["is_own_leading_bid"]),
                "affordable": (
                    own_available_budget is not None
                    and r["price"] is not None
                    and r["price"] <= own_available_budget
                ),
                "auction_status": auction_status,
                "auction_remaining_seconds": auction_remaining_seconds,
                "auction_urgent": 0 < auction_remaining_seconds < cutoff_seconds,
            }
        )
        rows.append(row)
    return rows


def _build_eigenes_team(own_squad, calibration, predictions) -> list[dict]:
    return [_player_row(r, calibration, predictions) for r in own_squad]


def _split_eigenes_team(eigenes_team_rows: list[dict], wunschkader_config: dict | None) -> dict:
    """Teilt den eigenen Kader in Verkaufskandidaten (sell_list aus
    wunschkader.json plus alle Spieler, die nicht in den Wunschkader-
    Zielen stehen) und Spieler, die im Kader bleiben sollen
    (Wunschkader-Ziele) - reine Umsortierung bestehender Zeilen, keine
    neuen Daten/Calls."""
    sell_names = set(wunschkader_config.get("sell_list", [])) if wunschkader_config else set()
    target_names = {t["name"] for t in wunschkader_config.get("targets", [])} if wunschkader_config else set()

    verkaufen, bleibt = [], []
    for row in eigenes_team_rows:
        if row["name"] in target_names:
            bleibt.append(row)
        else:
            sell_signal = "halten" if (row["name"] in sell_names and (row.get("ml_prediction") or 0) > 0) else "verkaufen"
            verkaufen.append({**row, "sell_signal": sell_signal})
    return {"verkaufen": verkaufen, "bleibt": bleibt}


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
                "auction_status": r.get("auction_status"),
                "auction_remaining_seconds": r.get("auction_remaining_seconds"),
                "auction_urgent": r.get("auction_urgent", False),
            }
        )
    rows.sort(key=lambda r: -r["roi_pct"])
    return rows


REGULAR_STARTING_RANKS = (1, 2)


def _count_regulars(starting_ranks) -> int:
    """'Stammspieler' = starting_rank 1 oder 2 (Startelf-Rang/Einsatz-
    wahrscheinlichkeit) - NICHT status_code (der bedeutet in diesem Projekt
    verletzt/angeschlagen, siehe MDs/codes.md). Per Nutzer-Nachfrage am
    27.07.2026 bestaetigt, um diese Verwechslung auszuschliessen."""
    return sum(1 for rank in starting_ranks if rank in REGULAR_STARTING_RANKS)


def _build_ligaanalyse(
    token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad, starting_rank_by_player_id
) -> list[dict]:
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
            regular_count = _count_regulars(p["starting_rank"] for p in own_squad)
        else:
            try:
                squad = get_manager_squad(token, league_id, user_id)
                items = squad.get("it", [])
                squad_size = squad.get("nps") or len(items)
                squad_value = sum((item.get("mv") or 0) for item in items)
                regular_count = _count_regulars(
                    starting_rank_by_player_id.get(item.get("pi")) for item in items
                )
            except KickbaseError as exc:
                print(f"Warnung: Kader von Manager {r['name']} nicht ladbar: {exc}", file=sys.stderr)
                squad_size, squad_value, regular_count = None, None, None

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
                "regular_count": regular_count,
            }
        )
    rows.sort(key=lambda row: (row["season_placement"] is None, row["season_placement"] or 0))
    return rows


def _load_wunschkader() -> dict | None:
    """Wunschkader lebt komplett in Firestore (wunschkader/current, siehe
    MDs/kaderplan.md fuer die Begruendungen der Eintraege) - der Browser
    kann targets direkt editieren (Alle-Spieler/Wunschkader-Feature).
    Ohne FIRESTORE_ENABLED (lokaler Testlauf) gibt es bewusst None zurueck
    (kein Wunschkader in diesem Modus). Ein echter Lesefehler wird NICHT
    abgefangen - soll export() komplett abbrechen lassen (der Firestore-
    Write des Dashboard-Snapshots passiert erst am Ende von export(), ein
    fehlgeschlagener Wunschkader-Read darf also nie zu einem kaputt
    veroeffentlichten Snapshot fuehren, lieber bleibt der alte Snapshot
    stehen)."""
    if not os.environ.get("FIRESTORE_ENABLED"):
        return None
    return firestore_db.get_wunschkader(firestore_db.connect())


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

        note = target.get("note")
        if is_own:
            status = "Eigener Kader"
        elif name in market_by_name:
            m = market_by_name[name]
            anbieter = "System" if m["is_system_offer"] else m["offering_username"]
            status = f"Markt ({anbieter}, {m['price']:,})"
            auction_status = m.get("auction_status")
            if auction_status:
                note = f"{note} - {auction_status}" if note else auction_status
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
                "note": note,
                "planned_price": planned_price,
                "is_estimate": "actual_bid" not in target and not is_own,
                "is_own": is_own,
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


def _build_alle_spieler(
    all_players: list[dict], owned_by: dict, own_squad_names: set, calibration: dict | None
) -> list[dict]:
    """Alle Liga-Spieler (~450) fuer den 'Alle Spieler'-Tab - reine
    Umformung von player_valuation.fetch_all_players(), das export() ohnehin
    schon fuer Wunschkader/Ligaanalyse laedt, keine neuen API-Calls."""
    rows = []
    for p in all_players:
        fairwert, signal = _valuation(p["market_value"], p["points_avg"], p["position"], calibration)
        if p["name"] in own_squad_names:
            owner = "Eigener Kader"
        else:
            owner = owned_by.get(p["player_id"], "Frei")
        rows.append(
            {
                "player_id": p["player_id"],
                "name": p["name"],
                "position": p["position"],
                "team_name": p["team_name"],
                "market_value": p["market_value"],
                "points_avg": p["points_avg"],
                "starting_rank": p["starting_rank"],
                "status_label": status_label(p["status_code"]),
                "owner": owner,
                "fairwert": fairwert,
                "signal": signal,
            }
        )
    return rows


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


def export() -> dict:
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

    # Ligaweite Spielerliste (u.a. starting_rank) wird sowohl fuer den
    # Wunschkader-Abgleich als auch fuer die Stammspieler-Zaehlung in
    # _build_ligaanalyse gebraucht - einmal holen, nicht doppelt.
    all_players = player_valuation.fetch_all_players(token, competition_id)
    starting_rank_by_player_id = {p["player_id"]: p["starting_rank"] for p in all_players}

    now = datetime.datetime.now(datetime.timezone.utc)
    transfermarkt_rows = _build_transfermarkt(market_listings, calibration, predictions, own_available_budget, now)

    own_name = own_budget_row["name"] if own_budget_row else None
    owned_by = (
        player_valuation.resolve_ownership(token, league_id, [dict(r) for r in ranking_rows], own_name)
        if own_name
        else {}
    )
    own_squad_names = {r["name"] for r in own_squad}

    wunschkader_config = _load_wunschkader()
    wunschkader_rows = []
    if wunschkader_config:
        # transfermarkt_rows statt roher market_listings, damit auction_status
        # (echte Auktions-Restzeit) fuer die Watchlist-Notiz verfuegbar ist.
        market_by_name = {r["name"]: r for r in transfermarkt_rows}
        wunschkader_rows = _build_wunschkader(
            wunschkader_config, all_players, owned_by, own_squad_names, market_by_name, calibration, predictions
        )
    wunschkader_watchlist = [r for r in wunschkader_rows if not r["is_own"]]

    budget_plan = (
        _build_budget_plan(
            wunschkader_config, wunschkader_rows, own_squad, own_budget_row["estimated_budget"] if own_budget_row else None, fetched_at
        )
        if wunschkader_config
        else None
    )

    eigenes_team_rows = _build_eigenes_team(own_squad, calibration, predictions)

    data = {
        "fetched_at": fetched_at,
        "own_available_budget": own_available_budget,
        "own_budget_exact": own_budget_row["estimated_budget"] if own_budget_row else None,
        "team_total_value": sum((p["market_value"] or 0) for p in own_squad),
        "calibration": calibration,
        "ml_metrics": predictions["metrics"] if predictions else None,
        "signal_thresholds": {"good": SIGNAL_GOOD, "critical": SIGNAL_CRITICAL},
        "transfermarkt": transfermarkt_rows,
        "eigenes_team_split": _split_eigenes_team(eigenes_team_rows, wunschkader_config),
        "ligaanalyse": _build_ligaanalyse(
            token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad,
            starting_rank_by_player_id,
        ),
        "wunschkader": wunschkader_rows,
        "wunschkader_watchlist": wunschkader_watchlist,
        "wunschkader_formation": wunschkader_config.get("formation") if wunschkader_config else None,
        "wunschkader_updated_at": wunschkader_config.get("updated_at") if wunschkader_config else None,
        "alle_spieler": _build_alle_spieler(all_players, owned_by, own_squad_names, calibration),
        "wunschkader_raw": wunschkader_config,
        "budget_plan": budget_plan,
        "spekulation": _build_spekulation(transfermarkt_rows),
    }

    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            fs_client = firestore_db.connect()
            firestore_db.upsert_dashboard_snapshot(fs_client, data)
        except Exception as exc:  # ein Firestore-Ausfall darf die Pipeline nie brechen
            print(f"Warnung: Firestore-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)
    return data


if __name__ == "__main__":
    try:
        data = export()
        print(f"Dashboard-Snapshot berechnet (Stand: {data['fetched_at']})")
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Dashboard-Export fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
