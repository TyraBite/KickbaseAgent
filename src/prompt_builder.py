"""Schritt 2 (MVP): baut aus dem SQLite-Snapshot einen fertigen,
copy-paste-fertigen Analyse-Prompt fuer das Claude-WebUI. Kein API-Call."""

import sqlite3

from src import db


def _latest_fetched_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(fetched_at) FROM own_squad").fetchone()
    return row[0] if row else None


def _status_hint(status_label: str | None) -> str:
    return f" [{status_label}]" if status_label else ""


def _fmt_points(value) -> str:
    """Unterscheidet 'noch keine Saisondaten' (None) von einer echten 0,
    statt der nackten Python-Repraesentation 'None' im Prompt."""
    return "noch keine Saisondaten" if value is None else str(value)


def _appearances(total_points, average_points) -> str:
    """Geschaetzte Einsatzzahl aus Gesamt-/Schnittpunkten - kein direktes
    API-Feld, deshalb klar als Schaetzung gekennzeichnet."""
    if not average_points or total_points is None:
        return "unbekannt"
    return f"~{round(total_points / average_points)} (geschaetzt)"


def _appearance_rate(total_points, average_points, current_matchday) -> str:
    if not average_points or total_points is None or not current_matchday or current_matchday <= 0:
        return "unbekannt"
    appearances = total_points / average_points
    return f"~{round(appearances / current_matchday * 100)}% (geschaetzt)"


def _cost_per_point(value, total_points) -> str:
    if value is None or not total_points:
        return "unbekannt"
    return str(round(value / total_points))


def _market_value_trend(p: sqlite3.Row) -> str:
    change_7d = p["market_value_change_7d"]
    low_92d = p["market_value_low_92d"]
    high_92d = p["market_value_high_92d"]
    if change_7d is None and low_92d is None and high_92d is None:
        raw_trend = p["market_value_trend"] if "market_value_trend" in p.keys() else None
        if raw_trend is not None:
            return f"Trend nicht verfuegbar (roher Kickbase-Code: {raw_trend}, Bedeutung unbestaetigt)"
        return "Trend nicht verfuegbar"
    parts = []
    if change_7d is not None:
        sign = "+" if change_7d >= 0 else ""
        parts.append(f"{sign}{change_7d} (7 Tage)")
    if low_92d is not None and high_92d is not None:
        parts.append(f"Tiefst/Hoechst 92 Tage: {low_92d}/{high_92d}")
    if p["market_value_in_drop_phase"]:
        parts.append("im Preisverfall")
    return ", ".join(parts) or "Trend nicht verfuegbar"


def _player_line(p: sqlite3.Row, current_matchday) -> str:
    verein = f", {p['team_name']}" if p["team_name"] else ""
    return (
        f"- {p['name']} ({p['position']}{verein}){_status_hint(p['status_label'])} | "
        f"Marktwert: {p['market_value']} ({_market_value_trend(p)}) | "
        f"Punkteschnitt: {_fmt_points(p['average_points'])} | "
        f"Punkte gesamt: {_fmt_points(p['total_points'])} | "
        f"Einsatzzahl: {_appearances(p['total_points'], p['average_points'])} | "
        f"Einsatzquote: {_appearance_rate(p['total_points'], p['average_points'], current_matchday)} | "
        f"Kosten/Punkt: {_cost_per_point(p['market_value'], p['total_points'])}"
    )


def _market_line(p: sqlite3.Row, current_matchday) -> str:
    if p["is_system_offer"]:
        anbieter = "Kickbase (kein Anbieter erkannt, freier Spieler)"
    else:
        anbieter = p["offering_username"] or f"Manager {p['offering_user_id']}"

    extra = ""
    if p["pending_offers_count"]:
        if p["is_own_leading_bid"]:
            extra = f" | Gebote: {p['pending_offers_count']} (ICH fuehre aktuell mit {p['leading_bid_price']})"
        elif p["leading_bid_username"]:
            extra = (
                f" | Gebote: {p['pending_offers_count']} "
                f"(fuehrend: {p['leading_bid_username']} mit {p['leading_bid_price']})"
            )
        else:
            extra = f" | Gebote: {p['pending_offers_count']}"

    delta = p["price_delta_pct"]
    delta_hint = ""
    if delta is not None and delta != 0:
        delta_hint = (
            f" | Preis-Delta: {'+' if delta > 0 else ''}{delta}% ggue. Marktwert"
            " -> vermutlich Mitspieler-Angebot mit Verhandlungsspielraum"
        )
    verein = f", {p['team_name']}" if p["team_name"] else ""
    return (
        f"- {p['name']} ({p['position']}{verein}){_status_hint(p['status_label'])} | "
        f"Preis: {p['price']} | Marktwert: {p['market_value']} ({_market_value_trend(p)}) | "
        f"Punkteschnitt: {_fmt_points(p['average_points'])} | "
        f"Punkte gesamt: {_fmt_points(p['total_points'])} | "
        f"Kosten/Punkt: {_cost_per_point(p['price'], p['total_points'])} | "
        f"Angeboten von: {anbieter}{delta_hint}{extra}"
    )


