# Fitness-Historie (Sammel-Pipeline + ML-Integration) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jeden Statuswechsel (fit/Verletzt/Angeschlagen/Im Aufbau) aller ~450 Kandidatenpool-Spieler ab jetzt in Firestore protokollieren, per Read-Pfad zurücklesen und als zwei neue Features in die tägliche ML-Marktwertprognose (`market_predictor.py`) einbauen.

**Architecture:** Diff-basiert (kein voller Snapshot), 1×/Tag im Heavy-Cron (`dashboard_export.py::export()`), gegen die players-Map des vorherigen Firestore-Snapshots. Neue Collection `fitness_history_log` (idempotenter Doc-Key `{date}_{player_id}`). `market_predictor.py`s Corpus-Aufbau ist komplett unabhängig vom Dashboard-Snapshot (holt Kickbase-Daten pro Spieler live) — die Fitness-Events werden zusätzlich einmal pro Lauf aus Firestore gelesen und pro Spieler an den bestehenden `pd.merge_asof`-Merge-Punkt angehängt.

**Tech Stack:** Python, Firestore (`google-cloud-firestore`), pandas.

## Global Constraints

- Kein neuer Kickbase-API-Call — `fetch_all_players()` läuft bereits 1×/Tag im Heavy-Cron.
- Diff läuft NUR im Heavy-Zweig (`all_players is not None`), 1×/Tag, für alle Spieler gleich — keine feinere Diff-Kadenz für den eigenen Kader.
- Doc-Id `{date}_{player_id}` — idempotent, ein erneuter Lauf am selben Tag überschreibt statt zu duplizieren.
- Kein Pointer/Range-Filter nötig (Collection bleibt klein, nur echte Deltas).
- Kein Backfill möglich (Kickbase liefert keine Vergangenheit) — Cold-Start-Limitation ist akzeptiert, kein Sonderfall im Code.
- Feature-Kodierung (`days_since_last_status_change`, `status_change_count_90d`) ist eine Vermutung ohne echte Daten — falls sie sich später als nutzlos erweist: `FEATURES`-Liste anpassen (Toggle), kein Neubau.
- TDD durchgehend: Test zuerst, dann Implementierung. Backend-Verifikation nach jedem Task: `python3 -m unittest discover -s tests`.
- Aus jedem Task: `git add` nur die in diesem Task geänderten Dateien, dann committen (Push erlaubt, wenn Tests grün — bestehende Projekt-Policy).

---

## Task 1: Firestore-Persistenz für `fitness_history_log` (Write + Read)

**Files:**
- Modify: `src/firestore_db.py`
- Test: `tests/test_firestore_db.py`

**Interfaces:**
- Produces: `firestore_db.upsert_fitness_history_entries(client: firestore.Client, entries: list[dict]) -> None`, `firestore_db.get_fitness_history(client: firestore.Client) -> list[dict]`. Jedes Entry-Dict hat die Felder `player_id: str`, `date: str` (YYYY-MM-DD), `from_status_code: int`, `to_status_code: int`, `recorded_at: str` (ISO-Timestamp).

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_firestore_db.py`, am Ende der Datei (nach `GetBidPremiumHistoryTests`) einfügen:

```python
class UpsertFitnessHistoryEntriesTests(unittest.TestCase):
    def test_writes_docs_keyed_by_date_and_player_id(self):
        client = MagicMock()
        entries = [
            {"player_id": "p1", "date": "2026-07-31", "from_status_code": 0, "to_status_code": 1, "recorded_at": "2026-07-31T21:07:00+00:00"},
            {"player_id": "p2", "date": "2026-07-31", "from_status_code": 2, "to_status_code": 0, "recorded_at": "2026-07-31T21:07:00+00:00"},
        ]

        firestore_db.upsert_fitness_history_entries(client, entries)

        client.collection.assert_any_call("fitness_history_log")
        self.assertEqual(_doc_ids(client), ["2026-07-31_p1", "2026-07-31_p2"])
        batch = client.batch.return_value
        batch.commit.assert_called_once()

    def test_empty_entries_writes_nothing(self):
        client = MagicMock()
        firestore_db.upsert_fitness_history_entries(client, [])
        client.batch.assert_not_called()


