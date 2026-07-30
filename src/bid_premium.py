"""Historische Gebotsaufschlaege fuer Kickbase-Systemangebote (freie Spieler,
von Kickbase selbst zum Kauf angeboten) - Basis fuer clientseitige
Gebotsempfehlungen (siehe frontend/src/lib/derive.ts::suggestBid()).

Kickbase-Systemangebote laufen als blindes Sealed-Bid-Verfahren: echte
Konkurrenzgebote sind waehrend der Frist nie sichtbar, nur rueckwirkend der
tatsaechliche Gewinnbetrag (ueber den Liga-Activity-Feed, Typ-15-Trade-
Eintraege ohne 'slr'/Verkaeufer-Feld = Systemkauf). Dieses Modul loggt jeden
abgeschlossenen Systemkauf mit seinem Marktwert-Aufschlag in Firestore
(bid_premium_log), inkrementell per Zeiger-Dokument (kein Full-Scan bei
jedem 2h-Lauf)."""

import datetime
import sys

from src.kickbase_client import get_market_value_history

TRADE_ACTIVITY_TYPE = 15
EPOCH = datetime.date(1970, 1, 1)
HISTORY_TIMEFRAME_DAYS = 365


def _is_system_purchase(activity: dict) -> bool:
    if activity.get("t") != TRADE_ACTIVITY_TYPE:
        return False
    return not activity.get("data", {}).get("slr")


def _compute_premium(price: float | None, market_value_then: float | None) -> float | None:
    if not market_value_then or price is None:
        return None
    return price / market_value_then - 1


def _filter_new_system_purchases(activities: list[dict], since_dt: str | None) -> list[dict]:
    """since_dt ist der ISO-Timestamp der zuletzt verarbeiteten Aktivitaet
    (Zeiger, siehe firestore_db.get_bid_premium_state) - None beim allerersten
    Lauf (dann werden ALLE bisherigen Systemkaeufe verarbeitet, das ist der
    Backfill). Grenze ist INKLUSIV (>=), nicht exklusiv - siehe Test-
    Docstring fuer die Begruendung."""
    return [
        a
        for a in activities
        if _is_system_purchase(a) and (since_dt is None or a.get("dt", "") >= since_dt)
    ]


def _days_since_epoch(iso_date: str) -> int:
    date_part = iso_date.split("T")[0]
    return (datetime.date.fromisoformat(date_part) - EPOCH).days


def _market_value_at(history: dict, target_days: int) -> float | None:
    for entry in history.get("it") or []:
        if entry.get("dt") == target_days:
            return entry.get("mv")
    return None


def build_new_entries(
    token: str,
    league_id: str,
    activities: list[dict],
    since_dt: str | None,
    players_map: dict[str, dict],
    get_history=get_market_value_history,
) -> tuple[list[dict], str | None]:
    """Filtert neue Systemkaeufe seit since_dt, loest pro Kauf den Marktwert
    zum Kaufzeitpunkt auf und baut daraus bid_premium_log-Eintraege.
    position/average_points_then kommen bewusst aus dem AKTUELLEN players_map-
    Stand (keine guenstige historische Punkteschnitt-Quelle vorhanden, siehe
    Global Constraints in der Plan-Datei) - Naeherung, kein exakter
    historischer Wert.

    Der Zeiger wandert bis zur letzten tatsaechlich VERARBEITETEN Aktivitaet
    (auch wenn eine einzelne History-Abfrage fehlschlug) - ein dauerhaft
    fehlender Marktwert (z.B. Kauf aelter als HISTORY_TIMEFRAME_DAYS) soll
    nicht bei jedem 2h-Lauf erneut versucht werden. Kaeufe mit unbekanntem
    Spieler (nicht in players_map) zaehlen NICHT als verarbeitet - der Zeiger
    bleibt davor stehen, falls players_map beim naechsten Lauf aktueller ist."""
    new_purchases = _filter_new_system_purchases(activities, since_dt)
    if not new_purchases:
        return [], None

    entries = []
    last_processed_dt = None
    for activity in new_purchases:
        data = activity["data"]
        player_id = data.get("pi")
        player = players_map.get(player_id)
        if not player:
            print(
                f"Warnung: bid_premium - Spieler {player_id!r} nicht in players_map, "
                "Kauf uebersprungen",
                file=sys.stderr,
            )
            continue
        last_processed_dt = activity["dt"]

        try:
            history = get_history(token, league_id, player_id, timeframe=HISTORY_TIMEFRAME_DAYS)
        except Exception as exc:
            print(f"Warnung: bid_premium - Marktwert-Historie fuer {player_id!r} fehlgeschlagen: {exc}", file=sys.stderr)
            continue

        target_days = _days_since_epoch(activity["dt"])
        market_value_then = _market_value_at(history, target_days)
        premium_pct = _compute_premium(data.get("trp"), market_value_then)
        if premium_pct is None:
            print(
                f"Warnung: bid_premium - kein Marktwert am Kauftag fuer {player_id!r} "
                f"(Tag {target_days}), Kauf uebersprungen",
                file=sys.stderr,
            )
            continue

        entries.append({
            "activity_id": activity["i"],
            "player_id": player_id,
            "position": player["position"],
            "market_value_then": market_value_then,
            "average_points_then": player.get("average_points"),
            "premium_pct": premium_pct,
            "purchased_at": activity["dt"],
        })

    return entries, last_processed_dt
