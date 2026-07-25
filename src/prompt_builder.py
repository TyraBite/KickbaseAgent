"""Schritt 2 (MVP): baut aus dem SQLite-Snapshot einen fertigen,
copy-paste-fertigen Analyse-Prompt fuer das Claude-WebUI. Kein API-Call."""

import sqlite3

from src import db

POSITION_LABELS = {
    "GOAL_KEEPER": "Torwart",
    "DEFENDER": "Abwehr",
    "MIDFIELDER": "Mittelfeld",
    "FORWARD": "Sturm",
    "UNKNOWN": "?",
}

STATUS_LABELS = {
    "NONE": None,  # fit, kein Hinweis noetig
    "INJURED": "verletzt",
    "STRICKEN": "angeschlagen",
    "REHAB": "im Aufbautraining",
    "RED_CARD": "gesperrt (Rote Karte)",
    "YELLOW_RED_CARD": "gesperrt (Gelb-Rot)",
    "FIFTH_YELLOW_CARD": "gesperrt (5. Gelbe)",
    "NOT_IN_TEAM": "nicht im Kader seines Vereins",
    "NOT_IN_LEAGUE": "nicht spielberechtigt",
    "ABSENT": "abwesend",
    "UNKNOWN": None,
}


def _latest_fetched_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(fetched_at) FROM own_squad").fetchone()
    return row[0] if row else None


def _status_hint(status: str) -> str:
    label = STATUS_LABELS.get(status)
    return f" [{label}]" if label else ""


def _player_line(p: sqlite3.Row) -> str:
    name = f"{p['first_name']} {p['last_name']}".strip()
    position = POSITION_LABELS.get(p["position"], p["position"])
    return (
        f"- {name} ({position}){_status_hint(p['status'])} | "
        f"Marktwert: {p['market_value']} (Trend: {p['market_value_trend']}) | "
        f"Punkteschnitt: {p['average_points']} | Punkte gesamt: {p['total_points']}"
    )


def _market_line(p: sqlite3.Row) -> str:
    name = f"{p['first_name']} {p['last_name']}".strip()
    position = POSITION_LABELS.get(p["position"], p["position"])
    if p["is_system_offer"]:
        anbieter = "Kickbase (Systemangebot)"
    else:
        anbieter = p["offering_username"] or f"Manager {p['offering_user_id']}"
    return (
        f"- {name} ({position}){_status_hint(p['status'])} | Preis: {p['price']} | "
        f"Marktwert: {p['market_value']} | Punkteschnitt: {p['average_points']} | "
        f"Angeboten von: {anbieter} | Laeuft ab in: {p['expiry']}s"
    )


def _league_table(conn: sqlite3.Connection) -> list[str]:
    latest_day_row = conn.execute("SELECT MAX(day) FROM league_matchday_stats").fetchone()
    latest_day = latest_day_row[0] if latest_day_row else None
    if latest_day is None:
        return ["(keine Liga-Tabellendaten vorhanden)"]

    rows = conn.execute(
        """
        SELECT s.user_id, u.name, s.points, s.placement, s.team_value, s.day_points
        FROM league_matchday_stats s
        LEFT JOIN league_users u ON u.user_id = s.user_id
        WHERE s.day = ?
        ORDER BY s.placement ASC
        """,
        (latest_day,),
    ).fetchall()

    lines = []
    for r in rows:
        name = r["name"] or r["user_id"]
        lines.append(
            f"{r['placement']}. {name} - Punkte: {r['points']} | "
            f"Teamwert: {r['team_value']} | Spieltagspunkte: {r['day_points']}"
        )
    return lines


def build_prompt(fetched_at: str | None = None) -> str:
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    try:
        if fetched_at is None:
            fetched_at = _latest_fetched_at(conn)
        if fetched_at is None:
            raise RuntimeError("Kein Snapshot in der Datenbank - erst den Fetcher laufen lassen")

        own_squad = conn.execute(
            "SELECT * FROM own_squad WHERE fetched_at = ? ORDER BY position, last_name",
            (fetched_at,),
        ).fetchall()
        market_listings = conn.execute(
            "SELECT * FROM market_listings WHERE fetched_at = ? ORDER BY position, last_name",
            (fetched_at,),
        ).fetchall()
        own_status = conn.execute(
            "SELECT * FROM own_status_history WHERE fetched_at = ?",
            (fetched_at,),
        ).fetchone()
        league_table_lines = _league_table(conn)
    finally:
        conn.close()

    squad_lines = "\n".join(_player_line(p) for p in own_squad) or "(keine Spieler im Kader gefunden)"
    market_lines = "\n".join(_market_line(p) for p in market_listings) or "(kein Spieler aktuell auf dem Markt)"
    table_lines = "\n".join(league_table_lines)

    status_block = (
        f"Budget: {own_status['budget']}\n"
        f"Teamwert: {own_status['team_value']}\n"
        f"Platzierung: {own_status['placement']}\n"
        f"Punkte gesamt: {own_status['points']}"
        if own_status
        else "(keine eigenen Statusdaten gefunden)"
    )

    return f"""Du bist mein Kickbase-Berater. Hier sind meine aktuellen Daten vom {fetched_at}. \
Analysiere sie und gib mir:

1. Eine Aufstellungsempfehlung fuer den naechsten Spieltag (Formation, wer spielt, \
wer pausiert - beruecksichtige verletzte/gesperrte Spieler).
2. Fuer JEDEN einzelnen Spieler in meinem Kader unten: Verkaufen oder Halten, \
mit einer kurzen Begruendung (1-2 Saetze).
3. Fuer JEDEN einzelnen Spieler auf dem Transfermarkt unten: Kaufen oder Nicht kaufen, \
mit einer kurzen Begruendung. Beruecksichtige dabei explizit, ob der Spieler von einem \
Mitspieler (dann ggf. Verhandlungsspielraum) oder von Kickbase selbst (Systemangebot, \
Festpreis) angeboten wird.
4. Eine Einschaetzung meiner Position in der Liga im Vergleich zu den anderen Managern \
(wer ist gefaehrlich, worauf sollte ich achten).

Bitte gehe wirklich JEDEN Spieler aus beiden Listen einzeln durch, ueberspringe keinen.

=== MEIN STATUS ===
{status_block}

=== MEIN KADER ({len(own_squad)} Spieler) ===
{squad_lines}

=== TRANSFERMARKT ({len(market_listings)} Spieler) ===
{market_lines}

=== LIGA-TABELLE (aktueller Spieltag) ===
{table_lines}
"""


if __name__ == "__main__":
    print(build_prompt())
