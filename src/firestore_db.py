"""Firestore-Persistenz fuer Kickbase-Snapshots.

Die urspruengliche "Phase 1" (siehe
docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md)
schrieb Kader/Markt/Liga/Budget als eigene Rohdaten-Collections
(own_squad/market_listings/league_ranking/manager_budgets/season_context/
own_budget_history), gedacht als spaetere Live-Datenquelle fuers Frontend.
Wurde nie so implementiert - Phase 2 fuehrte stattdessen den konsolidierten
dashboard_snapshot/latest-Read ein (upsert_dashboard_snapshot), der Client
liest NUR dieses eine Dokument. Die 6 Rohdaten-Collections wurden dadurch nie
gelesen (weder Client noch Pipeline selbst, die haengt an SQLite/src/db.py) -
am 2026-07-29 als totes Gewicht identifiziert und komplett entfernt (Writes
UND die Funktionen hier). `firestore.rules` verweigert Client-Reads darauf
ohnehin explizit.

Verbleibende Collections: `ml_prediction_log`/`ml_accuracy_daily` (ML-
Bookkeeping, siehe market_predictor.py), `dashboard_snapshot` (der einzige
vom Frontend gelesene Snapshot) und `wunschkader` (User-editierbare Ziel-
Config, Schreibpfad ist der Browser). Mehrzeilige Writes nutzen Firestore-
WriteBatch (max. 500 Operationen/Batch - siehe _write_in_batches).
"""

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

MAX_BATCH_OPS = 500


class FirestoreWriteError(Exception):
    """Signalisiert einen fehlgeschlagenen Firestore-Schreibzugriff auf Daten,
    die das Frontend direkt anzeigt - z.B. bei
    Spark-Free-Tier-Quota-Erschoepfung. Anders als die ML-internen Bookkeeping-
    Schreibversuche in market_predictor.py (die weiterhin nur warnen und
    weiterlaufen) darf so ein Fehler die Pipeline nicht stillschweigend gruen
    durchlaufen lassen - sonst bleibt die Live-Seite unbemerkt auf altem Stand,
    waehrend dashboard.yml gruen bleibt. fetched_at haengt am Fehler, damit
    export() trotz des Fehlers mit dem bereits lokal (SQLite) fertigen
    Snapshot weiterarbeiten und den Fehler erst am Ende hochreichen kann."""

    def __init__(self, fetched_at: str, message: str):
        super().__init__(message)
        self.fetched_at = fetched_at


def connect() -> firestore.Client:
    """Liest Projekt/Credentials automatisch aus der Standard-Google-Cloud-
    Umgebung (GOOGLE_APPLICATION_CREDENTIALS) - keine eigene Credential-
    Lade-Logik, wie im Spec-Dokument festgelegt."""
    return firestore.Client()


def _write_in_batches(client: firestore.Client, collection: str, docs: dict[str, dict]) -> None:
    items = list(docs.items())
    for start in range(0, len(items), MAX_BATCH_OPS):
        batch = client.batch()
        for doc_id, data in items[start : start + MAX_BATCH_OPS]:
            batch.set(client.collection(collection).document(doc_id), data)
        batch.commit()


