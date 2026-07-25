"""Schritt 1: Kickbase-Daten abrufen und als Tages-Snapshot in SQLite ablegen."""

import datetime
import os
import sys

from dotenv import load_dotenv

from src import db
from src.kickbase_client import (
    get_market,
    get_me,
    get_ranking,
    get_squad,
    login,
    position_label,
    status_label,
)


def _select_league(leagues: list[dict]) -> dict:
    league_id_override = os.environ.get("KICKBASE_LEAGUE_ID")
    if league_id_override:
        for league in leagues:
            if str(league.get("id")) == str(league_id_override):
                return league
        raise RuntimeError(
            f"KICKBASE_LEAGUE_ID={league_id_override} nicht unter den Ligen des Accounts gefunden"
        )
    if len(leagues) > 1:
        names = ", ".join(f"{l.get('name')} ({l.get('id')})" for l in leagues)
        print(
            f"Warnung: Account ist in {len(leagues)} Ligen ({names}), nehme die erste. "
            f"Setze KICKBASE_LEAGUE_ID um eine andere zu waehlen."
        )
    return leagues[0]


def _squad_item_to_row(item: dict) -> dict:
    status_code = item.get("st") or 0
    return {
        "player_id": item.get("i"),
        "name": item.get("n"),
        "position": position_label(item.get("pos")),
        "status_code": status_code,
        "status_label": status_label(status_code),
        "market_value": item.get("mv"),
        "market_value_trend": item.get("mvt"),
        "average_points": item.get("ap"),
        "total_points": item.get("p"),
        "team_id": item.get("tid"),
    }


def _market_item_to_row(item: dict, names_by_user_id: dict) -> dict:
    status_code = item.get("st") or 0
    offering_user_id = item.get("oui") or None
    offering_username = names_by_user_id.get(offering_user_id) if offering_user_id else None
    return {
        "player_id": item.get("i") or item.get("pi"),
        "name": item.get("n") or item.get("pn"),
        "position": position_label(item.get("pos")),
        "status_code": status_code,
        "status_label": status_label(status_code),
        "market_value": item.get("mv"),
        "price": item.get("prc"),
        "average_points": item.get("ap"),
        "offering_user_id": offering_user_id,
        "offering_username": offering_username,
        "is_system_offer": 1 if not offering_user_id else 0,
        "pending_offers_count": len(item.get("ofs") or []),
    }


def run() -> str:
    """Fuehrt einen kompletten Fetch-Lauf aus, gibt das Snapshot-Datum zurueck."""
    load_dotenv()

    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)"
        )

    token, user, leagues = login(email, password)
    if not leagues:
        raise RuntimeError("Account ist in keiner Liga Mitglied")
    league = _select_league(leagues)
    league_id = league["id"]

    ranking = get_ranking(token, league_id)
    ranking_users = ranking.get("us", [])
    names_by_user_id = {u.get("i"): u.get("n") for u in ranking_users if u.get("i")}

    fetched_at = datetime.date.today().isoformat()

    squad_items = get_squad(token, league_id)
    own_squad_rows = [_squad_item_to_row(item) for item in squad_items]

    market_items = get_market(token, league_id)
    market_rows = [_market_item_to_row(item, names_by_user_id) for item in market_items]

    ranking_rows = [
        {
            "user_id": u.get("i"),
            "name": u.get("n"),
            "season_points": u.get("sp"),
            "matchday_points": u.get("mdp"),
            "team_value": u.get("tv"),
            "season_placement": u.get("spl"),
            "matchday_placement": u.get("mdpl"),
            "recent_points": ",".join(str(p) for p in (u.get("lp") or [])),
        }
        for u in ranking_users
    ]

    me = get_me(token, league_id)
    budget = me.get("b")
    own_user_id = user.get("id")

    conn = db.connect()
    try:
        db.upsert_league_users(
            conn, [{"user_id": uid, "name": name} for uid, name in names_by_user_id.items()]
        )
        db.replace_own_squad(conn, fetched_at, own_squad_rows)
        db.replace_market_listings(conn, fetched_at, market_rows)
        db.replace_league_ranking(conn, fetched_at, ranking_rows)
        db.upsert_own_budget(conn, fetched_at, own_user_id, budget)
    finally:
        conn.close()

    print(
        f"Snapshot {fetched_at}: {len(own_squad_rows)} eigene Spieler, "
        f"{len(market_rows)} Marktangebote, {len(ranking_rows)} Liga-Manager"
    )
    return fetched_at


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Fetcher fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
