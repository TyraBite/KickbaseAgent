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
`{date}_{player_id}`.
"""

from google.cloud import firestore

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
    neue Collection laut Spec). Doc-Id `{date}_{player_id}` macht Re-Laeufe
    desselben Tages idempotent, analog zur Dedup-Logik in
    market_predictor._save_prediction_log()."""
    docs = {f"{e['date']}_{e['player_id']}": e for e in entries}
    _write_in_batches(client, "ml_prediction_log", docs)
