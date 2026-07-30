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

from src import firestore_db
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
    own_name: str | None = None,
    get_history=get_market_value_history,
) -> tuple[list[dict], str | None]:
    """Filtert neue Systemkaeufe seit since_dt, loest pro Kauf den Marktwert
    zum Kaufzeitpunkt auf und baut daraus bid_premium_log-Eintraege.
    position/average_points_then kommen bewusst aus dem AKTUELLEN players_map-
    Stand (keine guenstige historische Punkteschnitt-Quelle vorhanden, siehe
    Global Constraints in der Plan-Datei) - Naeherung, kein exakter
    historischer Wert.

    Zwei verschiedene Fehlerklassen, zwei verschiedene Zeiger-Reaktionen:
    - Spieler nicht (mehr) in players_map: i.d.R. PERMANENT (aus dem aktuell
      getrackten Kickbase-Kader-Pool raus, z.B. abgestiegen/Vertragsende) -
      Warten bringt nichts, der Zeiger rueckt trotzdem vor (kein Grund, das
      bei jedem Lauf erneut zu versuchen). Live-Fund 2026-07-30: 17 von 22
      historisch fehlenden Kaeufen waren genau das.
    - Marktwert-Historie nicht abrufbar ODER kein Marktwert am exakten
      Kauftag: kann TRANSIENT sein (z.B. der Marktwert von HEUTE ist erst
      nach dem naechtlichen Heavy-Lauf verfuegbar - ein Kauf von heute
      Morgen hat notwendigerweise noch keinen Marktwert-Eintrag fuer heute).
      Hier darf der Zeiger NICHT ueber die betroffene Aktivitaet vorruecken,
      auch wenn danach WEITERE Aktivitaeten erfolgreich sind - sonst wird
      sie permanent unerreichbar, sobald der Zeiger (Filter ist
      `dt >= since_dt`) an ihr vorbeigezogen ist. Live-Fund 2026-07-30: die
      alten 4 verbleibenden Faelle der 22 fehlenden Kaeufe waren alle vom
      selben Tag wie der Lauf selbst - reine Verfuegbarkeits-Verzoegerung,
      loest sich von selbst am naechsten Tag.

    In BEIDEN Faellen werden Aktivitaeten NACH dem jeweiligen Punkt trotzdem
    ganz normal weiterverarbeitet/geschrieben (Firestore-Write ist
    idempotent) - nur der Zeiger-Fortschritt unterscheidet sich.

    Aktivitaeten werden dafuer CHRONOLOGISCH (nicht in Feed-Reihenfolge)
    verarbeitet - get_activities_feed()s Reihenfolge ist laut eigenem
    Docstring UNBESTAETIGT (moeglicherweise newest-first statt
    oldest-first), die Luecken-Erkennung braucht aber eine wohldefinierte
    "vor/nach"-Beziehung zwischen Aktivitaeten."""
    new_purchases = _filter_new_system_purchases(activities, since_dt)
    if not new_purchases:
        return [], None

    entries = []
    pointer = None
    gap_found = False
    for activity in sorted(new_purchases, key=lambda a: a["dt"]):
        data = activity["data"]
        player_id = data.get("pi")
        player = players_map.get(player_id)
        if not player:
            print(
                f"Warnung: bid_premium - Spieler {player_id!r} nicht in players_map, "
                "Kauf uebersprungen",
                file=sys.stderr,
            )
            # Anders als die beiden Faelle unten ist das i.d.R. PERMANENT (der
            # Spieler ist aus dem aktuell getrackten Kickbase-Kader-Pool raus,
            # z.B. abgestiegen/Vertragsende) - Warten/Retry bringt hier nichts,
            # der Zeiger darf trotzdem vorruecken (kein gap_found).
            if not gap_found:
                pointer = activity["dt"]
            continue

        try:
            history = get_history(token, league_id, player_id, timeframe=HISTORY_TIMEFRAME_DAYS)
        except Exception as exc:
            print(f"Warnung: bid_premium - Marktwert-Historie fuer {player_id!r} fehlgeschlagen: {exc}", file=sys.stderr)
            gap_found = True
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
            gap_found = True
            continue

        entries.append({
            "activity_id": activity["i"],
            "player_id": player_id,
            "position": player["position"],
            "market_value_then": market_value_then,
            "average_points_then": player.get("average_points"),
            "premium_pct": premium_pct,
            "purchased_at": activity["dt"],
            "bought_by_self": bool(own_name) and data.get("byr") == own_name,
        })
        if not gap_found:
            pointer = activity["dt"]

    return entries, pointer


MAX_HISTORY_ENTRIES_IN_SNAPSHOT = 400


def detect_unsold_listings(
    market_listings: list[dict],
    activities: list[dict],
    last_seen_ids: list[str],
    players_map: dict[str, dict],
    detected_at: str,
) -> tuple[list[dict], list[str]]:
    """Vergleicht die Systemangebote-Spieler-IDs von 'letztem Lauf' (last_seen_ids)
    gegen 'jetzt' (market_listings) - jede verschwundene ID, fuer die sich KEIN
    Trade (egal ob Systemkauf oder Mitspieler-Handel) im Activity-Feed findet,
    gilt als unverkauft abgelaufen (0% Aufschlag haette gereicht). Findet sich
    IRGENDEIN Trade fuer diese ID, ist das Verschwinden erklaert (Systemkauf
    landet ohnehin schon in bid_premium_log ueber build_new_entries();
    Mitspieler-Handel ist regulaerer Weiterverkauf, kein Signal fuer
    Gebotsvorschlaege). Keine Kickbase-API-Calls - nutzt nur bereits
    abgerufene Daten."""
    current_ids = [l["player_id"] for l in market_listings if l["is_system_offer"]]
    current_ids_set = set(current_ids)
    disappeared = set(last_seen_ids) - current_ids_set

    traded_player_ids = {
        a["data"].get("pi")
        for a in activities
        if a.get("t") == TRADE_ACTIVITY_TYPE
    }

    entries = []
    for player_id in disappeared:
        if player_id in traded_player_ids:
            continue
        player = players_map.get(player_id)
        if not player:
            continue
        entries.append({
            "player_id": player_id,
            "position": player["position"],
            "market_value_then": player.get("market_value"),
            "average_points_then": player.get("average_points"),
            "detected_at": detected_at,
        })

    return entries, current_ids


