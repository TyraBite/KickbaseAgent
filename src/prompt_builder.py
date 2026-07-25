"""Schritt 2 (MVP): baut aus dem SQLite-Snapshot einen fertigen,
copy-paste-fertigen Analyse-Prompt fuer das Claude-WebUI. Kein API-Call."""

import sqlite3

from src import db


def _latest_fetched_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(fetched_at) FROM own_squad").fetchone()
    return row[0] if row else None


def _status_hint(status_label: str | None) -> str:
    return f" [{status_label}]" if status_label else ""


def _player_line(p: sqlite3.Row) -> str:
    return (
        f"- {p['name']} ({p['position']}){_status_hint(p['status_label'])} | "
        f"Marktwert: {p['market_value']} (Trend: {p['market_value_trend']}) | "
        f"Punkteschnitt: {p['average_points']} | Punkte gesamt: {p['total_points']}"
    )


def _market_line(p: sqlite3.Row) -> str:
    if p["is_system_offer"]:
        anbieter = "Kickbase (kein Anbieter-User erkannt, evtl. Systemangebot)"
    else:
        anbieter = p["offering_username"] or f"Manager {p['offering_user_id']}"
    extra = f" | Laufende Gebote: {p['pending_offers_count']}" if p["pending_offers_count"] else ""
    return (
        f"- {p['name']} ({p['position']}){_status_hint(p['status_label'])} | Preis: {p['price']} | "
        f"Marktwert: {p['market_value']} | Punkteschnitt: {p['average_points']} | "
        f"Angeboten von: {anbieter}{extra}"
    )


def _league_table(conn: sqlite3.Connection, fetched_at: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT user_id, name, season_points, season_placement, team_value,
               matchday_points, recent_points
        FROM league_ranking
        WHERE fetched_at = ?
        ORDER BY season_placement ASC
        """,
        (fetched_at,),
    ).fetchall()

    lines = []
    for r in rows:
        name = r["name"] or r["user_id"]
        lines.append(
            f"{r['season_placement']}. {name} - Punkte: {r['season_points']} | "
            f"Teamwert: {r['team_value']} | Spieltagspunkte: {r['matchday_points']} | "
            f"Letzte Spieltage: {r['recent_points']}"
        )
    return lines or ["(keine Liga-Tabellendaten vorhanden)"]


def build_prompt(fetched_at: str | None = None) -> str:
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    try:
        if fetched_at is None:
            fetched_at = _latest_fetched_at(conn)
        if fetched_at is None:
            raise RuntimeError("Kein Snapshot in der Datenbank - erst den Fetcher laufen lassen")

        own_squad = conn.execute(
            "SELECT * FROM own_squad WHERE fetched_at = ? ORDER BY position, name",
            (fetched_at,),
        ).fetchall()
        market_listings = conn.execute(
            "SELECT * FROM market_listings WHERE fetched_at = ? ORDER BY position, name",
            (fetched_at,),
        ).fetchall()
        own_budget_row = conn.execute(
            "SELECT * FROM own_budget_history WHERE fetched_at = ?",
            (fetched_at,),
        ).fetchone()
        own_ranking_row = None
        if own_budget_row and own_budget_row["user_id"]:
            own_ranking_row = conn.execute(
                "SELECT * FROM league_ranking WHERE fetched_at = ? AND user_id = ?",
                (fetched_at, own_budget_row["user_id"]),
            ).fetchone()
        league_table_lines = _league_table(conn, fetched_at)
    finally:
        conn.close()

    squad_lines = "\n".join(_player_line(p) for p in own_squad) or "(keine Spieler im Kader gefunden)"
    market_lines = "\n".join(_market_line(p) for p in market_listings) or "(kein Spieler aktuell auf dem Markt)"
    table_lines = "\n".join(league_table_lines)

    if own_budget_row:
        status_parts = [f"Budget: {own_budget_row['budget']}"]
        if own_ranking_row:
            status_parts.append(f"Teamwert: {own_ranking_row['team_value']}")
            status_parts.append(f"Platzierung: {own_ranking_row['season_placement']}")
            status_parts.append(f"Punkte gesamt: {own_ranking_row['season_points']}")
        status_block = "\n".join(status_parts)
    else:
        status_block = "(keine eigenen Statusdaten gefunden)"

    return f"""Du bist mein Kickbase-Berater. Hier sind meine aktuellen Daten vom {fetched_at}. \
Analysiere sie und gib mir:

1. Eine Aufstellungsempfehlung fuer den naechsten Spieltag (Formation, wer spielt, \
wer pausiert - beruecksichtige auffaellige Status-Codes, siehe Kader unten).
2. Fuer JEDEN einzelnen Spieler in meinem Kader unten: Verkaufen oder Halten, \
mit einer kurzen Begruendung (1-2 Saetze).
3. Fuer JEDEN einzelnen Spieler auf dem Transfermarkt unten: Kaufen oder Nicht kaufen, \
mit einer kurzen Begruendung. Beruecksichtige dabei explizit, ob der Spieler von einem \
Mitspieler (dann ggf. Verhandlungsspielraum) oder von Kickbase selbst (Systemangebot, \
Festpreis) angeboten wird.
4. Eine Einschaetzung meiner Position in der Liga im Vergleich zu den anderen Managern \
(wer ist gefaehrlich, worauf sollte ich achten).

Bitte gehe wirklich JEDEN Spieler aus beiden Listen einzeln durch, ueberspringe keinen.

Hinweis zu "Status-Code X" bei einzelnen Spielern: die genaue Bedeutung jenseits von \
"kein Code = unauffaellig" ist mir nicht zweifelsfrei bekannt (haeufig verletzt/gesperrt/ \
nicht nominiert) - wenn relevant, weise in deiner Antwort darauf hin, dass ich das im \
Kickbase-Client selbst gegenchecken sollte.

=== MEIN STATUS ===
{status_block}

=== MEIN KADER ({len(own_squad)} Spieler) ===
{squad_lines}

=== TRANSFERMARKT ({len(market_listings)} Spieler) ===
{market_lines}

=== LIGA-TABELLE ===
{table_lines}
"""


if __name__ == "__main__":
    print(build_prompt())