class GetFitnessHistoryTests(unittest.TestCase):
    def test_returns_all_docs_as_dicts(self):
        client = MagicMock()
        doc1, doc2 = MagicMock(), MagicMock()
        doc1.to_dict.return_value = {"player_id": "p1", "date": "2026-07-31"}
        doc2.to_dict.return_value = {"player_id": "p2", "date": "2026-07-31"}
        client.collection.return_value.stream.return_value = [doc1, doc2]

        result = firestore_db.get_fitness_history(client)

        client.collection.assert_any_call("fitness_history_log")
        self.assertEqual(result, [{"player_id": "p1", "date": "2026-07-31"}, {"player_id": "p2", "date": "2026-07-31"}])
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_firestore_db.UpsertFitnessHistoryEntriesTests tests.test_firestore_db.GetFitnessHistoryTests -v`
Expected: FAIL mit `AttributeError: module 'src.firestore_db' has no attribute 'upsert_fitness_history_entries'`

- [ ] **Step 3: Implementierung**

In `src/firestore_db.py`, am Ende der Datei (nach `get_unsold_log`) einfügen:

```python
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
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_firestore_db -v`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/firestore_db.py tests/test_firestore_db.py
git commit -m "firestore_db: Write/Read fuer fitness_history_log ergaenzt"
```

---

## Task 2: Diff-Funktion `_detect_status_changes()`

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py`

**Interfaces:**
- Consumes: nichts aus anderen Tasks.
- Produces: `_detect_status_changes(previous_players: dict[str, dict], all_players: list[dict]) -> list[dict]`. Rückgabe-Dicts haben `player_id`, `from_status_code`, `to_status_code` (kein `date`/`recorded_at` — die kommen erst beim Aufrufer in Task 3 dazu).

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_dashboard_export.py`, den Import am Dateikopf erweitern:

```python
from src.dashboard_export import (
    _assemble_snapshot,
    _build_ligaanalyse,
    _build_players_map,
    _build_transfermarkt_listings,
    _build_wunschkader_targets,
    _detect_status_changes,
    _finalize_firestore_write,
    _load_wunschkader,
    _resolve_heavy_data,
    _resolve_is_light,
    export,
)
```

Nach der `BuildPlayersMapTests`-Klasse (vor `BuildLigaanalyseTests`) einfügen:

```python
class DetectStatusChangesTests(unittest.TestCase):
    def test_no_change_returns_empty_list(self):
        previous = {"p1": {"player_id": "p1", "status_code": 0}}
        all_players = [{"player_id": "p1", "status_code": 0}]
        self.assertEqual(_detect_status_changes(previous, all_players), [])

    def test_one_change_returns_one_event_with_correct_codes(self):
        previous = {"p1": {"player_id": "p1", "status_code": 0}}
        all_players = [{"player_id": "p1", "status_code": 1}]
        result = _detect_status_changes(previous, all_players)
        self.assertEqual(result, [{"player_id": "p1", "from_status_code": 0, "to_status_code": 1}])

    def test_mixed_players_only_changed_ones_become_events(self):
        previous = {
            "p1": {"player_id": "p1", "status_code": 0},
            "p2": {"player_id": "p2", "status_code": 1},
        }
        all_players = [
            {"player_id": "p1", "status_code": 0},
            {"player_id": "p2", "status_code": 0},
        ]
        result = _detect_status_changes(previous, all_players)
        self.assertEqual(result, [{"player_id": "p2", "from_status_code": 1, "to_status_code": 0}])

    def test_player_without_prior_snapshot_is_skipped(self):
        result = _detect_status_changes({}, [{"player_id": "p_new", "status_code": 1}])
        self.assertEqual(result, [])

    def test_player_missing_from_all_players_causes_no_crash(self):
        previous = {"p1": {"player_id": "p1", "status_code": 0}, "p2": {"player_id": "p2", "status_code": 0}}
        result = _detect_status_changes(previous, [{"player_id": "p1", "status_code": 0}])
        self.assertEqual(result, [])
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_dashboard_export.DetectStatusChangesTests -v`
Expected: FAIL (ImportError: cannot import name `_detect_status_changes`)

- [ ] **Step 3: Implementierung**

In `src/dashboard_export.py`, direkt nach der `_build_players_map()`-Funktion (vor `_build_transfermarkt_listings`) einfügen:

```python
def _detect_status_changes(previous_players: dict[str, dict], all_players: list[dict]) -> list[dict]:
    """Reine Diff-Funktion: vergleicht status_code je Spieler zwischen dem
    vorherigen Firestore-Snapshot (previous_players) und den frisch
    gefetchten all_players (Heavy-Cron, 1x/Tag, siehe
    player_valuation.fetch_all_players). Liefert ein Event-Dict pro
    tatsaechlichem Wechsel - Rohbasis fuer fitness_history_log (siehe
    firestore_db.upsert_fitness_history_entries). Spieler ohne Vorstand
    (neu im Pool) oder die aus all_players verschwunden sind werden
    uebersprungen, kein Crash."""
    changes = []
    for row in all_players:
        pid = row.get("player_id")
        if not pid or pid not in previous_players:
            continue
        old_status = previous_players[pid].get("status_code")
        new_status = row.get("status_code")
        if old_status is None or new_status is None or old_status == new_status:
            continue
        changes.append({
            "player_id": pid,
            "from_status_code": old_status,
            "to_status_code": new_status,
        })
    return changes
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_dashboard_export -v`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: reine Diff-Funktion _detect_status_changes() ergaenzt"
```

---

## Task 3: In `export()` verdrahten (Heavy-Cron schreibt Fitness-Events)

**Files:**
- Modify: `src/dashboard_export.py`
- Test: `tests/test_dashboard_export.py`

**Interfaces:**
- Consumes: `firestore_db.upsert_fitness_history_entries` (Task 1), `_detect_status_changes` (Task 2).
- Produces: nichts Neues für spätere Tasks (Task 4/5 sind unabhängig, in `market_predictor.py`).

**Wichtiger Fund (vor diesem Task nicht bekannt):** `export()` lädt `cached_snapshot` bisher NUR wenn `DASHBOARD_MODE == "light"` (`src/dashboard_export.py`, in `export()`, ca. Zeile 407-411:
```python
    mode = os.environ.get("DASHBOARD_MODE")
    cached_snapshot = None
    if mode == "light" and os.environ.get("FIRESTORE_ENABLED"):
        cached_snapshot = firestore_db.get_dashboard_snapshot(firestore_db.connect())
    is_light = _resolve_is_light(mode, cached_snapshot)
```
Im Heavy-Cron (`dashboard-marktwerte.yml` setzt `DASHBOARD_MODE` gar nicht) bleibt `cached_snapshot` deshalb `None` - der vorherige Snapshot (und damit die alten `status_code`-Werte) ist dort bisher NICHT verfuegbar. Dieser Task aendert die Bedingung so, dass `cached_snapshot` bei aktiviertem Firestore IMMER geladen wird, unabhaengig vom Modus - `_resolve_is_light()` haengt weiterhin ausschliesslich an `mode == "light"` (siehe deren Code, `dashboard_export.py:236-250`), diese Aenderung veraendert `is_light` NICHT, nur die Verfuegbarkeit von `cached_snapshot` im Heavy-Zweig. Kosten: ein zusaetzlicher Firestore-Dokument-Read (`dashboard_snapshot/latest`, EIN Dokument) pro Heavy-Lauf (1x/Tag) - vernachlaessigbar.

- [ ] **Step 1: Bestehenden Test anpassen (wird durch die kommende Aenderung sonst brechen)**

In `tests/test_dashboard_export.py`, Klasse `ExportActivityFeedGuardTests`, Methode `test_activity_feed_error_does_not_abort_export` - die `with`-Kette bekommt einen zusaetzlichen `patch(...)` fuer `firestore_db.get_dashboard_snapshot` (sonst wuerde die neue, ungemockte Firestore-Read-Bedingung im Heavy-Zweig auf dem MagicMock-Client crashen). Ersetze:

```python
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
```

durch:

```python
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.firestore_db.get_dashboard_snapshot", return_value=None
        ), patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
