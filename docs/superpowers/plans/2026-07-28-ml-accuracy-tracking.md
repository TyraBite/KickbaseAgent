# ML-Genauigkeit tracken + datengetriebene Modellwahl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ml_prediction_log` von "nur Tagessieger, nur lokale Datei" auf
"beide Modelle, Firestore-Historie" umstellen, die Live-Modellwahl auf
echte Trailing-30d-Genauigkeit umstellen (mit Fallback), einen einmaligen
Backfill der letzten ~90 Tage schreiben, und einen neuen Dashboard-Tab
"ML-Genauigkeit" mit Kopf-an-Kopf-Vergleich + Trend-Chart bauen.

**Architecture:** `market_predictor.py` behaelt die gesamte ML-Logik
(Training, Auswertung, Trend-Berechnung) - `dashboard_export.py` liest nur
das fertige Ergebnis-Dict, baut nichts selbst nach (vermeidet einen
zweiten, teuren Kickbase-Historie-Fetch nur fuer den Trend-Chart, da
`market_predictor.py` den vollen Corpus/mv_lookup fuer den taeglichen Lauf
ohnehin schon baut). `firestore_db.py` bekommt ein neues Doc-Id-Schema
(`{date}_{player_id}_{model_type}`) und eine neue Lesefunktion.

**Tech Stack:** Python (sklearn, pandas), Firestore, vanilla-JS-Chart in
`index.html` (kein Chart-Framework im Projekt - `dataviz`-Skill wird in
Task 7 vor dem eigentlichen Chart-Code geladen).

## Global Constraints

- Doc-Id-Schema-Aenderung fuer `ml_prediction_log`: alte Eintraege aus
  dieser Session (Testdaten, altes Schema ohne `model_type`) bleiben
  bewusst liegen - keine Migration, werden von neuer Auswertungslogik
  automatisch uebersprungen (kein `model_type`-Feld = ignoriert).
- Lokale `data/ml_prediction_log.jsonl` bleibt als Offline-/Lokal-Dev-
  Fallback bestehen (gleiches `FIRESTORE_ENABLED`-Gating-Pattern wie
  ueberall sonst im Projekt) - kein Ersatz, additiv.
- Firestore-Lesefehler duerfen die Pipeline nie crashen (bestehendes
  Projekt-Prinzip) - Fallback auf lokale Datei bei Exception.
- **Git-Workflow**: Commits lokal lassen, NICHT pushen, keine Feature-
  Branches - User pusht selbst (Ruleset `NeverPushOnMain`, siehe
  [[project_kickbaseagent_git_workflow]]-Memory).
- Backfill-Utility bleibt dauerhaft im Code (User-Entscheidung), kein
  Wegwerf-Skript.

---

### Task 1: `firestore_db.py` — neues Doc-Id-Schema + Lesefunktion

**Files:**
- Modify: `src/firestore_db.py` (Docstring-Kopf, `upsert_prediction_log_entries`, neue `get_prediction_log_entries`)
- Test: `tests/test_firestore_db.py`

**Interfaces:**
- Produziert: `get_prediction_log_entries(client: firestore.Client) -> list[dict]` —
  von Task 2 (`market_predictor.py::_load_prediction_log`) genutzt.

- [ ] **Schritt 1: Docstring-Kopf aktualisieren (Zeilen 11-16, Doc-Id-Konvention)**

Von:
```python
Dokument-Id-Konvention (laut Spec): `{fetched_at}_{player_id}` bzw.
`{fetched_at}_{user_id}` fuer Tabellen mit mehreren Zeilen/Tag, nur
`{fetched_at}` wenn es maximal eine Zeile pro Tag gibt (season_context,
own_budget_history). `ml_prediction_log` (neue Collection, kein SQLite-
Pendant - dort liegt die Historie in data/ml_prediction_log.jsonl) nutzt
`{date}_{player_id}`.
```
Zu:
```python
Dokument-Id-Konvention (laut Spec): `{fetched_at}_{player_id}` bzw.
`{fetched_at}_{user_id}` fuer Tabellen mit mehreren Zeilen/Tag, nur
`{fetched_at}` wenn es maximal eine Zeile pro Tag gibt (season_context,
own_budget_history). `ml_prediction_log` (neue Collection, kein SQLite-
Pendant - dort liegt die Historie in data/ml_prediction_log.jsonl) nutzt
`{date}_{player_id}_{model_type}` (seit Phase 4: beide Modell-Kandidaten
werden taeglich geloggt, nicht nur der Tagessieger).
```

- [ ] **Schritt 2: `upsert_prediction_log_entries` Doc-Id anpassen**

