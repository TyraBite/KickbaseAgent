"""Einmalige Migration: fuegt player_id zu den bestehenden Wunschkader-
targets/sell_list-Eintraegen hinzu (bisher nur per Name referenziert).
Kein Dauerbetrieb-Code, kein Dual-Path-Fallback - einmal per Hand
ausfuehren (`python -m src.migrate_wunschkader_player_ids`), danach kann
diese Datei wieder geloescht werden (Repo-Konvention: keine Backwards-
Compat-Shims fuer diesen kleinen, persoenlichen Datensatz).

Voraussetzung: dashboard_snapshot/latest muss bereits im NEUEN Schema
vorliegen (players-Map vorhanden) - sonst zuerst einen Heavy-Lauf von
dashboard_export.export() (oder workflow_dispatch von dashboard-
marktwerte.yml) durchfuehren."""
import sys

from src import firestore_db


def _resolve_player_id(name: str, players: dict[str, dict]) -> str | None:
    matches = [pid for pid, p in players.items() if p.get("name") == name]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Warnung: '{name}' mehrfach gefunden ({matches}) - manuell aufloesen", file=sys.stderr)
    else:
        print(f"Warnung: '{name}' nicht gefunden - manuell aufloesen", file=sys.stderr)
    return None


def migrate() -> None:
    client = firestore_db.connect()
    snapshot = firestore_db.get_dashboard_snapshot(client)
    if not snapshot or "players" not in snapshot:
        raise RuntimeError("dashboard_snapshot/latest hat noch keine players-Map - zuerst Heavy-Lauf durchfuehren")
    players = snapshot["players"]

    wunschkader = firestore_db.get_wunschkader(client)
    if not wunschkader:
        print("Kein wunschkader/current-Dokument gefunden - nichts zu migrieren")
        return

    changed = False
    for target in wunschkader.get("targets", []):
        if "player_id" in target:
            continue
        pid = _resolve_player_id(target["name"], players)
        if pid:
            target["player_id"] = pid
            changed = True

    new_sell_list = []
    for entry in wunschkader.get("sell_list", []):
        if entry in players:  # schon eine player_id
            new_sell_list.append(entry)
            continue
        pid = _resolve_player_id(entry, players)
        new_sell_list.append(pid or entry)
        changed = changed or bool(pid)
    wunschkader["sell_list"] = new_sell_list

    if not changed:
        print("Keine Aenderungen noetig")
        return

    firestore_db.upsert_wunschkader(client, wunschkader)
    unresolved = [t.get("name") for t in wunschkader.get("targets", []) if "player_id" not in t]
    print(f"Migration geschrieben. Weiterhin ungeloest: {unresolved}")


if __name__ == "__main__":
    migrate()
