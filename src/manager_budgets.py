"""Reine Berechnungslogik fuer eine grobe Budget-Schaetzung aller Liga-Manager.

Kickbase gibt Kontostaende anderer Manager nicht direkt heraus (nur den
eigenen via kickbase_client.get_me()). Diese Schaetzung rekonstruiert sie aus
dem Liga-Activity-Feed: Trades (Kauf/Verkauf), Login-Boni, Achievement-Boni.

WICHTIG - bestaetigt an echten Daten (27.07.2026): Trade-Eintraege im Feed
referenzieren Manager per NAME ("byr"/"slr", z.B. "Fleischmanns"), NICHT per
User-Id wie in einem fremden Referenz-Client urspruenglich angenommen. Der
Name matcht exakt das "name"-Feld aus der Liga-Ranking-Response. Deshalb
rechnet dieses Modul durchgehend mit Namen als Schluessel; die Zuordnung zu
user_id (fuer die DB-Speicherung) passiert erst am Ende ueber ranking_rows.

Kein HTTP hier drin (kein requests/token) - das Holen der Rohdaten inkl.
Fehlerresilienz pro Call bleibt in fetcher.py, analog zu
_apply_market_value_history. Dieses Modul bekommt die schon geladenen
Rohdaten uebergeben und ist dadurch isoliert testbar (siehe tests/).
"""

from __future__ import annotations

TRADE_TYPE = 15
LOGIN_BONUS_TYPE = 22
ACHIEVEMENT_TYPE = 26

# Kickbase-Regel: maximale Ueberziehung ist 33% des aktuellen Teamwerts.
OVERDRAFT_FACTOR = -0.33


def _parse_trades(activities: list[dict], league_start_date: str | None) -> list[dict]:
    """Filtert Typ-15-Eintraege (Trade), optional per Datumscutoff (ISO-String-
    Vergleich, funktioniert weil Kickbase durchgehend ISO-8601-Timestamps
    liefert). Gibt die 'data'-Dicts zurueck (byr/slr/trp/t)."""
    trades = []
    for entry in activities:
        if entry.get("t") != TRADE_TYPE:
            continue
        if league_start_date and entry.get("dt", "") < league_start_date:
            continue
        trades.append(entry.get("data", {}))
    return trades


def _replay_trade_ledger(
    trades: list[dict], known_names: set[str], start_budget: float
) -> dict[str, float]:
    """Seedet ALLE bekannten Manager mit start_budget (nicht nur die mit
    Trades - ein Manager ohne jeden Trade fehlt sonst komplett), wendet dann
    jeden Trade an: byr (Kaeufer) -trp, slr (Verkaeufer) +trp. Fehlt byr oder
    slr, war es ein Kauf/Verkauf gegen das System (kein Gegenpart zu buchen).
    Unbekannte Namen (sollte nicht vorkommen, aber kein Grund zum Abbruch)
    werden ignoriert."""
    budgets = {name: float(start_budget) for name in known_names}
    for trade in trades:
        byr = trade.get("byr")
        slr = trade.get("slr")
        price = trade.get("trp", 0) or 0
        if byr in budgets:
            budgets[byr] -= price
        if slr in budgets:
            budgets[slr] += price
    return budgets


def _count_trades_per_name(trades: list[dict], known_names: set[str]) -> dict[str, int]:
    counts = {name: 0 for name in known_names}
    for trade in trades:
        for participant in (trade.get("byr"), trade.get("slr")):
            if participant in counts:
                counts[participant] += 1
    return counts


def _login_bonus_total(activities: list[dict]) -> float:
    """Summe aller Login-Boni der Liga. Wird gleichmaessig auf JEDEN Manager
    addiert (Annahme: jeder loggt sich taeglich ein) - einzig moegliche
    Schaetzung, da fremde Login-Bonus-Historie nicht einsehbar ist."""
    return sum(
        entry.get("data", {}).get("bn", 0) or 0
        for entry in activities
        if entry.get("t") == LOGIN_BONUS_TYPE
    )