Von:
```python
def upsert_prediction_log_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Firestore-Pendant zu data/ml_prediction_log.jsonl (kein SQLite-Original -
    neue Collection laut Spec). Doc-Id `{date}_{player_id}` macht Re-Laeufe
    desselben Tages idempotent, analog zur Dedup-Logik in
    market_predictor._save_prediction_log()."""
    docs = {f"{e['date']}_{e['player_id']}": e for e in entries}
    _write_in_batches(client, "ml_prediction_log", docs)
```
Zu:
```python
def upsert_prediction_log_entries(client: firestore.Client, entries: list[dict]) -> None:
    """Firestore-Pendant zu data/ml_prediction_log.jsonl (kein SQLite-Original -
    neue Collection laut Spec). Doc-Id `{date}_{player_id}_{model_type}` macht
    Re-Laeufe desselben Tages idempotent (pro Modell-Kandidat), analog zur
    Dedup-Logik in market_predictor._save_prediction_log()."""
    docs = {f"{e['date']}_{e['player_id']}_{e['model_type']}": e for e in entries}
    _write_in_batches(client, "ml_prediction_log", docs)
```

- [ ] **Schritt 3: Neue Funktion `get_prediction_log_entries` (nach `upsert_prediction_log_entries`)**

```python
def get_prediction_log_entries(client: firestore.Client) -> list[dict]:
    """Liest die komplette ml_prediction_log-Collection - keine Datumsfilterung
    noetig, Datenmenge bleibt ueberschaubar (~450 Spieler x 2 Modelle x
    max. ~1 Jahr Trailing-Retention)."""
    return [doc.to_dict() for doc in client.collection("ml_prediction_log").stream()]
```

- [ ] **Schritt 4: Tests in `tests/test_firestore_db.py` (ans Ende anhaengen, gleiches MagicMock-Muster wie bestehende Klassen)**

```python
class GetPredictionLogEntriesTests(unittest.TestCase):
    def test_returns_all_documents_as_dicts(self):
        client = MagicMock()
        doc1, doc2 = MagicMock(), MagicMock()
        doc1.to_dict.return_value = {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}
        doc2.to_dict.return_value = {"date": "2026-07-27", "player_id": "p1", "model_type": "HistGradientBoosting", "predicted_delta": 90}
        client.collection.return_value.stream.return_value = [doc1, doc2]

        result = firestore_db.get_prediction_log_entries(client)

        client.collection.assert_any_call("ml_prediction_log")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["model_type"], "RandomForest")


class UpsertPredictionLogEntriesModelTypeDocIdTests(unittest.TestCase):
    def test_doc_id_includes_model_type(self):
        client = MagicMock()
        entries = [{"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}]

        firestore_db.upsert_prediction_log_entries(client, entries)

        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-27_p1_RandomForest", doc_ids)
```
(`_doc_ids`-Helper existiert schon oben in der Datei, siehe bestehende
`UpsertOwnBudgetTests`/`ReplaceOwnSquadTests` fuer das exakte Muster -
nicht neu schreiben.)

- [ ] **Schritt 5: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle bisherigen + die 2 neuen Tests gruen.

- [ ] **Schritt 6: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/firestore_db.py tests/test_firestore_db.py
git commit -m "Firestore: ml_prediction_log auf Modell-spezifisches Doc-Id-Schema umstellen"
```

---

### Task 2: `market_predictor.py` — beide Modelle trainieren+behalten, Firestore-Read

**Files:** Modify: `src/market_predictor.py`

**Interfaces:**
- Konsumiert: `firestore_db.get_prediction_log_entries` aus Task 1.
- Produziert: `_train_and_evaluate(history_df) -> tuple[dict[str, model], dict] | None`
  (GEAENDERTE Signatur — vorher `tuple[model, dict] | None`, jetzt gibt es
  ALLE trainierten Kandidaten zurueck, nicht nur den Gewinner). Von Task 3
  genutzt (`predict_market_value_changes` braucht beide Modelle, um beide
  Prognosen zu loggen).

- [ ] **Schritt 1: `_train_and_evaluate` umbauen (aktuell Zeilen 303-360) — behaelt BEIDE Modelle + BEIDE Metrik-Saetze**

Von (aktuell, kompletter Funktionskoerper ab der `candidates`-Schleife):
```python
    best_name, best_model, best_r2, best_pred = None, None, None, None
    for name, candidate in candidates.items():
        candidate.fit(x_train, y_train)
        y_pred = candidate.predict(x_test)
        r2 = r2_score(y_test, y_pred)
        if best_r2 is None or r2 > best_r2:
            best_name, best_model, best_r2, best_pred = name, candidate, r2, y_pred

    rmse = mean_squared_error(y_test, best_pred) ** 0.5
    mae = mean_absolute_error(y_test, best_pred)
    sign_accuracy = float(np.mean(np.sign(y_test) == np.sign(best_pred)) * 100)

    metrics = {
        "model_type": best_name,
        "rmse": round(rmse, 2),
        "mae": round(mae, 2),
        "r2": round(best_r2, 3),
        "sign_accuracy": round(sign_accuracy, 1),
        "train_rows": len(train),
        "test_rows": len(test),
    }
    return best_model, metrics
