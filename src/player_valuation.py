"""Fairwert/K-Punkt-Kalibrierung: marktweite Referenzpreis-Schaetzung.

Portiert eine in einer separaten (API-losen) Claude-Session entwickelte
Bewertungsformel (siehe KickbaseAgent/MDs/methodik.md, Abschnitt "Kosten pro
Punkt") von einem 68-Spieler-Dump (eigener Kader + eigener, negativ
selektierter Markt) auf alle ~450 Bundesliga-Spieler:

    Referenzmenge = Spieler mit Punkteschnitt > 70, Einsatzquote > 85 %,
                     Marktwert > 500.000, Punkteschnitt vorhanden
    K             = Median(Marktwert / Punkteschnitt) ueber die Referenzmenge
    Signal        = K / (Marktwert_Kandidat / Punkteschnitt_Kandidat)
    Fairwert      = Punkteschnitt_Kandidat * K   (= Preisobergrenze)

Reines Recherche-/Kalibrierungswerkzeug fuer den MD-Workflow in
KickbaseAgent/MDs, NICHT Teil der taeglichen main.py-Pipeline - eigenstaendig
lauffaehig: `python -m src.player_valuation`.

Marktwert ("mv") und Punkteschnitt ("ap") kommen direkt aus
kickbase_client.get_team_squad() (teamprofile, 18 Calls). Die Einsatzquote
braucht dagegen echte Einsatzzahlen aus get_player_performance() (~450
Calls) - das ersetzt bewusst die in MDs/datencheck.md Punkt 2 als fehlerhaft
dokumentierte Naeherungsformel (Punkte gesamt / Punkteschnitt, bis zu 29 %
daneben), indem echte Einsaetze der letzten abgeschlossenen Saison gezaehlt
werden statt sie aus Gesamt-/Schnittpunkten zurueckzurechnen.
"""

from __future__ import annotations

import concurrent.futures
import os
import statistics
import sys

from src.kickbase_client import (
    KickbaseError,
    get_player_performance,
    get_team_squad,
    get_teams,
    position_label,
)

MIN_POINTS_AVG = 70
MIN_APPEARANCE_RATE = 0.85
MIN_MARKET_VALUE = 500_000
MIN_POSITION_SAMPLE = 4
MATCHDAYS_PER_SEASON = 34

# Aus MDs/methodik.md, kalibriert an 3 Datenpunkten aus einem stark
# verzerrten 68-Spieler-Dump (2026-07-25) - Referenz fuer den Konsistenz-Check
# gegen den vollen Live-Datensatz.
KNOWN_ANCHORS = {
    "Baumann": {"points_avg": 99, "k_per_point": 193_000},
    "Raum": {"points_avg": 148, "k_per_point": 211_000},
    "Leweling": {"points_avg": 103, "k_per_point": 252_000},
}


def _max_workers() -> int:
    return int(os.environ.get("PLAYER_VALUATION_MAX_WORKERS", 8))


def _fetch_all_players(token: str, competition_id: str) -> list[dict]:
    """Alle Liga-Spieler mit Marktwert/Punkteschnitt/Position, ueber alle
    Vereine der Competition (18 Calls, kein Threading noetig)."""
    rows = []
    for team_id in get_teams(token, competition_id):
        try:
            items = get_team_squad(token, competition_id, team_id)
        except KickbaseError as exc:
            print(f"Warnung: Kader von Team {team_id} nicht ladbar: {exc}", file=sys.stderr)
            continue
        for item in items:
            player_id = item.get("i")
            if not player_id:
                continue
            rows.append(
                {
                    "player_id": player_id,
                    "name": item.get("n"),
                    "position": position_label(item.get("pos")),
                    "team_id": team_id,
                    "market_value": item.get("mv"),
                    "points_avg": item.get("ap"),
                }
            )
    return rows


def _current_season_appearances(performance_data: dict) -> int | None:
    """Die 2026/27-Saison steht als eigene, noch leere Season-Gruppe am Ende
    von 'it' (bestaetigt: zukuenftige Spieltage ohne 'p', siehe
    market_predictor.py-Recherche). Rueckwaerts iterieren und die erste
    Gruppe mit mindestens einem gespielten Spiel nehmen = letzte
    tatsaechlich abgeschlossene Saison."""
    for season in reversed(performance_data.get("it", [])):
        played = [m for m in season.get("ph", []) if m.get("p") is not None]
        if played:
            return len(played)
    return None


def _fetch_player_appearances(token: str, competition_id: str, player_id: str) -> int | None:
    try:
        data = get_player_performance(token, competition_id, player_id)
    except KickbaseError as exc:
        print(f"Warnung: Performance fuer Spieler {player_id} nicht ladbar: {exc}", file=sys.stderr)
        return None
    return _current_season_appearances(data)


def _build_dataset(token: str, competition_id: str) -> list[dict]:
    rows = _fetch_all_players(token, competition_id)

    with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers()) as executor:
        futures = {
            executor.submit(_fetch_player_appearances, token, competition_id, row["player_id"]): row
            for row in rows
        }
        for future in concurrent.futures.as_completed(futures):
            row = futures[future]
            appearances = future.result()
            row["appearances"] = appearances
            row["appearance_rate"] = (
                appearances / MATCHDAYS_PER_SEASON if appearances is not None else None
            )

    return rows