def upsert_prediction_log_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Firestore-Pendant zu data/ml_prediction_log.jsonl (kein SQLite-Original -
    neue Collection laut Spec). Doc-Id `{date}_{player_id}_{model_type}` macht
    Re-Laeufe desselben Tages idempotent (pro Modell-Kandidat), analog zur
    Dedup-Logik in market_predictor._save_prediction_log(). `.get()` statt
    `e["model_type"]`: Alt-Eintraege aus der Zeit vor Phase 4 (ohne
    model_type-Feld) duerfen den Batch-Write nicht mit einem KeyError
    abbrechen, wenn sie im selben Tages-Batch neben neuen Eintraegen liegen."""
    docs = {f"{e['date']}_{e['player_id']}_{e.get('model_type')}": e for e in entries}
    _write_in_batches(client, "ml_prediction_log", docs)


def get_recent_prediction_log_entries(client: firestore.Client, since_date: str, before_date: str) -> list[dict]:
    """Liest NUR ml_prediction_log-Eintraege im Bereich [since_date,
    before_date) - serverseitig per Doppel-Range-Filter auf demselben Feld
    (kein Composite-Index noetig). Die Collection waechst taeglich um
    ~900 Rohdaten-Dokumente (450 Spieler x 2 Modelle), ein ungefiltertes
    Voll-Scan bei jedem der 12 taeglichen Laeufe wuerde Firestores
    Read-Quota sprengen (siehe HANDOFF.md, Quota-Vorfall 2026-07-28).
    `before_date` (exklusiv, typischerweise "heute") spart zusaetzlich die
    Eintraege des laufenden Tages, die ohnehin noch nicht auswertbar sind
    (kein Folgetag-Marktwert bekannt) und sonst gelesen und sofort
    verworfen wuerden. `ml_prediction_log` ist seit Phase-4-Quota-Fix nur
    noch eine kurzlebige Staging-Zone fuer NEUE, noch nicht ausgewertete
    Prognosen - siehe market_predictor.EVALUATION_LOOKBACK_DAYS."""
    query = (
        client.collection("ml_prediction_log")
        .where(filter=FieldFilter("date", ">=", since_date))
        .where(filter=FieldFilter("date", "<", before_date))
    )
    return [doc.to_dict() for doc in query.stream()]


def upsert_accuracy_daily(client: firestore.Client, entries: list[dict]) -> None:
    """Aggregierte Tages-/Modell-Genauigkeit (EIN Dokument pro (date,
    model_type) statt Rohdaten pro Spieler) - Doc-Id `{date}_{model_type}`.
    Ermoeglicht Trailing-Fenster-/Trend-Berechnung ueber lange Zeitraeume
    mit nur ~2 Dokumenten pro Tag statt ~900 - der eigentliche Fix fuers
    Quota-Problem. Idempotent (Ueberschreiben bei erneuter Auswertung
    desselben Tages ist unproblematisch)."""
    docs = {f"{e['date']}_{e['model_type']}": e for e in entries}
    _write_in_batches(client, "ml_accuracy_daily", docs)


def get_accuracy_daily(client: firestore.Client) -> list[dict]:
    """Liest die komplette ml_accuracy_daily-Collection - unkritisch klein
    (2 Dokumente pro Tag, auch nach einem Jahr nur ~730 Dokumente total,
    verglichen mit ~164.000+ bei der alten Rohdaten-basierten Variante)."""
    return [doc.to_dict() for doc in client.collection("ml_accuracy_daily").stream()]


def upsert_dashboard_snapshot(client: firestore.Client, data: dict) -> None:
    """Phase 2: schreibt den kompletten, bereits berechneten Dashboard-Dict
    (dashboard_export.py::export(), Joins/ML/Fairwert schon fertig gemischt)
    als EIN Dokument - keine Rekonstruktion aus den rohen Collections auf
    Client-Seite, siehe Spec. Immer genau ein Dokument, kein Batching noetig."""
    client.collection("dashboard_snapshot").document("latest").set(data)


def get_dashboard_snapshot(client: firestore.Client) -> dict | None:
    """Liest den zuletzt geschriebenen Dashboard-Snapshot (dashboard_snapshot/
    latest, siehe upsert_dashboard_snapshot) - bisher ein reines Schreibziel,
    jetzt zusaetzlich Lesequelle fuer dashboard_export.export()s
    DASHBOARD_MODE=light-Zweig. None signalisiert Cold Start (noch nie
    geschrieben): der Light-Zweig faellt dann automatisch auf den vollen
    Marktwert-Lauf zurueck (siehe _resolve_is_light in dashboard_export.py)."""
    doc = client.collection("dashboard_snapshot").document("latest").get()
    return doc.to_dict() if doc.exists else None


def get_wunschkader(client: firestore.Client) -> dict | None:
    """Liest den kompletten Wunschkader-Datensatz (targets/sell_list/
    markup_rules/login_bonus/formation/season_start als EIN Dokument,
    ehemals data/wunschkader.json). None falls noch kein Dokument existiert
    (vor der einmaligen Migration)."""
    doc = client.collection("wunschkader").document("current").get()
    return doc.to_dict() if doc.exists else None


def upsert_bid_premium_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Ein Dokument pro abgeschlossenem Systemkauf, Doc-Id = Activity-Id
    (macht Re-Laeufe idempotent, analog upsert_prediction_log_entries)."""
    docs = {e["activity_id"]: e for e in entries}
    _write_in_batches(client, "bid_premium_log", docs)


def get_bid_premium_history(client: firestore.Client) -> list[dict]:
    """Liest die komplette bid_premium_log-Collection - bei ~100-200 kleinen
    Dokumenten (4-5 Felder je Eintrag) unkritisch fuer die Read-Quota,
    analog get_accuracy_daily. Wird EINMAL pro Lauf gelesen, nicht pro
    Spieler/Anfrage."""
    return [doc.to_dict() for doc in client.collection("bid_premium_log").stream()]


