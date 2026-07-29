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

Seit der Cadence-Aufspaltung (Heavy/Light, 2026-07-29) steuert die
Umgebungsvariable DASHBOARD_MODE den Umfang dieses Laufs: fehlt sie (oder ist
!= 'light', z.B. workflow_dispatch/dashboard-marktwerte.yml), laeuft export()
den vollen Marktwert-Pfad (fetch_all_players + predict_market_value_changes,
~12x teurer an Kickbase-API-Calls/ML-Training). 'light' (dashboard.yml, alle
2h) uebernimmt die marktwert-abgeleiteten Teile stattdessen aus dem letzten
Firestore-Snapshot (dashboard_snapshot/latest) - Kader/Markt/Liga bleiben
trotzdem taggenau frisch. Ohne vorherigen Snapshot (Cold Start) faellt
'light' automatisch auf den vollen Pfad zurueck, siehe _resolve_is_light/
_resolve_heavy_data.

Seit der players-Map-Migration (2026-07-29) liefert export() eine einzige
`players`-Map (player_id -> rohe Felder + ml_prediction, siehe
_build_players_map) statt der fruehen parallelen Arrays (transfermarkt/
eigenes_team_split/alle_spieler/spekulation - alle entfernt, ebenso die
14 Python-Ableitungsfunktionen dahinter). Fairwert/Signal/Trend/
Auktionsstatus/Hype-Gipfel/Budget-Plan werden nicht mehr hier berechnet,
sondern clientseitig aus den rohen Feldern abgeleitet (siehe
frontend/src/lib/derive.ts) - dieses Modul liefert nur noch Rohdaten.

