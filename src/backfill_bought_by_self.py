"""Einmaliges Backfill-Skript (nach Lauf wieder loeschen, analog
migrate_wunschkader_player_ids.py): setzt das bought_by_self-Feld
nachtraeglich auf allen bid_premium_log-Eintraegen, die VOR dem
Gebotstracking-Feature (Commit 6de5aa2) geschrieben wurden und das Feld
deshalb komplett nicht haben. _build_outcome_counts() behandelt ein
fehlendes Feld als False (Fremd-Kauf) - macht dadurch ALLE alten Kaeufe
faelschlich zu Fremd-Kaeufen, egal wer sie tatsaechlich getaetigt hat.

Zieht den Activity-Feed noch einmal frisch (kein neuer Kickbase-Endpunkt,
derselbe Call wie in export()), matcht per activity_id (== Firestore-Doc-Id)
gegen 'byr' (Kaeufer-NAME, siehe manager_budgets.py-Docstring - nicht
User-Id trotz abweichendem Kommentar in kickbase_client.py), schreibt das
Feld gezielt per Firestore .update() nach (kein Full-Rewrite der Docs)."""

import os
import sys

from dotenv import load_dotenv

from src import dashboard_export, fetcher, firestore_db
from src.kickbase_client import get_activities_feed, login

TRADE_ACTIVITY_TYPE = 15


def backfill(
    client, token: str, league_id: str, own_name: str | None, get_activities=get_activities_feed
) -> int:
    activities = get_activities(token, league_id)
    byr_by_activity_id = {
        a["i"]: a.get("data", {}).get("byr")
        for a in activities
        if a.get("t") == TRADE_ACTIVITY_TYPE
    }

    entries = firestore_db.get_bid_premium_history(client)
    missing = [e for e in entries if "bought_by_self" not in e]
    print(f"{len(missing)} von {len(entries)} Eintraegen ohne bought_by_self-Feld gefunden.")

    updated = 0
    for entry in missing:
        activity_id = entry.get("activity_id")
        if activity_id not in byr_by_activity_id:
            print(
                f"Warnung: activity_id {activity_id!r} (Spieler {entry.get('player_id')!r}) "
                "nicht mehr im Activity-Feed, uebersprungen",
                file=sys.stderr,
            )
            continue
        bought_by_self = bool(own_name) and byr_by_activity_id[activity_id] == own_name
        client.collection("bid_premium_log").document(activity_id).update(
            {"bought_by_self": bought_by_self}
        )
        updated += 1

    print(f"{updated}/{len(missing)} Eintraege aktualisiert.")
    return updated


if __name__ == "__main__":
    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)")

    fetched_at = fetcher.run()
    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]

    _own_squad, _market_listings, _ranking_rows, manager_budget_rows = dashboard_export._load_snapshot(
        fetched_at
    )
    own_budget_row = next((b for b in manager_budget_rows if b["is_own_exact"]), None)
    own_name = own_budget_row["name"] if own_budget_row else None
    if not own_name:
        raise RuntimeError("own_name konnte nicht aufgeloest werden (own_budget_row fehlt)")

    client = firestore_db.connect()
    backfill(client, token, league_id, own_name)
