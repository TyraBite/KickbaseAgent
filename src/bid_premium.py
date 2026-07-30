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

TRADE_ACTIVITY_TYPE = 15


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