```

- [ ] **Step 2: Diesen Test isoliert laufen lassen, Erfolg bestätigen (Regressions-Baseline vor der eigentlichen Aenderung)**

Run: `python3 -m unittest tests.test_dashboard_export.ExportActivityFeedGuardTests -v`
Expected: PASS (Verhalten unveraendert, nur die Mock-Kette ist jetzt vollstaendig)

- [ ] **Step 3: Neue Failing Tests fuer die Fitness-Verdrahtung schreiben**

Im selben File, nach `ExportActivityFeedGuardTests` einfügen:

```python
class ExportWritesFitnessHistoryOnStatusChangeTests(unittest.TestCase):
    def _run_export_with(self, cached_snapshot, fresh_all_players):
        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ), patch("src.dashboard_export.login", return_value=("tok", {}, [{"id": "l1"}])), patch(
            "src.dashboard_export.get_me", return_value={"cpi": "1"}
        ), patch("src.dashboard_export.fetcher.run", return_value="2026-07-31"), patch(
            "src.dashboard_export._load_snapshot", return_value=([], [], [], [])
        ), patch("src.dashboard_export.firestore_db.connect"), patch(
            "src.dashboard_export.firestore_db.upsert_dashboard_snapshot"
        ), patch(
            "src.dashboard_export.firestore_db.get_dashboard_snapshot", return_value=cached_snapshot
        ), patch(
            "src.dashboard_export.firestore_db.upsert_fitness_history_entries"
        ) as mock_upsert_fitness, patch(
            "src.dashboard_export.get_activities_feed", side_effect=KickbaseError("API down")
        ), patch("src.dashboard_export._load_wunschkader", return_value=None
        ), patch("src.dashboard_export._build_ligaanalyse", return_value={"rows": [], "position_need": {}}
        ), patch("src.dashboard_export.player_valuation.fetch_all_players", return_value=fresh_all_players
        ), patch("src.dashboard_export.market_predictor.predict_market_value_changes", return_value=None
        ), patch("src.dashboard_export.player_valuation.load_calibration", return_value=None):
            export()
        return mock_upsert_fitness

    def test_status_change_in_heavy_mode_is_written_to_fitness_history(self):
        cached_snapshot = {"players": {"p1": {"player_id": "p1", "status_code": 0}}}
        fresh_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 1, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_fitness = self._run_export_with(cached_snapshot, fresh_all_players)

        mock_upsert_fitness.assert_called_once()
        written_entries = mock_upsert_fitness.call_args.args[1]
        self.assertEqual(len(written_entries), 1)
        self.assertEqual(written_entries[0]["player_id"], "p1")
        self.assertEqual(written_entries[0]["from_status_code"], 0)
        self.assertEqual(written_entries[0]["to_status_code"], 1)
        self.assertEqual(written_entries[0]["date"], "2026-07-31")

    def test_no_status_change_writes_nothing(self):
        cached_snapshot = {"players": {"p1": {"player_id": "p1", "status_code": 0}}}
        unchanged_all_players = [
            {"player_id": "p1", "name": "Krauss", "position": "Sturm", "team_name": "Bremen",
             "status_code": 0, "starting_rank": 1, "market_value": 5_000_000, "average_points": 100},
        ]

        mock_upsert_fitness = self._run_export_with(cached_snapshot, unchanged_all_players)

        mock_upsert_fitness.assert_not_called()
```

- [ ] **Step 4: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_dashboard_export.ExportWritesFitnessHistoryOnStatusChangeTests -v`
Expected: FAIL (`mock_upsert_fitness.assert_called_once()` -> nie aufgerufen, da die Verdrahtung noch fehlt)

- [ ] **Step 5: Implementierung - `cached_snapshot`-Bedingung + Diff-Aufruf**

In `src/dashboard_export.py`, Imports am Dateikopf: `import os` (Zeile ~45) wird um `import datetime` ergaenzt (alphabetisch davor):

```python
import datetime
import os
import sqlite3
import sys
```

In `export()`, ersetze:

```python
    mode = os.environ.get("DASHBOARD_MODE")
    cached_snapshot = None
    if mode == "light" and os.environ.get("FIRESTORE_ENABLED"):
        cached_snapshot = firestore_db.get_dashboard_snapshot(firestore_db.connect())
    is_light = _resolve_is_light(mode, cached_snapshot)
```

durch:

```python
    mode = os.environ.get("DASHBOARD_MODE")
    cached_snapshot = None
    if os.environ.get("FIRESTORE_ENABLED"):
        cached_snapshot = firestore_db.get_dashboard_snapshot(firestore_db.connect())
    is_light = _resolve_is_light(mode, cached_snapshot)
```

Weiter unten in `export()`, ersetze:

```python
    fs_client = firestore_db.connect() if os.environ.get("FIRESTORE_ENABLED") else None
    activity_feed_ok = True
```

durch:

```python
    fs_client = firestore_db.connect() if os.environ.get("FIRESTORE_ENABLED") else None
    if fs_client and heavy["all_players"] is not None:
        previous_players_for_fitness_diff = cached_snapshot.get("players", {}) if cached_snapshot else {}
        status_changes = _detect_status_changes(previous_players_for_fitness_diff, heavy["all_players"])
        if status_changes:
            fitness_entries = [
                {**change, "date": fetched_at, "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
                for change in status_changes
            ]
            firestore_db.upsert_fitness_history_entries(fs_client, fitness_entries)

    activity_feed_ok = True
```