def _build_outcome_counts(full_history: list[dict], unsold_log: list[dict]) -> dict:
    counts: dict[str, dict[str, int]] = {}
    for entry in full_history:
        bucket = counts.setdefault(entry["position"], {"rival_purchases": 0, "self_purchases": 0, "unsold": 0})
        if entry.get("bought_by_self"):
            bucket["self_purchases"] += 1
        else:
            bucket["rival_purchases"] += 1
    for entry in unsold_log:
        bucket = counts.setdefault(entry["position"], {"rival_purchases": 0, "self_purchases": 0, "unsold": 0})
        bucket["unsold"] += 1
    return counts


def update_and_load(
    client,
    token: str,
    league_id: str,
    activities: list[dict],
    players_map: dict[str, dict],
    market_listings: list[dict],
    own_name: str | None,
    detected_at: str,
    activity_feed_ok: bool = True,
    get_history=get_market_value_history,
) -> tuple[list[dict], dict]:
    """Zentraler Einstiegspunkt, von dashboard_export.export() aufgerufen.
    client=None (FIRESTORE_ENABLED fehlt, lokaler Testlauf) ist ein reines
    No-Op - leere Historie UND leere outcome_counts in diesem Fall.

    Die bid_premium_log-Collection waechst dauerhaft (ein Eintrag pro
    Systemkauf, fuer den Rest der Saison und darueber hinaus) und wird
    komplett in dashboard_snapshot/latest eingebettet (Firestores 1-MiB-
    Dokumentgrenze, schon jetzt ~450 Spieler schwer). suggestBid() im
    Frontend nutzt ohnehin nur die k=20 aehnlichsten Eintraege je Position -
    hier deshalb auf die MAX_HISTORY_ENTRIES_IN_SNAPSHOT neuesten Kaeufe
    gedeckelt (neueste zuerst, absteigend nach purchased_at). activity_id
    ist nur die Firestore-Schreib-Doc-Id und wird von keinem Frontend-
    Verbraucher gelesen (siehe frontend/src/types.ts::BidPremiumEntry) -
    wird deshalb vor dem Zurueckgeben entfernt statt unnoetig mitgeschickt
    zu werden.

    outcome_counts wird aus der VOLLEN (nicht gedeckelten) Historie berechnet
    - eine Zaehlung soll nicht durch den Snapshot-Cap verzerrt werden.

    activity_feed_ok=False (dashboard_export.py konnte den Activity-Feed
    NICHT laden, activities ist dann [] als sicherer No-Op fuer
    build_new_entries() oben) macht detect_unsold_listings() NICHT sicher -
    mit activities=[] waere JEDES verschwundene Systemangebot faelschlich
    "unverkauft abgelaufen", auch tatsaechlich gekaufte. Deshalb in diesem
    Fall die Unsold-Erkennung UND den last_seen_system_listing_ids-Zeiger-
    Write komplett auslassen (Zeiger bleibt bewusst stehen - ein laengeres
    Vergleichsfenster beim naechsten erfolgreichen Lauf ist harmlos, die
    player_id_detected_at-Doc-Id macht Re-Erkennung am selben Tag ohnehin
    idempotent)."""
    if client is None:
        return [], {}

    pointer = firestore_db.get_bid_premium_pointer(client)
    new_entries, new_pointer = build_new_entries(
        token, league_id, activities, pointer, players_map, own_name, get_history=get_history
    )
    if new_entries:
        firestore_db.upsert_bid_premium_entries(client, new_entries)
    if new_pointer:
        firestore_db.upsert_bid_premium_pointer(client, new_pointer)

    if activity_feed_ok:
        last_seen_ids = firestore_db.get_bid_premium_last_seen_listing_ids(client)
        unsold_entries, current_ids = detect_unsold_listings(
            market_listings, activities, last_seen_ids, players_map, detected_at
        )
        if unsold_entries:
            firestore_db.upsert_unsold_log_entries(client, unsold_entries)
        firestore_db.upsert_bid_premium_last_seen_listing_ids(client, current_ids)
    else:
        print(
            "Warnung: bid_premium - Activity-Feed war nicht ladbar, "
            "unsold-Erkennung fuer diesen Lauf uebersprungen (Zeiger "
            "last_seen_system_listing_ids bleibt unveraendert)",
            file=sys.stderr,
        )

    full_history = firestore_db.get_bid_premium_history(client)
    unsold_log = firestore_db.get_unsold_log(client)
    outcome_counts = _build_outcome_counts(full_history, unsold_log)

    capped = sorted(full_history, key=lambda e: e["purchased_at"], reverse=True)[:MAX_HISTORY_ENTRIES_IN_SNAPSHOT]
    history_for_frontend = [{k: v for k, v in e.items() if k != "activity_id"} for e in capped]
    return history_for_frontend, outcome_counts