`python -m src.dashboard_export`
"""

from __future__ import annotations

import os
import sqlite3
import sys

from dotenv import load_dotenv

from src import db, fetcher, firestore_db, market_predictor, player_valuation
from src.kickbase_client import KickbaseError, get_manager_squad, get_me, login

# Toleranzband aus MDs/methodik.md, Abschnitt "Fairwert und Signal".
SIGNAL_GOOD = 1.25
SIGNAL_CRITICAL = 0.80


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


def _build_wunschkader_targets(wunschkader: dict, players_map: dict) -> list[dict]:
    """Wunschkader-Ziele sind jetzt eine reine player_id-Referenzliste
    (Firestore wunschkader/current speichert player_id direkt seit der
    einmaligen Migration, siehe migrate_wunschkader_player_ids.py) - keine
    Namens-Aufloesung, keine Praesentations-Felder mehr (team_name/
    market_value/status/planned_price loest der Client selbst ueber
    players[player_id] auf). Nur eine Sanity-Warnung falls ein player_id
    (noch) nicht in players_map auftaucht - das Ziel bleibt trotzdem in der
    Liste (kein stiller Datenverlust bei einem einzelnen kaputten Eintrag,
    gleiche Philosophie wie _load_wunschkader())."""
    targets = wunschkader.get("targets", [])
    for t in targets:
        pid = t.get("player_id")
        if not pid or pid not in players_map:
            print(
                f"Warnung: Wunschkader-Ziel mit player_id={pid!r} nicht in players_map gefunden "
                "- siehe migrate_wunschkader_player_ids.py",
                file=sys.stderr,
            )
    return [
        {
            "player_id": t.get("player_id"),
            "role": t.get("role"),
            "note": t.get("note"),
            "actual_bid": t.get("actual_bid"),
        }
        for t in targets
    ]


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


def _resolve_is_light(mode: str | None, cached_snapshot: dict | None) -> bool:
    """Ein einziger Entscheidungspunkt fuer DASHBOARD_MODE=light vs. voller
    Lauf. Cold Start umfasst jetzt ZWEI Faelle: kein Snapshot gefunden ODER
    ein Snapshot im ALTEN Schema (vor der players-Map-Migration, erkennbar
    am fehlenden "players"-Key) - beide fuehren zum automatischen
    Selbstheilungs-Fallback auf den vollen Lauf."""
    is_cold_start = cached_snapshot is None or "players" not in cached_snapshot
    if mode == "light" and is_cold_start:
        print(
            "Warnung: DASHBOARD_MODE=light, aber kein verwertbarer Firestore-Snapshot "
            "gefunden (Cold Start oder alter Schema-Stand vor der players-Map-Migration) - "
            "falle automatisch auf den vollen Marktwert-Lauf zurueck.",
            file=sys.stderr,
        )
    return mode == "light" and not is_cold_start


def _resolve_heavy_data(
    is_light: bool,
    cached_snapshot: dict | None,
    token: str,
    league_id: str,
    competition_id: str,
    ranking_rows,
    own_name: str | None,
) -> dict:
    """Zentrale Weiche fuer alle marktwert-abgeleiteten export()-Eingaben.
    Light: liefert alles aus dem letzten Snapshot (inkl. owned_by, das
    frueher auf {} zurueckgesetzt wurde), predictions bleibt None statt
    eines synthetischen Dicts - _build_players_map() braucht das nicht
    mehr, da ml_prediction jetzt Teil der uebernommenen players-Map ist."""
    if is_light:
        return {
            "all_players": None,
            "predictions": None,
            "calibration": cached_snapshot["calibration"],
            "owned_by": cached_snapshot.get("owned_by", {}),
            "ml_metrics": cached_snapshot["ml_metrics"],
            "ml_accuracy_trend": cached_snapshot["ml_accuracy_trend"],
        }

    all_players = player_valuation.fetch_all_players(token, competition_id)
    predictions = market_predictor.predict_market_value_changes()
    owned_by = (
        player_valuation.resolve_ownership(token, league_id, [dict(r) for r in ranking_rows], own_name)
        if own_name
        else {}
    )
    return {
        "all_players": all_players,
        "predictions": predictions,
        "calibration": player_valuation.load_calibration(),
        "owned_by": owned_by,
        "ml_metrics": predictions["metrics"] if predictions else None,
        "ml_accuracy_trend": predictions["metrics"].get("accuracy_trend") if predictions else None,
    }


def _build_players_map(
    all_players: list[dict] | None,
    own_squad,
    market_listings,
    predictions: dict | None,
    previous_players: dict[str, dict] | None,
    is_light: bool,
) -> dict[str, dict]:
    """Baut/aktualisiert die players-Map (player_id -> rohe Felder +
    ml_prediction). Heavy: kompletter Rebuild aus den ~450 all_players-
    Zeilen (team_id wird NICHT uebernommen - niemand client-seitig braucht
    ihn). Light: startet als Kopie der VORHERIGEN Map - die anderen ~380
    Spieler bleiben dadurch unveraendert, kein Re-Fetch.

    In BEIDEN Modi werden anschliessend own_squad+market_listings (immer
    taggenau frisch, siehe fetcher.run()) auf die Basis ueberlagert - das
    ist das EINZIGE, was in einem Light-Lauf tatsaechlich veraendert wird.
    History-Felder werden nur uebernommen wenn die Zeile sie tatsaechlich
    hat (Feld bleibt UNGESETZT statt explizit null - sonst wuerden fuer
    ~380 Spieler pro Light-Lauf vorhandene Werte verloren gehen, obwohl sie
    gar nicht angefasst wurden).

    ml_prediction wird nur fuer player_ids in predictions['predictions']
    gesetzt/ueberschrieben - alle anderen behalten den Wert aus `base`
    (Light: der letzte bekannte Stand; Heavy: keiner, da `base` dort frisch
    aufgebaut wird)."""
    if is_light:
        base: dict[str, dict] = {pid: dict(p) for pid, p in (previous_players or {}).items()}
    else:
        base = {
            p["player_id"]: {
                "player_id": p["player_id"],
                "name": p["name"],
                "position": p["position"],
                "team_name": p["team_name"],
                "status_code": p["status_code"],
                "starting_rank": p["starting_rank"],
                "market_value": p["market_value"],
                "average_points": p["average_points"],
            }
            for p in (all_players or [])
            if p.get("player_id")
        }

    HISTORY_FIELDS = (
        "market_value_change_7d", "market_value_low_92d",
        "market_value_high_92d", "market_value_in_drop_phase",
    )
    for row in list(own_squad) + list(market_listings):
        pid = row["player_id"]
        entry = dict(base.get(pid) or {"player_id": pid})
        entry.update({
            "name": row["name"],
            "position": row["position"],
            "team_name": row["team_name"],
            "status_code": row["status_code"],
            "starting_rank": row["starting_rank"],
            "market_value": row["market_value"],
            "average_points": row["average_points"],
            "total_points": row["total_points"],
        })
        for field in HISTORY_FIELDS:
            value = row[field]
            if value is not None:
                entry[field] = value
        base[pid] = entry

    predictions_by_id = (predictions or {}).get("predictions", {})
    for pid, value in predictions_by_id.items():
        if pid in base:
            base[pid]["ml_prediction"] = value

    return base


def _build_transfermarkt_listings(market_listings) -> list[dict]:
    """Reine Markt-Rohfelder je Listing - kein Merge mit Spieler-Stammdaten
    mehr (die kommen aus der players-Map), kein auction_status/affordable
    (clientseitig aus listed_at/expires_at/expiry_is_estimate + price +
    eigenem Budget berechnet, siehe frontend/src/lib/derive.ts)."""
    return [
        {
            "player_id": r["player_id"],
            "price": r["price"],
            "price_delta_pct": r["price_delta_pct"],
            "offering_username": r["offering_username"],
            "is_system_offer": bool(r["is_system_offer"]),
            "pending_offers_count": r["pending_offers_count"],
            "leading_bid_username": r["leading_bid_username"],
            "leading_bid_price": r["leading_bid_price"],
            "is_own_leading_bid": bool(r["is_own_leading_bid"]),
            "listed_at": r["listed_at"],
            "expires_at": r["expires_at"],
            "expiry_is_estimate": bool(r["expiry_is_estimate"]),
        }
        for r in market_listings
    ]


def export() -> dict:
    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)")

    mode = os.environ.get("DASHBOARD_MODE")
    cached_snapshot = None
    if mode == "light" and os.environ.get("FIRESTORE_ENABLED"):
        cached_snapshot = firestore_db.get_dashboard_snapshot(firestore_db.connect())
    is_light = _resolve_is_light(mode, cached_snapshot)

    fetched_at = fetcher.run()

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    competition_id = get_me(token, league_id).get("cpi") or "1"

    own_squad, market_listings, ranking_rows, manager_budget_rows = _load_snapshot(fetched_at)

    own_budget_row = next((b for b in manager_budget_rows if b["is_own_exact"]), None)
    own_available_budget = own_budget_row["available_budget"] if own_budget_row else None
    own_name = own_budget_row["name"] if own_budget_row else None

    heavy = _resolve_heavy_data(is_light, cached_snapshot, token, league_id, competition_id, ranking_rows, own_name)

    previous_players = cached_snapshot.get("players", {}) if is_light else None
    players_map = _build_players_map(
        all_players=heavy["all_players"],
        own_squad=own_squad,
        market_listings=market_listings,
        predictions=heavy["predictions"],
        previous_players=previous_players,
        is_light=is_light,
    )

    wunschkader_config = _load_wunschkader()
    wunschkader_targets = (
        _build_wunschkader_targets(wunschkader_config, players_map) if wunschkader_config else []
    )

    data = {
        "fetched_at": fetched_at,
        "own_available_budget": own_available_budget,
        "own_budget_exact": own_budget_row["estimated_budget"] if own_budget_row else None,
        "team_total_value": sum((p["market_value"] or 0) for p in own_squad),
        "calibration": heavy["calibration"],
        "ml_metrics": heavy["ml_metrics"],
        "ml_accuracy_trend": heavy["ml_accuracy_trend"],
        "signal_thresholds": {"good": SIGNAL_GOOD, "critical": SIGNAL_CRITICAL},
        "players": players_map,
        "transfermarkt_listings": _build_transfermarkt_listings(market_listings),
        "own_squad_ids": [r["player_id"] for r in own_squad],
        "owned_by": heavy["owned_by"],
        "wunschkader_targets": wunschkader_targets,
        "wunschkader_formation": wunschkader_config.get("formation") if wunschkader_config else None,
        "wunschkader_sell_list": wunschkader_config.get("sell_list") if wunschkader_config else None,
        "wunschkader_updated_at": wunschkader_config.get("updated_at") if wunschkader_config else None,
        "ligaanalyse": _build_ligaanalyse(
            token, league_id, ranking_rows, manager_budget_rows, market_listings, own_squad,
            {pid: p["starting_rank"] for pid, p in players_map.items()},
        ),
    }

    _finalize_firestore_write(data)
    return data


def _finalize_firestore_write(data: dict) -> None:
    """Schreibt den fertigen Snapshot nach Firestore (dashboard_snapshot/latest,
    von index.html UND frontend/ live gelesen) und macht jeden Firestore-Ausfall
    sichtbar: genau wie bei _load_wunschkader() oben (siehe Docstring dort)
    darf ein Firestore-Ausfall bei diesem seiten-relevanten Write dashboard.yml
    nicht gruen durchlaufen lassen - sonst bleibt die Live-Seite unbemerkt auf
    altem Stand. (fetcher.run() spricht seit der Entfernung der toten Phase-1-
    Rohdaten-Collections gar nicht mehr mit Firestore - dieser Write hier ist
    der einzig verbleibende, seiten-relevante.)"""
    firestore_write_failed = False
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            fs_client = firestore_db.connect()
            firestore_db.upsert_dashboard_snapshot(fs_client, data)
        except Exception as exc:
            print(f"Warnung: Firestore-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)
            firestore_write_failed = True
    if firestore_write_failed:
        raise firestore_db.FirestoreWriteError(
            data["fetched_at"],
            "Firestore-Schreibzugriff fuer seiten-relevante Daten fehlgeschlagen (siehe Warnung oben)",
        )


if __name__ == "__main__":
    try:
        data = export()
        print(f"Dashboard-Snapshot berechnet (Stand: {data['fetched_at']})")
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Dashboard-Export fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