```
Zu:
```python
    models: dict[str, object] = {}
    per_model_metrics: dict[str, dict] = {}
    for name, candidate in candidates.items():
        candidate.fit(x_train, y_train)
        y_pred = candidate.predict(x_test)
        r2 = r2_score(y_test, y_pred)
        rmse = mean_squared_error(y_test, y_pred) ** 0.5
        mae = mean_absolute_error(y_test, y_pred)
        sign_accuracy = float(np.mean(np.sign(y_test) == np.sign(y_pred)) * 100)
        models[name] = candidate
        per_model_metrics[name] = {
            "rmse": round(rmse, 2),
            "mae": round(mae, 2),
            "r2": round(r2, 3),
            "sign_accuracy": round(sign_accuracy, 1),
        }

    best_name = max(per_model_metrics, key=lambda name: per_model_metrics[name]["r2"])
    metrics = {
        "model_type": best_name,
        **per_model_metrics[best_name],
        "train_rows": len(train),
        "test_rows": len(test),
        "per_model": per_model_metrics,
    }
    return models, metrics
```
Docstring der Funktion (aktuell Zeilen 304-310) entsprechend anpassen:
"Gibt (models, metrics) oder None zurueck" statt "(model, metrics)",
erwaehnen dass `models` ALLE trainierten Kandidaten enthaelt (Phase 4:
werden beide fuer die taegliche Prognose gebraucht, um beide zu loggen).

- [ ] **Schritt 2: `_load_prediction_log` um Firestore-Read erweitern (aktuell Zeilen 429-437)**

Von:
```python
def _load_prediction_log() -> list[dict]:
    if not PREDICTION_LOG_PATH.exists():
        return []
    entries = []
    for line in PREDICTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries
```
Zu:
```python
def _load_prediction_log() -> list[dict]:
    """Liest bei FIRESTORE_ENABLED aus Firestore (persistiert ueber CI-Laeufe
    hinweg, anders als die lokale Datei) - Firestore-Lesefehler faellt
    zurueck auf die lokale Datei statt die Pipeline zu crashen. Ohne
    FIRESTORE_ENABLED (lokaler Testlauf) bleibt alles wie bisher."""
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            return firestore_db.get_prediction_log_entries(firestore_db.connect())
        except Exception as exc:
            print(
                f"Warnung: ml_prediction_log-Lesezugriff fehlgeschlagen, nutze lokale Datei: {exc}",
                file=sys.stderr,
            )
    if not PREDICTION_LOG_PATH.exists():
        return []
    entries = []
    for line in PREDICTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries
```

- [ ] **Schritt 3: Neue Testdatei `tests/test_market_predictor.py` anlegen (existiert noch nicht)**

```python
import os
import unittest
from unittest.mock import MagicMock, patch

from src.market_predictor import _load_prediction_log


class LoadPredictionLogTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_reads_from_firestore_when_enabled(self, mock_connect, mock_get):
        mock_get.return_value = [{"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_prediction_log()
        self.assertEqual(result, mock_get.return_value)

    @patch("src.market_predictor.firestore_db.get_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_falls_back_to_local_file_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_prediction_log()  # lokale Datei existiert im Test-Repo nicht zwingend
        self.assertIsInstance(result, list)  # crasht nicht, degradiert auf leere/lokale Liste
```
(Patch-Pfade `src.market_predictor.firestore_db.*` matchen den Modul-Import
`from src import firestore_db` oben in der Datei.)

- [ ] **Schritt 4: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle gruen (bestehende `_train_and_evaluate`-Konsumenten in
`predict_market_value_changes` sind noch NICHT angepasst — das macht
Task 4, bis dahin bricht `predict_market_value_changes` nicht, da Python
erst zur Laufzeit auf die neue Tupel-Form trifft, nicht beim Import/Testlauf
dieser Tests, die nur `_load_prediction_log` isoliert testen. Ein echter
End-to-End-Lauf von `predict_market_value_changes()` findet planmaessig
erst in Task 8 statt, nach Task 4s Wiring).

- [ ] **Schritt 5: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: beide Modelle behalten, ml_prediction_log aus Firestore lesen"
```

---

### Task 3: `market_predictor.py` — Modell-spezifische Realwert-Auswertung + Live-Auswahl

**Files:** Modify: `src/market_predictor.py`

**Interfaces:**
- Konsumiert: `models: dict[str, model]` aus Task 2's `_train_and_evaluate`.
- Produziert: `_evaluate_realized_accuracy_by_model(log_entries, mv_lookup, today) -> dict[str, dict]`,
  `_select_live_model(realized_by_model, synthetic_winner) -> tuple[str, str]`.
  Von Task 4 (`predict_market_value_changes`-Verdrahtung) genutzt.

- [ ] **Schritt 1: `_evaluate_realized_accuracy` umbenennen + pro Modell auswerten (aktuell Zeilen 498-523)**

Von:
```python
def _evaluate_realized_accuracy(log_entries: list[dict], mv_lookup: dict, today: str) -> dict:
    """Prueft alle Log-Eintraege, fuer die inzwischen ein echtes Ergebnis
    bekannt ist (Datum vor 'today' UND Folgetag im Corpus vorhanden), gegen
    die tatsaechliche Wertaenderung - echte Tag-fuer-Tag-Genauigkeit statt
    nur des synthetischen Zeit-Splits aus _train_and_evaluate()."""
    evaluated = []
    for entry in log_entries:
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        evaluated.append(
            {
                "date": date,
                "sign_correct": np.sign(entry["predicted_delta"]) == np.sign(actual_delta),
                "abs_error": abs(entry["predicted_delta"] - actual_delta),
            }
        )
    return {
        f"realized_{days}d": _summarize_window(evaluated, today, days) for days in ACCURACY_WINDOWS_DAYS
    }
```
Zu:
```python
def _evaluate_realized_accuracy_by_model(log_entries: list[dict], mv_lookup: dict, today: str) -> dict[str, dict]:
    """Wie zuvor, aber getrennt pro model_type - ermoeglicht echten
    Kopf-an-Kopf-Vergleich ueber die Zeit statt nur 'der jeweilige
    Tagessieger, egal welches Modell das war'. Log-Eintraege ohne
    model_type (altes Schema, vor Phase 4) werden uebersprungen statt
    einen KeyError zu werfen - bewusst keine Migration noetig."""
    evaluated_by_model: dict[str, list[dict]] = {"RandomForest": [], "HistGradientBoosting": []}
    for entry in log_entries:
        model_type = entry.get("model_type")
        if model_type not in evaluated_by_model:
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        evaluated_by_model[model_type].append(
            {
                "date": date,
                "sign_correct": np.sign(entry["predicted_delta"]) == np.sign(actual_delta),
                "abs_error": abs(entry["predicted_delta"] - actual_delta),
            }
        )
    return {
        name: {f"realized_{days}d": _summarize_window(evaluated, today, days) for days in ACCURACY_WINDOWS_DAYS}
        for name, evaluated in evaluated_by_model.items()
    }
```

- [ ] **Schritt 2: Neue Konstante + `_select_live_model` (nach `ACCURACY_WINDOWS_DAYS`-Konstante bzw. nach `_evaluate_realized_accuracy_by_model`)**

Konstante (bei den anderen Konstanten, Zeile ~72):
```python
MIN_REALIZED_SAMPLES_FOR_SELECTION = 14
```

Neue Funktion:
```python
def _select_live_model(realized_by_model: dict[str, dict], synthetic_winner: str) -> tuple[str, str]:
    """Waehlt das Modell fuer die tatsaechliche Live-Prognose. Bevorzugt echte
    Trailing-30d-sign_accuracy sobald BEIDE Modelle genug Realdaten haben
    (MIN_REALIZED_SAMPLES_FOR_SELECTION), sonst Fallback auf den heutigen
    synthetischen Split (bisheriges Verhalten) - vermeidet eine Entscheidung
    auf Basis von 1-2 verrauschten Datenpunkten in der Kaltstart-Phase."""
    rf_window = realized_by_model.get("RandomForest", {}).get("realized_30d")
    hgb_window = realized_by_model.get("HistGradientBoosting", {}).get("realized_30d")
    if (
        rf_window and hgb_window
        and rf_window["n"] >= MIN_REALIZED_SAMPLES_FOR_SELECTION
        and hgb_window["n"] >= MIN_REALIZED_SAMPLES_FOR_SELECTION
    ):
        winner = "RandomForest" if rf_window["sign_accuracy"] >= hgb_window["sign_accuracy"] else "HistGradientBoosting"
        return winner, "realized_trailing_30d"
    return synthetic_winner, "synthetic_split_fallback"
```

- [ ] **Schritt 3: Tests in `tests/test_market_predictor.py` ergaenzen**

```python
from src.market_predictor import _select_live_model, _evaluate_realized_accuracy_by_model


class SelectLiveModelTests(unittest.TestCase):
    def test_falls_back_to_synthetic_when_not_enough_realized_samples(self):
        realized = {
            "RandomForest": {"realized_30d": {"n": 5, "sign_accuracy": 80.0, "mae": 100}},
            "HistGradientBoosting": {"realized_30d": {"n": 5, "sign_accuracy": 60.0, "mae": 100}},
        }
        name, reason = _select_live_model(realized, "HistGradientBoosting")
        self.assertEqual(name, "HistGradientBoosting")
        self.assertEqual(reason, "synthetic_split_fallback")

    def test_picks_better_realized_model_when_enough_samples(self):
        realized = {
            "RandomForest": {"realized_30d": {"n": 20, "sign_accuracy": 80.0, "mae": 100}},
            "HistGradientBoosting": {"realized_30d": {"n": 20, "sign_accuracy": 60.0, "mae": 100}},
        }
        name, reason = _select_live_model(realized, "HistGradientBoosting")
        self.assertEqual(name, "RandomForest")
        self.assertEqual(reason, "realized_trailing_30d")


class EvaluateRealizedAccuracyByModelTests(unittest.TestCase):
    def test_skips_entries_without_model_type(self):
        log_entries = [{"date": "2026-07-01", "player_id": "p1", "predicted_delta": 100}]  # altes Schema
        result = _evaluate_realized_accuracy_by_model(log_entries, {}, "2026-07-28")
        self.assertEqual(result["RandomForest"]["realized_7d"], None)
        self.assertEqual(result["HistGradientBoosting"]["realized_7d"], None)

    def test_separates_by_model_type(self):
        log_entries = [
            {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100},
            {"date": "2026-07-27", "player_id": "p1", "model_type": "HistGradientBoosting", "predicted_delta": -100},
        ]
        mv_lookup = {("p1", "2026-07-27"): 1000.0, ("p1", "2026-07-28"): 1200.0}
        result = _evaluate_realized_accuracy_by_model(log_entries, mv_lookup, "2026-07-29")
        self.assertTrue(result["RandomForest"]["realized_7d"]["sign_accuracy"] > result["HistGradientBoosting"]["realized_7d"]["sign_accuracy"])
```

- [ ] **Schritt 4: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v`

- [ ] **Schritt 5: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: Modell-spezifische Realwert-Auswertung + Trailing-30d-Live-Auswahl"
```

---

### Task 4: `market_predictor.py` — beide Prognosen loggen, Live-Auswahl verdrahten, Trend berechnen

**Files:** Modify: `src/market_predictor.py`

**Interfaces:**
- Konsumiert: alles aus Task 2+3.
- Produziert: `predict_market_value_changes()`-Rueckgabewert bekommt neues
  Feld `"accuracy_trend"` (Liste, siehe Schritt 4) und `metrics["selection_reason"]`.
  Von Task 6 (`dashboard_export.py`) genutzt.

- [ ] **Schritt 1: `_append_todays_predictions` auf Mehrfach-Modell umstellen (aktuell Zeilen 526-533)**

Von:
```python
def _append_todays_predictions(today_df: pd.DataFrame, predictions: dict[str, float]) -> None:
    new_entries = [
        {"date": pd.Timestamp(date).date().isoformat(), "player_id": player_id, "predicted_delta": predictions[player_id]}
        for player_id, date in zip(today_df["player_id"], today_df["date"])
        if player_id in predictions
    ]
    log = _load_prediction_log() + new_entries
    _save_prediction_log(log)
```
Zu:
```python
def _append_todays_predictions(today_df: pd.DataFrame, predictions_by_model: dict[str, dict[str, float]]) -> None:
    new_entries = [
        {
            "date": pd.Timestamp(date).date().isoformat(),
            "player_id": player_id,
            "model_type": model_type,
            "predicted_delta": predictions[player_id],
        }
        for model_type, predictions in predictions_by_model.items()
        for player_id, date in zip(today_df["player_id"], today_df["date"])
        if player_id in predictions
    ]
    log = _load_prediction_log() + new_entries
    _save_prediction_log(log)
```

- [ ] **Schritt 2: `_save_prediction_log`s Dedup-Key um `model_type` erweitern (aktuell Zeile 449)**

Von:
```python
    deduped = {(e["date"], e["player_id"]): e for e in entries}
```
Zu:
```python
    deduped = {(e["date"], e["player_id"], e["model_type"]): e for e in entries}
```

- [ ] **Schritt 3: Neue Funktion `_build_accuracy_trend` (nach `_evaluate_realized_accuracy_by_model`)**

```python
def _build_accuracy_trend(log_entries: list[dict], mv_lookup: dict, today: str) -> list[dict]:
    """Taegliche realisierte sign_accuracy pro Modell UEBER DIE KOMPLETTE
    Historie (nicht nur 'heute' wie _evaluate_realized_accuracy_by_model) -
    Rohdaten fuer den Trend-Chart im 'ML-Genauigkeit'-Tab. Gruppiert nach
    Log-Datum, ein Eintrag pro Tag mit beiden Modellen nebeneinander."""
    by_date: dict[str, dict[str, list[bool]]] = {}
    for entry in log_entries:
        model_type = entry.get("model_type")
        if model_type not in ("RandomForest", "HistGradientBoosting"):
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        sign_correct = bool(np.sign(entry["predicted_delta"]) == np.sign(actual_delta))
        by_date.setdefault(date, {"RandomForest": [], "HistGradientBoosting": []})[model_type].append(sign_correct)

    trend = []
    for date in sorted(by_date):
        day = {"date": date}
        for model_type, hits in by_date[date].items():
            day[model_type] = round(float(np.mean(hits)) * 100, 1) if hits else None
        trend.append(day)
    return trend
```

- [ ] **Schritt 4: `predict_market_value_changes` verdrahten (aktuell Zeilen 536-606, konkret ab `trained = _train_and_evaluate(history_df)`)**

Von:
```python
        trained = _train_and_evaluate(history_df)
        if trained is None:
            print(
                f"Warnung: zu wenig Trainingsdaten ({len(history_df)} Zeilen, Minimum {MIN_TRAINING_ROWS}) - "
                "ML-Prognose uebersprungen.",
                file=sys.stderr,
            )
            return None
        model, metrics = trained

        backtest = _walk_forward_backtest(history_df)
        if backtest is not None:
            metrics["backtest"] = backtest

        # ... (median_days_to_next / today_df-Vorbereitung unveraendert) ...

        predicted = model.predict(today_df[FEATURES])
        predictions = {
            player_id: round(float(value))
            for player_id, value in zip(today_df["player_id"], predicted)
        }

        today_iso = pd.Timestamp(corpus["date"].max()).date().isoformat()
        mv_lookup = _build_mv_lookup(corpus)
        realized = _evaluate_realized_accuracy(_load_prediction_log(), mv_lookup, today_iso)
        metrics.update(realized)
        _append_todays_predictions(today_df, predictions)

        return {"predictions": predictions, "metrics": metrics}
```
Zu:
```python
        trained = _train_and_evaluate(history_df)
        if trained is None:
            print(
                f"Warnung: zu wenig Trainingsdaten ({len(history_df)} Zeilen, Minimum {MIN_TRAINING_ROWS}) - "
                "ML-Prognose uebersprungen.",
                file=sys.stderr,
            )
            return None
        models, metrics = trained
        synthetic_winner = metrics["model_type"]

        backtest = _walk_forward_backtest(history_df)
        if backtest is not None:
            metrics["backtest"] = backtest

        # ... (median_days_to_next / today_df-Vorbereitung UNVERAENDERT) ...

        today_iso = pd.Timestamp(corpus["date"].max()).date().isoformat()
        mv_lookup = _build_mv_lookup(corpus)
        log_entries = _load_prediction_log()
        realized_by_model = _evaluate_realized_accuracy_by_model(log_entries, mv_lookup, today_iso)
        metrics["realized_by_model"] = realized_by_model
        metrics["accuracy_trend"] = _build_accuracy_trend(log_entries, mv_lookup, today_iso)

        live_model_name, selection_reason = _select_live_model(realized_by_model, synthetic_winner)
        metrics["model_type"] = live_model_name
        metrics["selection_reason"] = selection_reason
        live_model = models[live_model_name]

        predictions_by_model = {
            name: {
                player_id: round(float(value))
                for player_id, value in zip(today_df["player_id"], model.predict(today_df[FEATURES]))
            }
            for name, model in models.items()
        }
        predictions = predictions_by_model[live_model_name]
        _append_todays_predictions(today_df, predictions_by_model)

        return {"predictions": predictions, "metrics": metrics}
```
**Wichtig**: der Block zwischen `models, metrics = trained` und
`today_iso = ...` (median_days_to_next-Berechnung, `today_df.dropna(...)`)
bleibt UNVERAENDERT stehen, nur an der richtigen Stelle im neuen Ablauf
(nach `backtest`, vor `today_iso`) - im Diff nicht vergessen, nur die
Stellen DAVOR und DANACH aendern sich.

- [ ] **Schritt 5: Tests laufen lassen + `__main__`-Ausgabe pruefen**

Run: `python3 -m unittest discover -s tests -v`

Die bestehende `if __name__ == "__main__":`-Ausgabe (`print("Metriken:",
result["metrics"])`) zeigt jetzt zusaetzlich `selection_reason`/
`realized_by_model`/`accuracy_trend` mit an - kein Code-Aenderung an
diesem Block noetig (Task 5 erweitert ihn um das `--backfill`-Flag).

- [ ] **Schritt 6: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/market_predictor.py
git commit -m "market_predictor: beide Modell-Prognosen loggen, Live-Modellwahl + Trend verdrahten"
```

---

### Task 5: `market_predictor.py` — Backfill-Utility

**Files:** Modify: `src/market_predictor.py`

**Interfaces:**
- Produziert: `backfill_prediction_log(days: int = 90) -> dict` (aufrufbar
  per `python -m src.market_predictor --backfill 90`).

- [ ] **Schritt 1: Neue Funktion `backfill_prediction_log` (nach `_walk_forward_backtest`, vor `_load_prediction_log`)**

```python
def backfill_prediction_log(days: int = 90) -> dict:
    """Einmalige Utility (dauerhaft im Code, nicht Teil des taeglichen Laufs):
    baut denselben Corpus wie ein normaler Lauf, aber statt nur der letzten
    BACKTEST_FOLDS Cutoffs werden bis zu `days` rollierende historische
    Cutoffs durchlaufen (begrenzt durch verfuegbare Kickbase-Historie UND
    genug Trainingszeilen je Cutoff - fruehe Tage im ~365-Tage-Fenster
    fallen typischerweise raus). Pro Fold werden ECHTE Pro-Spieler-
    predicted_delta-Werte fuer BEIDE Modelle gesammelt (nicht nur
    aggregiertes Hit/Miss wie _walk_forward_backtest) und als
    ml_prediction_log-Eintraege nach Firestore geschrieben - schliesst die
    Kaltstart-Luecke fuer die Trailing-30d-Live-Auswahl, ohne 90 echte
    Kalendertage abwarten zu muessen. Wiederverwendbar, falls die
    Firestore-Historie je zurueckgesetzt werden muss."""
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        print("Warnung: KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen, Backfill uebersprungen.", file=sys.stderr)
        return {"folds_run": 0, "entries_written": 0}

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    me = get_me(token, league_id)
    competition_id = me.get("cpi") or "1"
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)

    dates = sorted(history_df["date"].unique())
    cutoffs = dates[-days:] if len(dates) > days else dates

    entries = []
    folds_run = 0
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[TARGET]
        x_test = test[FEATURES]
        cutoff_date = pd.Timestamp(cutoff).date().isoformat()

        candidates = {
            "RandomForest": RandomForestRegressor(
                n_estimators=200,
                max_depth=20,
                min_samples_split=5,
                min_samples_leaf=2,
                max_features="sqrt",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
            "HistGradientBoosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE),
        }
        for model_type, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            entries.extend(
                {
                    "date": cutoff_date,
                    "player_id": player_id,
                    "model_type": model_type,
                    "predicted_delta": round(float(pred)),
                }
                for player_id, pred in zip(test["player_id"], y_pred)
            )

    if entries and os.environ.get("FIRESTORE_ENABLED"):
        fs_client = firestore_db.connect()
        firestore_db.upsert_prediction_log_entries(fs_client, entries)

    return {"folds_run": folds_run, "entries_written": len(entries)}
```
(Nutzt bewusst dieselben Hyperparameter/RandomState wie
`_walk_forward_backtest`, NICHT die von `_train_and_evaluate` - konsistent
mit dem bestehenden Backtest-Mechanismus, den das hier hochskaliert.)

- [ ] **Schritt 2: `__main__`-Block um `--backfill`-Flag erweitern (aktuell Zeilen 609-618)**

Von:
```python
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    result = predict_market_value_changes()
    if result is None:
        print("Keine Prognose verfuegbar (siehe Warnungen oben).")
    else:
        print("Metriken:", result["metrics"])
        print(f"Anzahl Spieler mit Prognose: {len(result['predictions'])}")
```
Zu:
```python
if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=int, default=None, metavar="DAYS")
    args = parser.parse_args()

    if args.backfill is not None:
        result = backfill_prediction_log(args.backfill)
        print(f"Backfill: {result['folds_run']} Folds, {result['entries_written']} Eintraege geschrieben.")
    else:
        result = predict_market_value_changes()
        if result is None:
            print("Keine Prognose verfuegbar (siehe Warnungen oben).")
        else:
            print("Metriken:", result["metrics"])
            print(f"Anzahl Spieler mit Prognose: {len(result['predictions'])}")
```

- [ ] **Schritt 3: Test in `tests/test_market_predictor.py` (reine Struktur-/Grenzfall-Tests, kein echter Kickbase-Call)**

```python
from unittest.mock import patch


class BackfillPredictionLogTests(unittest.TestCase):
    def test_returns_zero_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            result = backfill_prediction_log(90)
        self.assertEqual(result, {"folds_run": 0, "entries_written": 0})
```
(Weitere Tests mit echtem Corpus wuerden echte Kickbase-Zugangsdaten
brauchen - nicht sinnvoll unit-testbar, analog zu `predict_market_value_changes`
selbst, das auch keine solchen Tests hat. Die Verifikation fuer den
"echten Lauf"-Pfad passiert in Task 8 als manueller Testlauf.)

- [ ] **Schritt 4: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v`

- [ ] **Schritt 5: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: Backfill-Utility fuer ml_prediction_log (--backfill Flag)"
```

---

### Task 6: `dashboard_export.py` — Trend-Daten in den Snapshot einhaengen

**Files:** Modify: `src/dashboard_export.py`

**Interfaces:**
- Konsumiert: `predictions["metrics"]["accuracy_trend"]`/`["realized_by_model"]`/`["selection_reason"]`
  aus Task 4 (bereits Teil des bestehenden `predictions`-Dicts, das
  `export()` schon von `market_predictor.predict_market_value_changes()`
  bekommt - KEINE neue Funktion noetig, nur Wiring).

- [ ] **Schritt 1: In `export()`s `data`-Dict einhaengen**

Suche die Stelle, an der `predictions` bereits verwendet wird (z.B.
`"ml_metrics": predictions["metrics"] if predictions else None,` — quote
den exakten aktuellen Kontext vor dem Edit, Zeile per `grep -n "ml_metrics"
src/dashboard_export.py` bestaetigen). Direkt danach ergaenzen:

```python
        "ml_accuracy_trend": predictions["metrics"].get("accuracy_trend") if predictions else None,
```
(`.get(...)` statt `[...]`, defensiv falls ein alter/degradierter
`predictions`-Dict das Feld mal nicht hat - z.B. wenn `market_predictor.py`
mal ohne die Phase-4-Aenderung liefe, sollte das nicht crashen.)

- [ ] **Schritt 2: Tests laufen lassen**

Run: `python3 -m unittest discover -s tests -v` — kein neuer Test noetig
(reines Dict-Wiring, keine eigene Logik; `ml_metrics` selbst wird bereits
indirekt durch bestehende Tests/den E2E-Lauf abgedeckt).

- [ ] **Schritt 3: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/dashboard_export.py
git commit -m "dashboard_export: ml_accuracy_trend in den Snapshot einhaengen"
```

---

### Task 7: `index.html` — Neuer Tab "ML-Genauigkeit"

**Files:** Modify: `index.html`

**WICHTIG — vor dem eigentlichen Chart-Code**: das `dataviz`-Skill laden
(`Skill`-Tool, `dataviz`), damit Farben/Form des neuen Trend-Charts
konsistent zum Rest des Dashboards sind (erster Chart in diesem Projekt,
bisher nur Tabellen/Pills). Diesen Schritt NICHT ueberspringen, auch wenn
der Chart "nur eine Linie" scheint.

**Interfaces:**
- Konsumiert: `DATA.ml_accuracy_trend` (Liste von `{date, RandomForest,
  HistGradientBoosting}`, `RandomForest`/`HistGradientBoosting` sind
  `sign_accuracy`-Prozentwerte oder `null`), `DATA.ml_metrics.realized_by_model`,
  `DATA.ml_metrics.selection_reason`, `DATA.ml_metrics.model_type` (bereits
  vorhanden, zeigt nach Task 4 das LIVE gewaehlte Modell).

- [ ] **Schritt 1: dataviz-Skill laden, dann Tab-Button + Panel ergaenzen**
  (gleiches Muster wie der "Alle Spieler"-Tab: `data-tab="ml-genauigkeit"`-Button
  + `id="tab-ml-genauigkeit"`-Section, siehe `index.html` Zeilen ~184-196
  fuer die Stelle).

- [ ] **Schritt 2: `renderMlGenauigkeit()` schreiben**

  - Kopf-an-Kopf-Karte: `DATA.ml_metrics.model_type` (aktuell gewaehlt),
    `DATA.ml_metrics.selection_reason` als Klartext ("Trailing-30-Tage-
    Realwerte" / "Synthetischer Split (noch zu wenig Realdaten)"),
    daneben beide Modelle mit ihrer `realized_by_model[name].realized_30d`
    (sign_accuracy/mae/n) nebeneinander (Tabelle oder zwei Karten,
    `fmtNum`/vorhandene Pill-Helfer wiederverwenden wo passend).
  - Trend-Chart: `DATA.ml_accuracy_trend` als Zeitreihe, zwei Linien
    (RandomForest/HistGradientBoosting), X-Achse Datum, Y-Achse
    sign_accuracy% — exakte Umsetzung (SVG-Inline vs. Canvas, Achsen-
    beschriftung, Legende, Farben) richtet sich nach der `dataviz`-Skill-
    Anleitung aus Schritt 1, hier bewusst nicht vorgeschrieben.
  - `null`-Werte im Trend (Tage ohne genug Log-Daten fuer ein Modell)
    duerfen die Linie nicht abbrechen lassen (Luecke ueberspringen statt
    Fehler) - `fmtNum`-aehnliches Nullish-Handling wie im Rest der Datei.

- [ ] **Schritt 3: In `renderAll()`/`updateTabBadges()` einhaengen**

  Gleiches Muster wie beim Alle-Spieler-Tab (Task 5 der letzten Session,
  `index.html` Zeilen ~750/~657/~669 als Referenz) - Badge kann z.B. Anzahl
  Trend-Tage zeigen (`(DATA.ml_accuracy_trend || []).length`).

- [ ] **Schritt 4: Syntax-Check + Tests**

  `<script type="module">`-Bloecke extrahieren, `node --check` (gleiche
  Methode wie mehrfach in dieser Session genutzt).
  `python3 -m unittest discover -s tests -v` — weiterhin gruen (reine
  `index.html`-Aenderung).

- [ ] **Schritt 5: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add index.html
git commit -m "Neuen ML-Genauigkeit-Tab mit Kopf-an-Kopf-Vergleich + Trend-Chart"
```

---

### Task 8: Backfill ausfuehren + End-to-End-Verifikation + HANDOFF.md

**Files:** Modify: `HANDOFF.md`

- [ ] **Schritt 1: Echten Backfill-Lauf durchfuehren**

```bash
FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3 -m src.market_predictor --backfill 90
```
Erwartung: Terminal zeigt plausible `folds_run`/`entries_written`
(> 0, deutlich mehr als die bisherigen 6 Backtest-Folds). Firestore-Console
zeigt neue `ml_prediction_log`-Dokumente im neuen `{date}_{player_id}_{model_type}`-Schema.

- [ ] **Schritt 2: Lokalen Dashboard-Export-Testlauf machen**

```bash
FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3 -m src.dashboard_export
```
Erwartung: laeuft durch, `data["ml_accuracy_trend"]` im Ergebnis mit
mehreren Tagen befuellt (dank Backfill aus Schritt 1).

- [ ] **Schritt 3: `HANDOFF.md` aktualisieren**

Phase 4 als erledigt markieren, neue `ml_prediction_log`-Schema-Aenderung
dokumentieren, Backfill-Utility erwaehnen, Resume Instructions auf Phase 5
(Mobile/UX) umstellen.

- [ ] **Schritt 4: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add HANDOFF.md
git commit -m "HANDOFF.md: Phase 4 (ML-Genauigkeit/Modellwahl) als erledigt markieren"
```

---

## Verifikation (Gesamt)

- `python3 -m unittest discover -s tests -v` — alle Tests gruen (bisherige
  42 + neue aus Task 1/2/3/5).
- Backfill-Lauf schreibt plausible Anzahl Firestore-Dokumente im neuen Schema.
- Lokaler `dashboard_export`-Lauf liefert befuellten `ml_accuracy_trend`.
- Browser-Test (User): neuer "ML-Genauigkeit"-Tab zeigt Kopf-an-Kopf-Karte
  + Trend-Chart mit den Backfill-Daten, `selection_reason` ist nachvollziehbar.
- `node --check` beide Script-Bloecke fehlerfrei.
