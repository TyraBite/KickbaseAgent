"""Schritt 1: Kickbase-Daten abrufen und als Tages-Snapshot in SQLite ablegen."""

import datetime
import os
import sys

from dotenv import load_dotenv

from src import db
from src.kickbase_client import fetch_all


def run() -> str:
    """Fuehrt einen kompletten Fetch-Lauf aus, gibt das Snapshot-Datum zurueck."""
    load_dotenv()

    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)"
        )

    data = fetch_all(email, password)
    fetched_at = datetime.date.today().isoformat()

    conn = db.connect()
    try:
        db.upsert_league_users(conn, data.league_users)
        db.replace_own_squad(conn, fetched_at, data.own_squad)
        db.replace_market_listings(conn, fetched_at, data.market_listings)
        db.upsert_matchday_stats(conn, data.matchday_stats)
        db.upsert_own_status(conn, {**data.own_status, "fetched_at": fetched_at})
    finally:
        conn.close()

    print(
        f"Snapshot {fetched_at}: {len(data.own_squad)} eigene Spieler, "
        f"{len(data.market_listings)} Marktangebote, {len(data.league_users)} Liga-Manager"
    )
    return fetched_at


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Fetcher fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
