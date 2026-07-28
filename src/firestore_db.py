"""Firestore-Persistenz fuer Kickbase-Snapshots - Firestore-Pendant zu
src/db.py (Phase 1 der Firestore-Migration, siehe
docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md).

Additiv zur bestehenden SQLite-DB (data/kickbase.db), kein Ersatz. Jede
replace_*/upsert_*-Funktion hat dieselbe Signatur (nimmt dieselben Row-Dicts
entgegen) wie ihr db.py-Pendant, schreibt aber in eine gleichnamige Firestore-
Collection statt in eine SQLite-Tabelle. Mehrzeilige Writes nutzen Firestore-
WriteBatch (max. 500 Operationen/Batch - siehe _write_in_batches).

Dokument-Id-Konvention (laut Spec): `{fetched_at}_{player_id}` bzw.
`{fetched_at}_{user_id}` fuer Tabellen mit mehreren Zeilen/Tag, nur
`{fetched_at}` wenn es maximal eine Zeile pro Tag gibt (season_context,
own_budget_history). `ml_prediction_log` (neue Collection, kein SQLite-
Pendant - dort liegt die Historie in data/ml_prediction_log.jsonl) nutzt
`{date}_{player_id}_{model_type}` (seit Phase 4: beide Modell-Kandidaten
werden taeglich geloggt, nicht nur der Tagessieger).
"""

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

MAX_BATCH_OPS = 500


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


def replace_own_squad(client: firestore.Client, fetched_at: str, players: list[dict]) -> None:
    docs = {f"{fetched_at}_{p['player_id']}": {**p, "fetched_at": fetched_at} for p in players}
    _write_in_batches(client, "own_squad", docs)


def replace_market_listings(client: firestore.Client, fetched_at: str, listings: list[dict]) -> None:
    docs = {
        f"{fetched_at}_{listing['player_id']}": {**listing, "fetched_at": fetched_at}
        for listing in listings
    }
    _write_in_batches(client, "market_listings", docs)


def replace_league_ranking(client: firestore.Client, fetched_at: str, rows: list[dict]) -> None:
    docs = {f"{fetched_at}_{r['user_id']}": {**r, "fetched_at": fetched_at} for r in rows}
    _write_in_batches(client, "league_ranking", docs)


def upsert_own_budget(
    client: firestore.Client, fetched_at: str, user_id: str | None, budget: float | None
) -> None:
    client.collection("own_budget_history").document(fetched_at).set(
        {"fetched_at": fetched_at, "user_id": user_id, "budget": budget}
    )


def upsert_season_context(client: firestore.Client, fetched_at: str, context: dict) -> None:
    client.collection("season_context").document(fetched_at).set({**context, "fetched_at": fetched_at})


def replace_manager_budgets(client: firestore.Client, fetched_at: str, rows: list[dict]) -> None:
    docs = {f"{fetched_at}_{r['user_id']}": {**r, "fetched_at": fetched_at} for r in rows}
    _write_in_batches(client, "manager_budgets", docs)


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


def get_wunschkader(client: firestore.Client) -> dict | None:
    """Liest den kompletten Wunschkader-Datensatz (targets/sell_list/
    markup_rules/login_bonus/formation/season_start als EIN Dokument,
    ehemals data/wunschkader.json). None falls noch kein Dokument existiert
    (vor der einmaligen Migration)."""
    doc = client.collection("wunschkader").document("current").get()
    return doc.to_dict() if doc.exists else None


def upsert_wunschkader(client: firestore.Client, data: dict) -> None:
    """Ueberschreibt den kompletten Wunschkader-Datensatz. Aktuell nur aus
    Tests/einmaligen Ad-hoc-Migrationen aufgerufen - der laufende
    Schreibpfad ist der Browser (Client-SDK, setDoc mit merge:true auf nur
    targets), nicht diese Admin-SDK-Funktion."""
    client.collection("wunschkader").document("current").set(data)