def _form_curve(recent_matchday_points: str | None) -> str:
    if not recent_matchday_points:
        return "noch keine Spieltage in dieser Saison"
    return recent_matchday_points.replace(",", ", ")


def _league_table(conn: sqlite3.Connection, fetched_at: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT user_id, name, season_points, season_placement, team_value,
               matchday_points, recent_matchday_points
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
            f"{r['season_placement']}. {name} - Punkte: {_fmt_points(r['season_points'])} | "
            f"Teamwert: {_fmt_points(r['team_value'])} | "
            f"Spieltagspunkte: {_fmt_points(r['matchday_points'])} | "
            f"Formkurve (letzte Spieltage): {_form_curve(r['recent_matchday_points'])}"
        )
    return lines or ["(keine Liga-Tabellendaten vorhanden)"]


def _manager_budget_line(r: sqlite3.Row) -> str:
    name = r["name"] or r["user_id"]
    herkunft = "exakt" if r["is_own_exact"] else f"geschaetzt, {r['trade_count']} Trades"
    return (
        f"- {name} - Budget: {_fmt_points(r['estimated_budget'])} ({herkunft}) | "
        f"Teamwert: {_fmt_points(r['team_value'])} | "
        f"Verfuegbares Budget inkl. Ueberziehung: {_fmt_points(r['available_budget'])}"
    )


def _manager_budgets_block(conn: sqlite3.Connection, fetched_at: str) -> list[str]:
    rows = conn.execute(
        "SELECT * FROM manager_budgets WHERE fetched_at = ? ORDER BY available_budget DESC",
        (fetched_at,),
    ).fetchall()
    return [_manager_budget_line(r) for r in rows] or ["(keine Budget-Schaetzung vorhanden)"]


def _season_context_block(conn: sqlite3.Connection, fetched_at: str) -> str:
    row = conn.execute(
        "SELECT * FROM season_context WHERE fetched_at = ?", (fetched_at,)
    ).fetchone()
    if not row:
        return "(keine Saisonphasen-Daten vorhanden)"

    parts = []
    if row["season_name"]:
        parts.append(f"Saison {row['season_name']}")
    if row["current_matchday"] is not None:
        parts.append(f"aktueller Spieltag: {row['current_matchday']}")
    if row["days_until_next_deadline"] is not None:
        parts.append(f"naechster Termin in {row['days_until_next_deadline']} Tagen")
    text = ", ".join(parts) if parts else "(unbekannt)"
    return (
        f"{text}\n"
        "(Hinweis: die genaue Bedeutung von Spieltag-Index/Termin-Datum ist noch nicht "
        "im echten Kickbase-Client gegengecheckt - bei Unsicherheit vorsichtig interpretieren.)"
    )