def k_per_point(row: dict) -> float | None:
    if not row.get("points_avg") or row.get("market_value") is None:
        return None
    return row["market_value"] / row["points_avg"]


def signal(row: dict, k: float) -> float | None:
    """Signal = K / (Marktwert_Kandidat / Punkteschnitt_Kandidat). >1 heisst
    unter Referenzpreis, <1 heisst Praemie."""
    kp = k_per_point(row)
    if not kp:
        return None
    return k / kp


def fairwert(row: dict, k: float) -> float | None:
    """Fairwert = Punkteschnitt * K, zugleich die Preisobergrenze."""
    if not row.get("points_avg"):
        return None
    return row["points_avg"] * k


def build_reference_set(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row.get("points_avg")
        and row["points_avg"] > MIN_POINTS_AVG
        and row.get("market_value")
        and row["market_value"] > MIN_MARKET_VALUE
        and row.get("appearance_rate") is not None
        and row["appearance_rate"] > MIN_APPEARANCE_RATE
    ]


def calibrate(reference_set: list[dict]) -> dict:
    """Globales K (Median ueber die ganze Referenzmenge) plus Positions-K,
    letzteres nur wenn eine Position mindestens MIN_POSITION_SAMPLE Spieler
    in der Referenzmenge hat - sonst instabiler Median aus zu wenigen
    Punkten, siehe Spezifikation in MDs/methodik.md."""
    global_values = [v for v in (k_per_point(r) for r in reference_set) if v is not None]
    global_k = statistics.median(global_values) if global_values else None

    by_position: dict[str, list[dict]] = {}
    for row in reference_set:
        by_position.setdefault(row["position"], []).append(row)

    position_k = {}
    for pos, group in by_position.items():
        values = [v for v in (k_per_point(r) for r in group) if v is not None]
        position_k[pos] = {
            "k": statistics.median(values) if len(group) >= MIN_POSITION_SAMPLE else None,
            "n": len(group),
        }

    return {"global_k": global_k, "n": len(reference_set), "position_k": position_k}


def _find_anchor(rows: list[dict], name: str) -> dict | None:
    matches = [r for r in rows if r.get("name") == name]
    if len(matches) > 1:
        teams = ", ".join(str(m["team_id"]) for m in matches)
        print(f"Warnung: '{name}' mehrfach im Dataset (Teams {teams}) - nicht eindeutig", file=sys.stderr)
        return None
    return matches[0] if matches else None


def _print_report(rows: list[dict], calibration: dict) -> None:
    print(f"Gescannte Spieler: {len(rows)}")
    print(
        f"Referenzmenge (Schnitt>{MIN_POINTS_AVG}, Quote>{MIN_APPEARANCE_RATE:.0%}, "
        f"Marktwert>{MIN_MARKET_VALUE}): {calibration['n']}"
    )
    if calibration["n"] < 10:
        print(
            f"WARNUNG: Referenzmenge sehr klein ({calibration['n']}) - Median instabil. "
            "Erwaege, MIN_APPEARANCE_RATE auf 0.75 zu senken."
        )

    if calibration["global_k"]:
        print(f"\nGlobales K (Median Marktwert/Punkteschnitt): {calibration['global_k']:.0f}")
    else:
        print("\nGlobales K: nicht berechenbar (Referenzmenge leer)")

    print("\nPositions-K:")
    for pos, info in sorted(calibration["position_k"].items()):
        if info["k"] is not None:
            print(f"  {pos}: {info['k']:.0f} (n={info['n']})")
        else:
            print(
                f"  {pos}: zu wenig Datenpunkte (n={info['n']}, Minimum {MIN_POSITION_SAMPLE}) "
                "- globales K verwenden"
            )

    print("\nVergleich gegen bekannte Anker aus MDs/methodik.md:")
    for name, anchor in KNOWN_ANCHORS.items():
        row = _find_anchor(rows, name)
        if row is None:
            print(f"  {name}: nicht eindeutig im Dataset gefunden")
            continue
        computed_kp = k_per_point(row)
        if computed_kp is None:
            print(f"  {name}: k/Punkt live nicht berechenbar (Punkteschnitt={row.get('points_avg')})")
            continue
        print(
            f"  {name}: Punkteschnitt live={row['points_avg']} (methodik.md: {anchor['points_avg']}), "
            f"Marktwert live={row['market_value']}, "
            f"k/Punkt live={computed_kp:.0f} vs. methodik.md={anchor['k_per_point']}"
        )


if __name__ == "__main__":
    from dotenv import load_dotenv

    from src.kickbase_client import get_me, login

    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        print("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (.env)", file=sys.stderr)
        sys.exit(1)

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    me = get_me(token, league_id)
    competition_id = me.get("cpi") or "1"

    dataset = _build_dataset(token, competition_id)
    reference_set = build_reference_set(dataset)
    calibration = calibrate(reference_set)
    _print_report(dataset, calibration)