def unique_achievement_ids(activities: list[dict]) -> set:
    """Dedupliziert Achievement-Ids: 'ac'/'er' aus get_achievement_reward()
    sind der KUMULIERTE Gesamtstand, ein wiederholt im Feed auftauchendes
    Achievement darf deshalb nur einmal abgefragt/gezaehlt werden. Oeffentlich,
    weil fetcher.py das Ergebnis braucht, um die einzelnen Rewards per HTTP
    abzufragen (HTTP-Calls gehoeren nicht in dieses Modul, siehe Docstring
    oben)."""
    return {
        entry["data"]["t"]
        for entry in activities
        if entry.get("t") == ACHIEVEMENT_TYPE and entry.get("data", {}).get("t") is not None
    }


def _scale_achievement_bonus(anchor_bonus: float, own_points, target_points) -> float:
    """Skaliert den (nur fuer den eigenen User bekannten) Achievement-Bonus
    linear nach Saisonpunkte-Verhaeltnis auf einen anderen Manager. Fehlen
    dessen Punkte, gibt es keine belastbare Schaetzung -> 0 statt Raten."""
    if target_points is None:
        return 0.0
    if not own_points:
        return anchor_bonus
    return anchor_bonus * (target_points / own_points)


def _overdraft(budget: float, team_value) -> tuple[float, float]:
    """Kickbase-Regel: maximal 33% des Teamwerts Ueberziehung erlaubt."""
    team_value = team_value or 0
    max_negative = (team_value + budget) * OVERDRAFT_FACTOR
    available = budget - max_negative
    return max_negative, available


def estimate_all(
    *,
    activities: list[dict],
    ranking_rows: list[dict],
    own_name: str,
    own_budget: float,
    start_budget: float,
    league_start_date: str | None,
    achievement_bonus_total: float,
) -> list[dict]:
    """Schaetzt Budgets aller Manager. ranking_rows braucht mind. 'user_id'/
    'name'/'team_value'/'season_points' (wie in fetcher.py aufgebaut).
    achievement_bonus_total ist die Summe aus ac*er ueber alle deduplizierten
    Achievement-Ids des EIGENEN Users (siehe _unique_achievement_ids), wird
    hier pro Manager nach Punkte-Verhaeltnis skaliert.

    Gibt eine nach 'available_budget' absteigend sortierte Liste fertiger
    DB-Row-Dicts zurueck. Die eigene Zeile wird mit dem echten own_budget
    ueberschrieben (exakt statt geschaetzt) - konsequenterweise auch VOR der
    Ueberziehungsberechnung, damit 'available_budget' fuer die eigene Zeile
    ebenfalls exakt ist."""
    known_names = {row["name"] for row in ranking_rows if row.get("name")}

    trades = _parse_trades(activities, league_start_date)
    budgets = _replay_trade_ledger(trades, known_names, start_budget)
    trade_counts = _count_trades_per_name(trades, known_names)

    login_bonus = _login_bonus_total(activities)
    for name in budgets:
        budgets[name] += login_bonus

    own_points = next(
        (row.get("season_points") for row in ranking_rows if row.get("name") == own_name),
        None,
    )
    for row in ranking_rows:
        name = row.get("name")
        if not name or name not in budgets:
            continue
        budgets[name] += _scale_achievement_bonus(
            achievement_bonus_total, own_points, row.get("season_points")
        )

    if own_name in budgets:
        budgets[own_name] = float(own_budget)

    results = []
    for row in ranking_rows:
        name = row.get("name")
        if not name or name not in budgets:
            continue
        budget = budgets[name]
        max_negative, available = _overdraft(budget, row.get("team_value"))
        results.append(
            {
                "user_id": row.get("user_id"),
                "name": name,
                "estimated_budget": round(budget),
                "is_own_exact": 1 if name == own_name else 0,
                "team_value": row.get("team_value"),
                "max_negative_budget": round(max_negative),
                "available_budget": round(available),
                "trade_count": trade_counts.get(name, 0),
            }
        )
    results.sort(key=lambda r: r["available_budget"], reverse=True)
    return results