def build_prompt(fetched_at: str | None = None) -> str:
    conn = db.connect()
    conn.row_factory = sqlite3.Row
    try:
        if fetched_at is None:
            fetched_at = _latest_fetched_at(conn)
        if fetched_at is None:
            raise RuntimeError("Kein Snapshot in der Datenbank - erst den Fetcher laufen lassen")

        season_context_row = conn.execute(
            "SELECT current_matchday FROM season_context WHERE fetched_at = ?",
            (fetched_at,),
        ).fetchone()
        current_matchday = season_context_row["current_matchday"] if season_context_row else None

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
        manager_budget_lines = _manager_budgets_block(conn, fetched_at)
        season_block = _season_context_block(conn, fetched_at)
    finally:
        conn.close()

    squad_lines = (
        "\n".join(_player_line(p, current_matchday) for p in own_squad)
        or "(keine Spieler im Kader gefunden)"
    )
    market_lines = (
        "\n".join(_market_line(p, current_matchday) for p in market_listings)
        or "(kein Spieler aktuell auf dem Markt)"
    )
    table_lines = "\n".join(league_table_lines)
    manager_budget_block_lines = "\n".join(manager_budget_lines)

    if own_budget_row:
        status_parts = [f"Budget: {own_budget_row['budget']}"]
        if own_ranking_row:
            status_parts.append(f"Teamwert: {_fmt_points(own_ranking_row['team_value'])}")
            status_parts.append(f"Platzierung: {_fmt_points(own_ranking_row['season_placement'])}")
            status_parts.append(f"Punkte gesamt: {_fmt_points(own_ranking_row['season_points'])}")
        else:
            status_parts.append(
                "(eigener Liga-Ranking-Eintrag nicht gefunden - Teamwert/Platzierung/Punkte fehlen)"
            )
        status_block = "\n".join(status_parts)
    else:
        status_block = "(keine eigenen Statusdaten gefunden)"

    return f"""Du bist mein Kickbase-Berater. Hier sind meine aktuellen Daten vom {fetched_at}. \
Analysiere sie und gib mir:

0. Beruecksichtige zuerst die Saisonphase unten (Spieltag/naechster Termin): wenn der naechste \
Spieltag noch weit entfernt ist, ist keine akute Aufstellungsempfehlung noetig - schaetze das \
selbst anhand der Angabe ein.
1. Eine Aufstellungsempfehlung fuer den naechsten Spieltag (Formation, wer spielt, \
wer pausiert - beruecksichtige auffaellige Status-Codes, siehe Kader unten), falls laut \
Saisonphase ueberhaupt relevant.
2. Fuer JEDEN einzelnen Spieler in meinem Kader unten: Verkaufen oder Halten, mit einer kurzen \
Begruendung (1-2 Saetze). Beruecksichtige dabei explizit die Marktwertentwicklung (Trend/Tiefst-\
Hoechstwert/Preisverfall) und Kosten pro Punkt als eigene Kriterien, nicht nur nebenbei. \
Achte bei Verkaufsempfehlungen darauf, dass keine Position in meinem Kader komplett leerlaeuft.
3. Fuer JEDEN einzelnen Spieler auf dem Transfermarkt unten: Kaufen oder Nicht kaufen, mit einer \
kurzen Begruendung. Beruecksichtige dabei explizit: ob der Spieler von einem Mitspieler (dann ggf. \
Verhandlungsspielraum, siehe Preis-Delta) oder von Kickbase selbst (Systemangebot, Festpreis) \
angeboten wird, sowie mein verfuegbares Budget (siehe MEIN STATUS) - priorisiere bei mehreren \
Kaufempfehlungen danach, was ich mir tatsaechlich leisten kann.
4. Eine Einschaetzung meiner Position in der Liga im Vergleich zu den anderen Managern - nutze dafuer \
nicht nur die aktuelle Platzierung, sondern auch die Formkurve (letzte Spieltage) je Manager: wer ist \
im Aufwind, wer im Abwind, wer ist deshalb besonders gefaehrlich oder gerade verwundbar. Beruecksichtige \
dabei auch die geschaetzten Budgets unten (siehe GESCHAETZTE BUDGETS ALLER MANAGER): wer kann sich \
ueberhaupt noch grosse Transfers leisten und ist deshalb eine echte Bedrohung im Bietwettstreit.

Bitte gehe wirklich JEDEN Spieler aus beiden Listen einzeln durch, ueberspringe keinen.

Hinweis zu "Status-Code X" bei einzelnen Spielern: die genaue Bedeutung jenseits von \
"kein Code = unauffaellig" ist mir nicht zweifelsfrei bekannt (moeglicherweise eine Bitmaske, \
nicht ein einfacher Enum) - wenn relevant, weise in deiner Antwort darauf hin, dass ich das im \
Kickbase-Client selbst gegenchecken sollte.

Hinweis zu "Einsatzzahl"/"Einsatzquote"/"Kosten pro Punkt": das sind von mir aus Gesamt-/ \
Schnittpunkten abgeleitete Schaetzungen, keine direkten Kickbase-Felder - bei der Interpretation \
entsprechend vorsichtig sein.

=== SAISONPHASE ===
{season_block}

=== MEIN STATUS ===
{status_block}

=== MEIN KADER ({len(own_squad)} Spieler) ===
{squad_lines}

=== TRANSFERMARKT ({len(market_listings)} Spieler) ===
{market_lines}

=== LIGA-TABELLE ===
{table_lines}

Hinweis zu geschaetzten Budgets: Kickbase zeigt Kontostaende anderer Manager nicht direkt an. Die \
Werte unten sind aus dem Liga-Activity-Feed hochgerechnet (Transfers nachvollzogen, Login-Bonus \
gleichmaessig auf alle verteilt, Achievement-Bonus anteilig nach Saisonpunkten skaliert) - nur meine \
eigene Zeile (markiert "exakt") ist ein echter Wert. Nutze die Schaetzungen als grobe Tendenz, nicht \
als exakte Zahl.

=== GESCHAETZTE BUDGETS ALLER MANAGER ===
{manager_budget_block_lines}
"""


if __name__ == "__main__":
    print(build_prompt())