- [ ] **Step 6: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS (kompletter Backend-Testlauf, nicht nur die neue Klasse - Regressionscheck)

- [ ] **Step 7: Commit**

```bash
git add src/dashboard_export.py tests/test_dashboard_export.py
git commit -m "dashboard_export: Fitness-Statuswechsel werden im Heavy-Cron nach fitness_history_log geschrieben"
```

---

## Task 4: Feature-Berechnung `_fitness_features_as_of()`

**Files:**
- Modify: `src/market_predictor.py`
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Consumes: nichts aus anderen Tasks (reine Funktion, unabhängig testbar).
- Produces: `_fitness_features_as_of(events: list[dict], as_of_date: datetime.date) -> dict` mit Keys `days_since_last_status_change: int`, `status_change_count_90d: int`. Konstanten `FITNESS_NO_HISTORY_DAYS = 9999`, `FITNESS_COUNT_WINDOW_DAYS = 90`. `events`-Elemente haben mindestens `{"date": "YYYY-MM-DD", ...}` (Format wie `fitness_history_log`-Dokumente, siehe Task 1) - Reihenfolge/Sortierung der Liste ist EGAL, die Funktion sortiert intern nicht, sondern filtert/vergleicht direkt.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_market_predictor.py`, Imports am Dateikopf ergänzen:

```python
import datetime
import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.market_predictor import (
    _summarize_from_daily,
    _build_daily_accuracy_updates,
    _realized_by_model_from_daily,
    _trend_from_daily,
    _load_local_prediction_log,
    _load_recent_prediction_log,
    _select_live_model,
    _infer_today,
    _performance_frame,
    _fitness_features_as_of,
    FITNESS_NO_HISTORY_DAYS,
)
from src.market_predictor import backfill_prediction_log, _build_candidates
```

Nach der `PerformanceFrameMinutesAvgTests`-Klasse (am Ende der Datei) einfügen:

```python
class FitnessFeaturesAsOfTests(unittest.TestCase):
    def test_no_prior_event_returns_placeholder(self):
        result = _fitness_features_as_of([], datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], FITNESS_NO_HISTORY_DAYS)
        self.assertEqual(result["status_change_count_90d"], 0)

    def test_ignores_events_after_as_of_date(self):
        events = [{"date": "2026-08-01", "from_status_code": 0, "to_status_code": 1}]
        result = _fitness_features_as_of(events, datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], FITNESS_NO_HISTORY_DAYS)

    def test_one_event_returns_correct_days_since(self):
        events = [{"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1}]
        result = _fitness_features_as_of(events, datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 1)

    def test_multiple_events_only_within_window_counted(self):
        events = [
            {"date": "2026-01-01", "from_status_code": 0, "to_status_code": 1},
            {"date": "2026-07-01", "from_status_code": 1, "to_status_code": 0},
            {"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
        ]
        result = _fitness_features_as_of(events, datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 2)

    def test_event_exactly_90_days_before_is_excluded_boundary(self):
        as_of = datetime.date(2026, 7, 31)
        boundary_date = (as_of - datetime.timedelta(days=90)).isoformat()
        events = [{"date": boundary_date, "from_status_code": 0, "to_status_code": 1}]
        result = _fitness_features_as_of(events, as_of)
        self.assertEqual(result["status_change_count_90d"], 0)
        self.assertEqual(result["days_since_last_status_change"], 90)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_market_predictor.FitnessFeaturesAsOfTests -v`
Expected: FAIL (ImportError: cannot import name `_fitness_features_as_of`)

- [ ] **Step 3: Implementierung**

In `src/market_predictor.py`, nach der bestehenden Konstante `BACKTEST_MIN_TRAIN_ROWS = MIN_TRAINING_ROWS` (im Konstanten-Block, vor `_ABORT_FAILURE_SAMPLE`) einfügen:

```python
FITNESS_NO_HISTORY_DAYS = 9999  # Platzhalter: kein Fitness-Ereignis vor diesem Datum bekannt (Cold-Start oder Spieler nie im fitness_history_log)
FITNESS_COUNT_WINDOW_DAYS = 90
```

Direkt vor `_fetch_player_training_frame()` (nach `_performance_frame()`) einfügen:

```python
def _fitness_features_as_of(events: list[dict], as_of_date: datetime.date) -> dict:
    """events: EIN Spielers Eintraege aus fitness_history_log (jeweils
    {'date': 'YYYY-MM-DD', 'from_status_code': int, 'to_status_code': int}),
    Reihenfolge egal. as_of_date: das Datum der Trainings-/Prognose-Zeile.
    Nur Ereignisse mit event_date <= as_of_date fliessen ein - kein
    Lookahead in die Zukunft dieser Zeile. Siehe
    docs/superpowers/specs/2026-07-31-fitness-history-design.md,
    Abschnitt 'ML-Integration'."""
    relevant = [e for e in events if datetime.date.fromisoformat(e["date"]) <= as_of_date]
    if not relevant:
        return {"days_since_last_status_change": FITNESS_NO_HISTORY_DAYS, "status_change_count_90d": 0}
    last_date = max(datetime.date.fromisoformat(e["date"]) for e in relevant)
    days_since = (as_of_date - last_date).days
    cutoff = as_of_date - datetime.timedelta(days=FITNESS_COUNT_WINDOW_DAYS)
    count_90d = sum(1 for e in relevant if datetime.date.fromisoformat(e["date"]) > cutoff)
    return {"days_since_last_status_change": days_since, "status_change_count_90d": count_90d}
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_market_predictor -v`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: reine Feature-Funktion _fitness_features_as_of() ergaenzt"
```

---

## Task 5: Verdrahtung in den ML-Corpus + `FEATURES`

**Files:**
- Modify: `src/market_predictor.py`
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Consumes: `firestore_db.get_fitness_history` (Task 1), `_fitness_features_as_of`/`FITNESS_NO_HISTORY_DAYS` (Task 4).
- Produces: `_load_fitness_events_by_player() -> dict[str, list[dict]]`. Neuer Parameter `fitness_events_by_player: dict[str, list[dict]]` bei `_fetch_player_training_frame()` (letzter Positionsparameter, nach `team_id`) und `_build_corpus()` (letzter Positionsparameter, nach `competition_id`). `FEATURES` enthält zwei neue Einträge `"days_since_last_status_change"`, `"status_change_count_90d"`.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_market_predictor.py`, Imports ergänzen (in der bestehenden `from src.market_predictor import (...)`-Klammer aus Task 4 zusätzlich `_fetch_player_training_frame`, `_load_fitness_events_by_player` aufnehmen):

```python
from src.market_predictor import (
    _summarize_from_daily,
    _build_daily_accuracy_updates,
    _realized_by_model_from_daily,
    _trend_from_daily,
    _load_local_prediction_log,
    _load_recent_prediction_log,
    _select_live_model,
    _infer_today,
    _performance_frame,
    _fitness_features_as_of,
    _fetch_player_training_frame,
    _load_fitness_events_by_player,
    FITNESS_NO_HISTORY_DAYS,
)
```

Am Ende der Datei (nach `FitnessFeaturesAsOfTests`, aus Task 4) einfügen:

```python
class LoadFitnessEventsByPlayerTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_fitness_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_entries_by_player_id(self, mock_connect, mock_get):
        mock_get.return_value = [
            {"player_id": "p1", "date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
            {"player_id": "p1", "date": "2026-07-25", "from_status_code": 1, "to_status_code": 0},
            {"player_id": "p2", "date": "2026-07-22", "from_status_code": 0, "to_status_code": 2},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_fitness_events_by_player()
        self.assertEqual(len(result["p1"]), 2)
        self.assertEqual(len(result["p2"]), 1)

    def test_returns_empty_dict_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_load_fitness_events_by_player(), {})

    @patch("src.market_predictor.firestore_db.get_fitness_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_returns_empty_dict_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            self.assertEqual(_load_fitness_events_by_player(), {})


class FetchPlayerTrainingFrameFitnessColumnsTests(unittest.TestCase):
    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_adds_fitness_columns_computed_as_of_each_row_date(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-07-31"]),
            "mv": [10_000_000, 10_200_000],
        })
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])
        fitness_events_by_player = {
            "p1": [{"player_id": "p1", "date": "2026-07-20", "from_status_code": 0, "to_status_code": 1}],
        }

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", fitness_events_by_player)

        self.assertEqual(list(result["days_since_last_status_change"]), [5, 11])
        self.assertEqual(list(result["status_change_count_90d"]), [1, 1])

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_fitness_events_gets_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-07-31"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {})

        self.assertEqual(list(result["days_since_last_status_change"]), [FITNESS_NO_HISTORY_DAYS])
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_market_predictor.LoadFitnessEventsByPlayerTests tests.test_market_predictor.FetchPlayerTrainingFrameFitnessColumnsTests -v`
Expected: FAIL (ImportError bzw. `TypeError: _fetch_player_training_frame() missing 1 required positional argument`)

- [ ] **Step 3: Implementierung - Imports + `_load_fitness_events_by_player()`**

In `src/market_predictor.py`, Import-Block am Dateikopf: `from collections import defaultdict` ergänzen (vor `import concurrent.futures`):

```python
from collections import defaultdict
import concurrent.futures
import datetime
import json
import os
import sys
from pathlib import Path
```

Direkt nach `_max_workers()` (vor `_fetch_competition_player_ids`) einfügen:

```python
def _load_fitness_events_by_player() -> dict[str, list[dict]]:
    """Liest fitness_history_log (siehe firestore_db.get_fitness_history)
    einmal pro Lauf und gruppiert nach player_id - Basis fuer
    _fitness_features_as_of() in _fetch_player_training_frame(). Leeres
    Dict bei deaktiviertem Firestore oder Lesefehler (gleiches
    Resilienz-Muster wie _load_recent_prediction_log) - jeder Spieler
    bekommt dann ueberall den Cold-Start-Platzhalter, kein Crash."""
    events_by_player: dict[str, list[dict]] = defaultdict(list)
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            for entry in firestore_db.get_fitness_history(firestore_db.connect()):
                events_by_player[entry["player_id"]].append(entry)
        except Exception as exc:
            print(f"Warnung: fitness_history_log-Lesezugriff fehlgeschlagen: {exc}", file=sys.stderr)
            return {}
    return dict(events_by_player)
```

- [ ] **Step 4: Implementierung - `_fetch_player_training_frame()` erweitern**

Signatur ändern von:

```python
def _fetch_player_training_frame(
    token: str, league_id: str, competition_id: str, player_id: str, team_id: str
) -> pd.DataFrame | None:
```

zu:

```python
def _fetch_player_training_frame(
    token: str, league_id: str, competition_id: str, player_id: str, team_id: str,
    fitness_events_by_player: dict[str, list[dict]],
) -> pd.DataFrame | None:
```

Die letzten beiden Zeilen der Funktion (`merged["player_id"] = player_id` / `merged["team_id"] = team_id` / `return merged`) ersetzen von:

```python
    merged["player_id"] = player_id
    merged["team_id"] = team_id
    return merged
```

zu:

```python
    merged["player_id"] = player_id
    merged["team_id"] = team_id

    events = fitness_events_by_player.get(player_id, [])
    fitness_features = merged["date"].apply(lambda ts: _fitness_features_as_of(events, ts.date()))
    merged["days_since_last_status_change"] = fitness_features.apply(lambda f: f["days_since_last_status_change"])
    merged["status_change_count_90d"] = fitness_features.apply(lambda f: f["status_change_count_90d"])

    return merged
```

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen (Zwischenstand)**

Run: `python3 -m unittest tests.test_market_predictor.LoadFitnessEventsByPlayerTests tests.test_market_predictor.FetchPlayerTrainingFrameFitnessColumnsTests -v`
Expected: alle PASS

- [ ] **Step 6: `_build_corpus()` + `predict_market_value_changes()` + `FEATURES` verdrahten**

`_build_corpus()`-Signatur ändern von:

```python
def _build_corpus(token: str, league_id: str, competition_id: str) -> pd.DataFrame:
```

zu:

```python
def _build_corpus(
    token: str, league_id: str, competition_id: str, fitness_events_by_player: dict[str, list[dict]]
) -> pd.DataFrame:
```

Im Funktionskörper, die `executor.submit(...)`-Zeile ändern von:

```python
            executor.submit(_fetch_player_training_frame, token, league_id, competition_id, pid, tid): pid
```

zu:

```python
            executor.submit(_fetch_player_training_frame, token, league_id, competition_id, pid, tid, fitness_events_by_player): pid
```

In `FEATURES` (Konstanten-Block am Dateikopf), ergänzen von:

```python
FEATURES = [
    "p", "mv", "days_to_next",
    "mv_change_1d", "mv_trend_1d",
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence",
]
```

zu:

```python
FEATURES = [
    "p", "mv", "days_to_next",
    "mv_change_1d", "mv_trend_1d",
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence",
    "days_since_last_status_change", "status_change_count_90d",
]
```

In `predict_market_value_changes()`, ersetze:

```python
        corpus = _build_corpus(token, league_id, competition_id)
```

durch:

```python
        fitness_events_by_player = _load_fitness_events_by_player()
        corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player)
```

- [ ] **Step 7: Kompletten Backend-Testlauf verifizieren**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS (inkl. `BuildCandidatesTests`, `_engineer_features`-nahe Tests - die neuen `FEATURES`-Einträge dürfen keinen bestehenden Test brechen, da `_fitness_features_as_of()` nie `NaN` liefert und `_engineer_features()`s `dropna(subset=[...])`/`fillna({...})`-Aufrufe diese beiden neuen Spalten unverändert durchreichen)

- [ ] **Step 8: Live-Smoke-Test (Sandbox hat echten Kickbase/Firestore-Zugriff, siehe HANDOFF.md)**

Run: `python3 -m src.market_predictor`
Expected: läuft ohne Absturz durch, druckt eine Prognose-Zusammenfassung. Prüfen: taucht `days_since_last_status_change`/`status_change_count_90d` sinnvoll auf (z.B. per kurzem Debug-Print der `FEATURES`-Spalten von `today_df` vor dem eigentlichen Lauf, danach wieder entfernen) - da `fitness_history_log` zu diesem Zeitpunkt noch leer ist, MUSS jeder Wert `FITNESS_NO_HISTORY_DAYS`/`0` sein (Cold-Start, siehe Spec) - das ist der erwartete, korrekte Zustand, kein Fehler.

- [ ] **Step 9: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: Fitness-Historie als zwei neue Features (days_since_last_status_change, status_change_count_90d) eingebaut"
```

---

## Verification (gesamt)

- [ ] `python3 -m unittest discover -s tests` grün nach jedem Task.
- [ ] Nach Task 5: `python3 -m src.market_predictor` einmal live laufen lassen (Sandbox hat Zugriff) - bestätigt, dass die neue Verdrahtung im echten Pipeline-Lauf nicht crasht.
- [ ] Push nach jedem Task erlaubt, wenn Tests grün (bestehende Projekt-Policy, siehe [[project_kickbaseagent_git_workflow]] falls Memory verfügbar).
- [ ] Nach Abschluss aller 5 Tasks: HANDOFF.md aktualisieren (neue Collection, Cold-Start-Status, Hinweis dass eine Auswertung erst in einigen Wochen sinnvoll möglich ist).

## Self-Review

- **Spec-Abdeckung**: Sammel-Pipeline (Task 2+3), Read-Pfad (Task 1), ML-Integration (Task 4+5) - alle drei Spec-Abschnitte haben je einen Task-Block.
- **Kritischer Fund vor Task 3 eingearbeitet**: die Spec-Annahme "`cached_snapshot` ist in `export()` bereits unabhängig von `is_light` verfügbar" war unvollständig geprüft - tatsächlich wird sie nur bei `mode == "light"` geladen. Task 3 korrigiert das explizit als Teil der Implementierung (nicht als nachträglicher Bugfix), inkl. Anpassung des einzigen dadurch betroffenen bestehenden Tests.
- **Platzhalter-Scan**: keine TBD/TODO, jeder Code-Block ist vollständig, jeder Testschritt hat echten Code.
- **Typ-Konsistenz**: `_detect_status_changes()` (Task 2) liefert Dicts ohne `date`/`recorded_at` - Task 3 ergänzt diese explizit beim Zusammenbau von `fitness_entries`, keine Diskrepanz. `_fitness_features_as_of()` (Task 4) und dessen Nutzung in `_fetch_player_training_frame()` (Task 5) nutzen exakt dieselben Dict-Keys (`days_since_last_status_change`, `status_change_count_90d`).
- **YAGNI-Entscheidung dokumentiert**: `_build_corpus()`/`predict_market_value_changes()` selbst sind (wie vor diesem Plan auch schon) nicht direkt unit-getestet - das war schon vorher Konvention in diesem Modul (kein Test ruft sie auf), Task 5 fügt stattdessen einen Live-Smoke-Test hinzu statt eine aufwendige Mock-Kette für einen threadenden Corpus-Aufbau zu bauen.