def get_bid_premium_pointer(client: firestore.Client) -> str | None:
    """Letzte verarbeitete Activity-Id/Datum (siehe src/bid_premium.py) -
    ein einziges kleines Dokument statt eines Full-Scans der wachsenden
    bid_premium_log-Collection bei jedem 2h-Lauf."""
    doc = client.collection("bid_premium_state").document("current").get()
    return doc.to_dict().get("last_processed_dt") if doc.exists else None


def upsert_bid_premium_pointer(client: firestore.Client, dt: str) -> None:
    client.collection("bid_premium_state").document("current").set(
        {"last_processed_dt": dt}, merge=True
    )


def get_bid_premium_last_seen_listing_ids(client: firestore.Client) -> list[str]:
    """Systemangebote-Spieler-IDs, die beim letzten Lauf noch gelistet waren
    - Vergleichsbasis fuer detect_unsold_listings() (src/bid_premium.py).
    Liegt im selben Dokument wie last_processed_dt, aber unabhaengig davon
    aktualisiert - deshalb merge=True bei beiden Writes."""
    doc = client.collection("bid_premium_state").document("current").get()
    return doc.to_dict().get("last_seen_system_listing_ids", []) if doc.exists else []


def upsert_bid_premium_last_seen_listing_ids(client: firestore.Client, ids: list[str]) -> None:
    client.collection("bid_premium_state").document("current").set(
        {"last_seen_system_listing_ids": ids}, merge=True
    )


def upsert_unsold_log_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Ein Dokument pro erkanntem 'unverkauft abgelaufen'-Fall, Doc-Id =
    player_id + detected_at (macht Re-Laeufe am selben Tag idempotent)."""
    docs = {f"{e['player_id']}_{e['detected_at']}": e for e in entries}
    _write_in_batches(client, "bid_premium_unsold_log", docs)


def get_unsold_log(client: firestore.Client) -> list[dict]:
    """Liest die komplette bid_premium_unsold_log-Collection - klein und
    langsam wachsend (nur bei tatsaechlich unverkauften Angeboten), analog
    get_bid_premium_history."""
    return [doc.to_dict() for doc in client.collection("bid_premium_unsold_log").stream()]


def upsert_fitness_history_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Ein Dokument pro Status-Wechsel (siehe
    dashboard_export._detect_status_changes), Doc-Id `{date}_{player_id}`
    macht einen erneuten Heavy-Lauf am selben Tag idempotent (ueberschreibt
    statt zu duplizieren)."""
    docs = {f"{e['date']}_{e['player_id']}": e for e in entries}
    _write_in_batches(client, "fitness_history_log", docs)


def get_fitness_history(client: firestore.Client) -> list[dict]:
    """Liest die komplette fitness_history_log-Collection - bleibt klein
    (nur echte Statuswechsel, deutlich unter 450/Tag), analog
    get_bid_premium_history. Wird einmal pro ML-Lauf gelesen, nicht pro
    Spieler."""
    return [doc.to_dict() for doc in client.collection("fitness_history_log").stream()]


def upsert_fitness_status_baseline(client: firestore.Client, status_by_player: dict[str, int]) -> None:
    """Baseline NUR der status_codes (player_id -> status_code), komplett
    unabhaengig vom dashboard_snapshot/latest-Dokument und damit unberuehrt
    vom stuendlichen Light-Cron (der dashboard_snapshot/latest ueberschreibt
    und dabei status_code fuer own_squad/market_listings-Spieler aktualisiert -
    genau das wuerde die Diff-Baseline korrumpieren, wenn sie stattdessen aus
    dashboard_snapshot/latest gelesen wuerde). Wird JEDEN Heavy-Lauf komplett
    ueberschrieben (kein Merge - immer der volle all_players-Stand von JETZT),
    Diff-Quelle fuer den naechsten Heavy-Lauf (siehe _detect_status_changes in
    dashboard_export.py)."""
    client.collection("fitness_status_baseline").document("latest").set(status_by_player)


def get_fitness_status_baseline(client: firestore.Client) -> dict[str, int]:
    """Leeres Dict beim allerersten Lauf (Cold Start, noch kein Dokument
    vorhanden) - _detect_status_changes() behandelt das korrekt (kein
    Vorwert fuer irgendeinen Spieler -> keine Events, dann wird die Baseline
    zum ersten Mal geschrieben)."""
    doc = client.collection("fitness_status_baseline").document("latest").get()
    return doc.to_dict() if doc.exists else {}
