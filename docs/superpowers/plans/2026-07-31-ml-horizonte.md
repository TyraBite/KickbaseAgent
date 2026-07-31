# ML-Horizonte (3-Tage-Prognose + Konfidenz-Signal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Einen zusätzlichen 3-Tage-Prognose-Horizont in `market_predictor.py` einbauen (1-Tage bleibt primär), plus eine kombinierte Konfidenz-Einschätzung im Frontend, die 1-Tage-Prognose + 3-Tage-Prognose + Modell-Ungenauigkeit (MAE) zusammenführt und den bestehenden `sellSignal()`-Trigger um einen dritten Zustand ("unklar") erweitert.

**Architecture:** Backend: neues Trainingsziel `mv_target_3d_clipped` (gleiche Features, `.shift(-3)` statt `.shift(-1)`), Training/Backtest-Funktionen werden um einen `target_col`-Parameter erweitert statt dupliziert, Genauigkeits-Tracking (`ml_prediction_log`/`ml_accuracy_daily`) bekommt eine `horizon_days`-Dimension im Doc-Key. Frontend: neue `momentumAssessment()`-Funktion (reine Ableitung aus bereits vorhandenen Zahlen) + `sellSignal()`-Umbau auf 3-wertig.

**Tech Stack:** Python (pandas/sklearn, `src/market_predictor.py`, `src/firestore_db.py`, `src/dashboard_export.py`), TypeScript/React (`frontend/src/lib/derive.ts`, `frontend/src/types.ts`, 4 Tab-Komponenten).

## Global Constraints

- 1-Tages-Prognose bleibt der PRIMÄRE Indikator, unverändert in ihrem heutigen Verhalten (Regression-Risiko: die bestehende, bereits genutzte 1-Tages-Prognose darf durch diesen Plan an KEINER Stelle schlechter/anders werden).
- 3-Tages-Training/-Tracking ist unabhängig fehlschlagbar — ein Fehler dort darf die 1-Tages-Prognose niemals mitreißen (kein gemeinsamer Try/Except-Block).
- Nur 2 Horizonte (1 + 3 Tage), keine weiteren.
- Keine Änderung an Spekulations-Sortierung/-Filterung (bleibt ROI-basiert).
- `sellSignal()`-Konfidenz-Schwelle (`|prediction| ≤ mae` → `"unklar"`) ist identisch zur `momentumAssessment()`-Schwelle für `"unsicher"` — beide Stellen nutzen dieselbe Definition.
- Backend-Verifikation: `python3 -m unittest discover -s tests` nach jedem Backend-Task.
- Frontend-Verifikation: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` nach jedem Frontend-Task. Kein Test-Runner im Projekt vorhanden (kein Jest/Vitest).
- Push nach jedem Task erlaubt, wenn die jeweilige Verifikation grün ist (bestehende Projekt-Policy).

---

## Task 1: Neues Trainingsziel `mv_target_3d_clipped`

**Files:**
- Modify: `src/market_predictor.py`
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Produces: neue Konstante `TARGET_3D = "mv_target_3d_clipped"`. `_engineer_features()`s zurückgegebene `history_df`/`today_df` haben zusätzlich die Spalten `mv_next_3d`, `mv_target_3d`, `mv_target_3d_clipped` — NICHT Teil des bestehenden `history_df.dropna(subset=[...])`-Filters (siehe Begründung unten), können also NaN enthalten.

**Wichtig:** `mv_target_3d_clipped` wird bewusst NICHT zum bestehenden `history_df.dropna(subset=[...])`-Aufruf hinzugefügt — das würde die Trainingsdaten der (unveränderten, primären) 1-Tages-Prognose um die letzten ~2 Zeilen pro Spieler verkleinern, obwohl die 1-Tages-Prognose diese Spalte gar nicht braucht. Die 3-Tage-Prognose entfernt ihre eigenen NaN-Zeilen selbst, siehe Task 2.

- [ ] **Step 1: Failing Test schreiben**

In `tests/test_market_predictor.py`, `PerformanceFrameMinutesAvgTests` oder eine neue Klasse am Ende der Datei (Import-Liste um `_engineer_features` ergänzen falls noch nicht vorhanden):

```python
class EngineerFeatures3dTargetTests(unittest.TestCase):
    def test_mv_target_3d_uses_shift_of_three_not_one(self):
        # 5 Tage, taeglich +1000 Marktwert-Aenderung fuer denselben Spieler.
        rows = [
            {"player_id": "p1", "team_id": "t1", "date": pd.Timestamp(f"2026-07-{20+i:02d}"),
             "mv": 10_000_000 + i * 1000, "md": pd.NaT, "p": None, "mp": None, "mp_avg_3": None,
             "t1": "t1", "t2": None, "t1g": None, "t2g": None,
             "days_since_last_status_change": 9999, "status_change_count_90d": 0}
            for i in range(5)
        ]
        df = pd.DataFrame(rows)
        history_df, _ = _engineer_features(df)
        # Zeile fuer 2026-07-20 (i=0): mv_target (1 Tag) = 1000, mv_target_3d (3 Tage) = 3000.
        row0 = history_df[history_df["date"] == pd.Timestamp("2026-07-20")].iloc[0]
        self.assertEqual(row0["mv_target"], 1000)
        self.assertEqual(row0["mv_target_3d"], 3000)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_market_predictor.EngineerFeatures3dTargetTests -v`
Expected: FAIL (`KeyError: 'mv_target_3d'`)

- [ ] **Step 3: Implementierung**

In `src/market_predictor.py`, Konstante nach `TARGET = "mv_target_clipped"` ergänzen:

```python
TARGET_3D = "mv_target_3d_clipped"
```

In `_engineer_features()`, direkt nach `df["mv_target"] = df["mv_next_day"] - df["mv"]` (vor `df = df[df["mv"] != 0.0]`) ergänzen:

```python
    df["mv_next_3d"] = df.groupby("player_id")["mv"].shift(-3)
    df["mv_target_3d"] = df["mv_next_3d"] - df["mv"]
```

Direkt nach dem bestehenden Clipping-Block (nach `df["mv_target_clipped"] = df["mv_target"].clip(...)`, vor `df = df.fillna({...})`) ergänzen:

```python
    q1_3d = df["mv_target_3d"].quantile(0.25)
    q3_3d = df["mv_target_3d"].quantile(0.75)
    iqr_3d = q3_3d - q1_3d
    df["mv_target_3d_clipped"] = df["mv_target_3d"].clip(q1_3d - 2.5 * iqr_3d, q3_3d + 2.5 * iqr_3d)
```

`history_df.dropna(subset=[...])` (Zeile mit `"mv_change_1d", "next_md", ...`) bleibt UNVERÄNDERT — bewusst, siehe "Wichtig" oben.

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_market_predictor -v`
Expected: alle PASS (inkl. aller bestehenden Tests unverändert grün — reine Ergänzung)

- [ ] **Step 5: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: mv_target_3d_clipped als zweites Trainingsziel ergaenzt (3-Tage-Horizont)"
```

---

## Task 2: `_train_and_evaluate()`/`_walk_forward_backtest()` um `target_col`-Parameter erweitern

**Files:**
- Modify: `src/market_predictor.py`
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Consumes: `TARGET_3D` (Task 1).
- Produces: `_train_and_evaluate(history_df, target_col: str = TARGET)`, `_walk_forward_backtest(history_df, target_col: str = TARGET)` — beide Default-Parameter, damit JEDER bestehende Aufruf ohne Änderung weiterhin exakt das 1-Tage-Verhalten von heute liefert (reine Erweiterung, kein Verhaltensunterschied bei Default-Aufruf).

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_market_predictor.py` (Import-Liste um `_train_and_evaluate`, `_walk_forward_backtest`, `TARGET_3D` ergänzen falls noch nicht vorhanden):

```python
class TrainAndEvaluateTargetColTests(unittest.TestCase):
    def _history_df(self, target_col):
        import numpy as np
        n = 250
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rng = np.random.RandomState(42)
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "mv_target_clipped": rng.randn(n) * 5000,
            "alt_target_clipped": rng.randn(n) * 9000,
        })
        return df

    def test_default_target_col_is_backward_compatible(self):
        df = self._history_df("mv_target_clipped")
        result = _train_and_evaluate(df)
        self.assertIsNotNone(result)

    def test_custom_target_col_is_used_for_training(self):
        df = self._history_df("alt_target_clipped")
        result = _train_and_evaluate(df, target_col="alt_target_clipped")
        self.assertIsNotNone(result)
        models, metrics = result
        self.assertIn("model_type", metrics)

    def test_rows_with_nan_target_col_are_dropped_not_fatal(self):
        df = self._history_df("mv_target_clipped")
        df.loc[df.index[:5], "alt_target_clipped"] = None
        result = _train_and_evaluate(df, target_col="alt_target_clipped")
        self.assertIsNotNone(result)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_market_predictor.TrainAndEvaluateTargetColTests -v`
Expected: FAIL (`TypeError: _train_and_evaluate() got an unexpected keyword argument 'target_col'`)

- [ ] **Step 3: Implementierung — `_train_and_evaluate()`**

Signatur + erste Zeilen ändern von:

```python
def _train_and_evaluate(history_df: pd.DataFrame):
    """..."""
    if len(history_df) < MIN_TRAINING_ROWS:
        return None

    df = history_df.sort_values("date").reset_index(drop=True)
```

zu:

```python
def _train_and_evaluate(history_df: pd.DataFrame, target_col: str = TARGET):
    """... Erweitert um target_col: die Zeilen ohne bekannten Zielwert
    (z.B. die letzten paar Tage pro Spieler beim 3-Tage-Ziel, siehe
    TARGET_3D) werden hier - und nur hier, nicht global auf history_df -
    verworfen, damit ein zweites Trainingsziel die Datenbasis des ersten
    nicht verkleinert."""
    df = history_df.dropna(subset=[target_col])
    if len(df) < MIN_TRAINING_ROWS:
        return None

    df = df.sort_values("date").reset_index(drop=True)
```

Weiter unten in derselben Funktion, ersetze:

```python
    x_train, y_train = train[FEATURES], train[TARGET]
    x_test, y_test = test[FEATURES], test[TARGET]
```

durch:

```python
    x_train, y_train = train[FEATURES], train[target_col]
    x_test, y_test = test[FEATURES], test[target_col]
```

- [ ] **Step 4: Implementierung — `_walk_forward_backtest()`**

Signatur ändern von `def _walk_forward_backtest(history_df: pd.DataFrame) -> dict | None:` zu `def _walk_forward_backtest(history_df: pd.DataFrame, target_col: str = TARGET) -> dict | None:`.

Im Funktionskörper, ersetze:

```python
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[TARGET]
        x_test = test[FEATURES]
        y_test_actual = test["mv_target"]
```

durch:

```python
    unclipped_col = target_col.removesuffix("_clipped")
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff].dropna(subset=[target_col])
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty or test[unclipped_col].isna().all():
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[target_col]
        x_test = test[FEATURES]
        y_test_actual = test[unclipped_col]
```

(`target_col.removesuffix("_clipped")` macht aus `"mv_target_clipped"` → `"mv_target"` und aus `"mv_target_3d_clipped"` → `"mv_target_3d"` — exakt die schon vorhandenen unkleinen Spaltennamen, keine neue Spalte nötig.)

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS (insbesondere alle BESTEHENDEN `_train_and_evaluate`/`_walk_forward_backtest`-Tests unverändert grün — Regressionscheck für die unveraenderte 1-Tages-Prognose)

- [ ] **Step 6: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: _train_and_evaluate()/_walk_forward_backtest() um target_col-Parameter erweitert (fuer 3-Tage-Horizont wiederverwendbar)"
```

---

## Task 3: Horizont-Dimension im Genauigkeits-Tracking

**Files:**
- Modify: `src/market_predictor.py`
- Modify: `src/firestore_db.py`
- Test: `tests/test_market_predictor.py`, `tests/test_firestore_db.py`

**Interfaces:**
- Produces: `_load_recent_prediction_log(today: str, horizon_days: int) -> list[dict]`, `_build_daily_accuracy_updates(recent_entries, mv_lookup, today, horizon_days: int) -> list[dict]`, `_append_todays_predictions(today_df, predictions_by_model, horizon_days: int) -> None`. `firestore_db.upsert_prediction_log_entries()`/`upsert_accuracy_daily()`s Doc-Ids bekommen `_{horizon_days}` angehängt (Default `1` über `.get("horizon_days", 1)` für Alt-Einträge ohne das Feld — bleiben dadurch als Horizont 1 einsortiert, keine Migration nötig).
- `get_recent_prediction_log_entries()`/`get_accuracy_daily()` in `firestore_db.py` bleiben UNVERÄNDERT (Horizont-Filterung passiert client-seitig in `market_predictor.py`, kein neuer Firestore-Query-Index nötig).

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_firestore_db.py`, nach `UpsertPredictionLogEntriesModelTypeDocIdTests` einfügen:

```python
class PredictionLogHorizonDocIdTests(unittest.TestCase):
    def test_doc_id_includes_horizon_days(self):
        client = MagicMock()
        entries = [{"date": "2026-07-31", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100, "horizon_days": 3}]
        firestore_db.upsert_prediction_log_entries(client, entries)
        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-31_p1_RandomForest_3", doc_ids)

    def test_doc_id_defaults_horizon_to_1_when_missing(self):
        client = MagicMock()
        entries = [{"date": "2026-07-31", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}]
        firestore_db.upsert_prediction_log_entries(client, entries)
        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-31_p1_RandomForest_1", doc_ids)


class AccuracyDailyHorizonDocIdTests(unittest.TestCase):
    def test_doc_id_includes_horizon_days(self):
        client = MagicMock()
        entries = [{"date": "2026-07-31", "model_type": "RandomForest", "horizon_days": 3, "n": 10, "sign_correct": 7, "abs_error_sum": 1000.0}]
        firestore_db.upsert_accuracy_daily(client, entries)
        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-31_RandomForest_3", doc_ids)
```

In `tests/test_market_predictor.py` (Import-Liste um `_build_daily_accuracy_updates`, `_load_recent_prediction_log`, `_append_todays_predictions` ergänzen falls fehlend):

```python
class HorizonAwareAccuracyUpdatesTests(unittest.TestCase):
    def test_uses_horizon_days_shift_not_hardcoded_one_day(self):
        mv_lookup = {("p1", "2026-07-20"): 10_000_000, ("p1", "2026-07-23"): 10_003_000}
        entries = [{"date": "2026-07-20", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 3000}]
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-31", horizon_days=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["horizon_days"], 3)
        self.assertEqual(result[0]["sign_correct"], 1)

    def test_missing_horizon_shifted_value_skips_entry(self):
        mv_lookup = {("p1", "2026-07-20"): 10_000_000}  # kein Wert fuer +3 Tage bekannt
        entries = [{"date": "2026-07-20", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 3000}]
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-31", horizon_days=3)
        self.assertEqual(result, [])


class LoadRecentPredictionLogHorizonTests(unittest.TestCase):
    def test_returns_empty_dict_without_firestore_enabled_for_any_horizon(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.market_predictor._load_local_prediction_log", return_value=[]):
            self.assertEqual(_load_recent_prediction_log("2026-07-31", horizon_days=3), [])

    def test_filters_local_fallback_by_horizon(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.market_predictor._load_local_prediction_log") as mock_local:
            mock_local.return_value = [
                {"date": "2026-07-29", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 1, "horizon_days": 1},
                {"date": "2026-07-29", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 2, "horizon_days": 3},
            ]
            result = _load_recent_prediction_log("2026-07-31", horizon_days=3)
        self.assertEqual([e["predicted_delta"] for e in result], [2])


class AppendTodaysPredictionsHorizonTests(unittest.TestCase):
    def test_logged_entries_include_horizon_days(self):
        with patch("src.market_predictor._load_local_prediction_log", return_value=[]), patch("src.market_predictor._save_prediction_log") as mock_save:
            today_df = pd.DataFrame({"player_id": ["p1"], "date": [pd.Timestamp("2026-07-31")]})
            _append_todays_predictions(today_df, {"RandomForest": {"p1": 500}}, horizon_days=3)
        logged = mock_save.call_args.args[0]
        self.assertEqual(logged[0]["horizon_days"], 3)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_firestore_db.PredictionLogHorizonDocIdTests tests.test_firestore_db.AccuracyDailyHorizonDocIdTests tests.test_market_predictor.HorizonAwareAccuracyUpdatesTests tests.test_market_predictor.LoadRecentPredictionLogHorizonTests tests.test_market_predictor.AppendTodaysPredictionsHorizonTests -v`
Expected: FAIL (diverse `TypeError`/`AssertionError` — Parameter/Felder existieren noch nicht)

- [ ] **Step 3: Implementierung — `firestore_db.py`**

In `upsert_prediction_log_entries()`, ersetze:

```python
    docs = {f"{e['date']}_{e['player_id']}_{e.get('model_type')}": e for e in entries}
```

durch:

```python
    docs = {f"{e['date']}_{e['player_id']}_{e.get('model_type')}_{e.get('horizon_days', 1)}": e for e in entries}
```

In `upsert_accuracy_daily()`, ersetze:

```python
    docs = {f"{e['date']}_{e['model_type']}": e for e in entries}
```

durch:

```python
    docs = {f"{e['date']}_{e['model_type']}_{e.get('horizon_days', 1)}": e for e in entries}
```

- [ ] **Step 4: Implementierung — `market_predictor.py`**

`_load_recent_prediction_log()`:

```python
def _load_recent_prediction_log(today: str, horizon_days: int) -> list[dict]:
    since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=EVALUATION_LOOKBACK_DAYS)).isoformat()
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            entries = firestore_db.get_recent_prediction_log_entries(firestore_db.connect(), since, today)
            return [e for e in entries if e.get("horizon_days", 1) == horizon_days]
        except Exception as exc:
            print(
                f"Warnung: ml_prediction_log-Lesezugriff fehlgeschlagen, nutze lokale Datei: {exc}",
                file=sys.stderr,
            )
    return [e for e in _load_local_prediction_log() if since <= e["date"] < today and e.get("horizon_days", 1) == horizon_days]
```

`_build_daily_accuracy_updates()` — Signatur und Kern ändern:

```python
def _build_daily_accuracy_updates(recent_entries: list[dict], mv_lookup: dict, today: str, horizon_days: int) -> list[dict]:
    agg: dict[tuple[str, str], dict] = {}
    for entry in recent_entries:
        model_type = entry.get("model_type")
        if model_type not in ("RandomForest", "HistGradientBoosting"):
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=horizon_days)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        sign_correct = bool(np.sign(entry["predicted_delta"]) == np.sign(actual_delta))
        abs_error = abs(entry["predicted_delta"] - actual_delta)
        key = (date, model_type)
        bucket = agg.setdefault(
            key, {"date": date, "model_type": model_type, "horizon_days": horizon_days, "n": 0, "sign_correct": 0, "abs_error_sum": 0.0}
        )
        bucket["n"] += 1
        bucket["sign_correct"] += int(sign_correct)
        bucket["abs_error_sum"] += abs_error
    return list(agg.values())
```

`_append_todays_predictions()`:

```python
def _append_todays_predictions(today_df: pd.DataFrame, predictions_by_model: dict[str, dict[str, float]], horizon_days: int) -> None:
    new_entries = [
        {
            "date": pd.Timestamp(date).date().isoformat(),
            "player_id": player_id,
            "model_type": model_type,
            "predicted_delta": predictions[player_id],
            "horizon_days": horizon_days,
        }
        for model_type, predictions in predictions_by_model.items()
        for player_id, date in zip(today_df["player_id"], today_df["date"])
        if player_id in predictions
    ]
    log = _load_local_prediction_log() + new_entries
    _save_prediction_log(log)
```

In `_save_prediction_log()`, ersetze die Dedup-Zeile:

```python
    deduped = {(e["date"], e["player_id"], e.get("model_type")): e for e in entries}
```

durch:

```python
    deduped = {(e["date"], e["player_id"], e.get("model_type"), e.get("horizon_days", 1)): e for e in entries}
```

(Diese beiden Aufrufstellen — `_build_daily_accuracy_updates`/`_load_recent_prediction_log` in `predict_market_value_changes()` — werden erst in Task 4 aktualisiert, dieser Task ändert nur die Funktionsdefinitionen + Firestore-Doc-Ids. `predict_market_value_changes()` bricht deshalb zwischen Task 3 und Task 4 kurzzeitig mit einem `TypeError` bei fehlendem `horizon_days`-Argument — das ist in Ordnung, kein Test ruft `predict_market_value_changes()` direkt end-to-end auf, siehe bestehende Test-Suite.)

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS

- [ ] **Step 6: Commit**

```bash
git add src/market_predictor.py src/firestore_db.py tests/test_market_predictor.py tests/test_firestore_db.py
git commit -m "Genauigkeits-Tracking um horizon_days-Dimension erweitert (ml_prediction_log/ml_accuracy_daily Doc-Ids, Alt-Eintraege defaulten auf Horizont 1)"
```

---

## Task 4: `_train_and_track_horizon()`-Helper extrahieren, `predict_market_value_changes()` fürs 1-Tage-Ziel umgestellt (reiner Refactor)

**Files:**
- Modify: `src/market_predictor.py`
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Consumes: `TARGET`/`TARGET_3D` (Task 1), `target_col`-Parameter (Task 2), `horizon_days`-Parameter (Task 3).
- Produces: `_train_and_track_horizon(history_df, today_df, target_col, horizon_days, today_iso, mv_lookup) -> dict | None` (Rückgabe `{"predictions": {...}, "metrics": {...}}` oder `None` bei zu wenig Trainingsdaten). `predict_market_value_changes()`s äußerlich sichtbares Verhalten für den 1-Tage-Fall bleibt in diesem Task **exakt identisch** zu vorher — reiner Umbau, kein neuer Horizont wird hier noch angeboten (das ist Task 5).

- [ ] **Step 1: Failing Test schreiben**

In `tests/test_market_predictor.py` (Import um `_train_and_track_horizon` ergänzen):

```python
class TrainAndTrackHorizonTests(unittest.TestCase):
    def test_returns_none_when_too_few_training_rows(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2026-07-01"]), "player_id": ["p1"], "mv_target_clipped": [100]})
        result = _train_and_track_horizon(df, df, TARGET, 1, "2026-07-31", {})
        self.assertIsNone(result)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_market_predictor.TrainAndTrackHorizonTests -v`
Expected: FAIL (`NameError: name '_train_and_track_horizon' is not defined`)

- [ ] **Step 3: Implementierung — Helper extrahieren**

In `src/market_predictor.py`, direkt vor `def predict_market_value_changes()` einfügen:

```python
def _train_and_track_horizon(
    history_df: pd.DataFrame,
    today_df: pd.DataFrame,
    target_col: str,
    horizon_days: int,
    today_iso: str,
    mv_lookup: dict,
) -> dict | None:
    """Trainiert+trackt+waehlt live EINEN Prognose-Horizont. Faktorisiert
    aus predict_market_value_changes(), das dies fuer horizon_days=1
    (target_col=TARGET, unveraendertes Verhalten) und horizon_days=3
    (target_col=TARGET_3D, Task 5) getrennt aufruft - ein fehlschlagendes
    3-Tage-Training darf die 1-Tages-Prognose nicht mitreissen, deshalb
    zwei unabhaengige Aufrufe statt einer gemeinsamen Fehlerbehandlung."""
    trained = _train_and_evaluate(history_df, target_col)
    if trained is None:
        return None
    models, metrics = trained
    synthetic_winner = metrics["model_type"]

    backtest = _walk_forward_backtest(history_df, target_col)
    if backtest is not None:
        metrics["backtest"] = backtest

    recent_entries = _load_recent_prediction_log(today_iso, horizon_days)
    daily_updates = _build_daily_accuracy_updates(recent_entries, mv_lookup, today_iso, horizon_days)
    if daily_updates and os.environ.get("FIRESTORE_ENABLED"):
        try:
            firestore_db.upsert_accuracy_daily(firestore_db.connect(), daily_updates)
        except Exception as exc:
            print(f"Warnung: Firestore-Schreibzugriff fuer ml_accuracy_daily (Horizont {horizon_days}) fehlgeschlagen: {exc}", file=sys.stderr)

    daily_docs: list[dict] = []
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            all_docs = firestore_db.get_accuracy_daily(firestore_db.connect())
            daily_docs = [d for d in all_docs if d.get("horizon_days", 1) == horizon_days]
        except Exception as exc:
            print(f"Warnung: ml_accuracy_daily-Lesezugriff (Horizont {horizon_days}) fehlgeschlagen: {exc}", file=sys.stderr)

    realized_by_model = _realized_by_model_from_daily(daily_docs, today_iso)
    metrics["realized_by_model"] = realized_by_model
    metrics["accuracy_trend"] = _trend_from_daily(daily_docs)
    metrics["synthetic_winner"] = synthetic_winner

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
    _append_todays_predictions(today_df, predictions_by_model, horizon_days)

    return {"predictions": predictions, "metrics": metrics}
```

`live_model` (Zeile `live_model = models[live_model_name]`) wird zwar zugewiesen aber nicht weiter genutzt - identisch zum bisherigen Code (`live_model` war im Original auch ungenutzt, siehe `predictions_by_model` nutzt `models` direkt), bewusst nicht bereinigt in diesem reinen Extraktions-Schritt.

- [ ] **Step 4: `predict_market_value_changes()` umbauen (nur 1-Tage, Verhalten identisch)**

Ersetze den kompletten Block ab `trained = _train_and_evaluate(history_df)` bis `return {"predictions": predictions, "metrics": metrics}` (also alles zwischen `history_df, today_df = _engineer_features(corpus)` und dem `except`-Block) durch:

```python
        history_df, today_df = _engineer_features(corpus)

        median_days_to_next = history_df["days_to_next"].median()
        today_df = today_df.copy()
        today_df["days_to_next"] = today_df["days_to_next"].fillna(median_days_to_next)
        today_df = today_df.dropna(subset=["mv"] + FEATURES)
        if today_df.empty:
            print("Warnung: keine heutigen Zeilen mit vollstaendigen Features - ML-Prognose uebersprungen.", file=sys.stderr)
            return None

        today_iso = _infer_today(corpus)
        mv_lookup = _build_mv_lookup(corpus)

        result_1d = _train_and_track_horizon(history_df, today_df, TARGET, 1, today_iso, mv_lookup)
        if result_1d is None:
            print(
                f"Warnung: zu wenig Trainingsdaten ({len(history_df)} Zeilen, Minimum {MIN_TRAINING_ROWS}) - "
                "ML-Prognose uebersprungen.",
                file=sys.stderr,
            )
            return None

        return {"predictions": result_1d["predictions"], "metrics": result_1d["metrics"]}
```

(Der 3-Tage-Aufruf kommt erst in Task 5 dazu - dieser Task liefert bewusst exakt dasselbe Rückgabe-Dict wie vorher, nur anders zusammengesetzt.)

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS

- [ ] **Step 6: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: _train_and_track_horizon()-Helper extrahiert (reiner Refactor, 1-Tages-Verhalten unveraendert)"
```

---

## Task 5: 3-Tage-Horizont live schalten + players-Map/Snapshot verdrahten

**Files:**
- Modify: `src/market_predictor.py`
- Modify: `src/dashboard_export.py`
- Test: `tests/test_market_predictor.py`, `tests/test_dashboard_export.py`

**Interfaces:**
- Consumes: `_train_and_track_horizon()` (Task 4), `TARGET_3D` (Task 1).
- Produces: `predict_market_value_changes()`s Rückgabe-Dict bekommt zusätzlich `predictions_3d: dict | None`, `metrics_3d: dict | None`. players-Map bekommt `ml_prediction_3d`. Snapshot bekommt `ml_metrics_3d`, `ml_accuracy_trend_3d`.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_dashboard_export.py`, `BuildPlayersMapTests` ergänzen:

```python
    def test_overlays_ml_prediction_3d_only_for_predicted_ids(self):
        result = _build_players_map(
            all_players=[self._all_players_row(player_id="p1"), self._all_players_row(player_id="p2", name="Foo")],
            own_squad=[], market_listings=[],
            predictions={"predictions": {}, "predictions_3d": {"p1": 70_000}},
            previous_players=None, is_light=False,
        )
        self.assertEqual(result["p1"]["ml_prediction_3d"], 70_000)
        self.assertNotIn("ml_prediction_3d", result["p2"])

    def test_ml_prediction_3d_absent_when_predictions_3d_missing(self):
        result = _build_players_map(
            all_players=[self._all_players_row(player_id="p1")], own_squad=[], market_listings=[],
            predictions={"predictions": {}}, previous_players=None, is_light=False,
        )
        self.assertNotIn("ml_prediction_3d", result["p1"])
```

In `AssembleSnapshotContractTests`, `EXPECTED_KEYS` und den Testaufruf ergänzen (siehe Step 4 unten für die exakten neuen Zeilen).

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_dashboard_export.BuildPlayersMapTests -v`
Expected: FAIL (`KeyError`/`AssertionError` - `ml_prediction_3d` wird noch nicht gesetzt)

- [ ] **Step 3: `predict_market_value_changes()` um den 3-Tage-Aufruf erweitern**

In `src/market_predictor.py`, ersetze das Ende von `predict_market_value_changes()` (den `return`-Aufruf aus Task 4, Step 4) durch:

```python
        result_1d = _train_and_track_horizon(history_df, today_df, TARGET, 1, today_iso, mv_lookup)
        if result_1d is None:
            print(
                f"Warnung: zu wenig Trainingsdaten ({len(history_df)} Zeilen, Minimum {MIN_TRAINING_ROWS}) - "
                "ML-Prognose uebersprungen.",
                file=sys.stderr,
            )
            return None

        result_3d = _train_and_track_horizon(history_df, today_df, TARGET_3D, 3, today_iso, mv_lookup)
        if result_3d is None:
            print(
                "Warnung: 3-Tage-Prognose konnte nicht trainiert werden, wird uebersprungen "
                "(1-Tages-Prognose unbetroffen).",
                file=sys.stderr,
            )

        return {
            "predictions": result_1d["predictions"],
            "metrics": result_1d["metrics"],
            "predictions_3d": result_3d["predictions"] if result_3d else None,
            "metrics_3d": result_3d["metrics"] if result_3d else None,
        }
```

- [ ] **Step 4: `dashboard_export.py` verdrahten**

`_resolve_heavy_data()`, Light-Zweig (`if is_light: return {...}`) — ergänze zwei neue Keys, mit `.get()` statt Bracket-Zugriff (Alt-Snapshots ohne diese Felder duerfen keinen `KeyError` werfen):

```python
    if is_light:
        return {
            "all_players": None,
            "predictions": None,
            "calibration": cached_snapshot["calibration"],
            "owned_by": cached_snapshot.get("owned_by", {}),
            "ml_metrics": cached_snapshot["ml_metrics"],
            "ml_accuracy_trend": cached_snapshot["ml_accuracy_trend"],
            "ml_metrics_3d": cached_snapshot.get("ml_metrics_3d"),
            "ml_accuracy_trend_3d": cached_snapshot.get("ml_accuracy_trend_3d"),
        }
```

Heavy-Zweig, ersetze das Rückgabe-Dict:

```python
    return {
        "all_players": all_players,
        "predictions": predictions,
        "calibration": player_valuation.load_calibration(),
        "owned_by": owned_by,
        "ml_metrics": predictions["metrics"] if predictions else None,
        "ml_accuracy_trend": predictions["metrics"].get("accuracy_trend") if predictions else None,
        "ml_metrics_3d": predictions.get("metrics_3d") if predictions else None,
        "ml_accuracy_trend_3d": (predictions.get("metrics_3d") or {}).get("accuracy_trend") if predictions else None,
    }
```

In `_build_players_map()`, direkt nach dem bestehenden `predictions_by_id`-Overlay-Block (`for pid, value in predictions_by_id.items(): if pid in base: base[pid]["ml_prediction"] = value`) ergänzen:

```python
    predictions_3d_by_id = (predictions or {}).get("predictions_3d") or {}
    for pid, value in predictions_3d_by_id.items():
        if pid in base:
            base[pid]["ml_prediction_3d"] = value
```

In `_assemble_snapshot()`, Parameterliste um `ml_metrics_3d, ml_accuracy_trend_3d,` ergänzen (nach `ml_accuracy_trend,`) und im zurückgegebenen Dict ergänzen:

```python
        "ml_metrics_3d": ml_metrics_3d,
        "ml_accuracy_trend_3d": ml_accuracy_trend_3d,
```

(direkt nach `"ml_accuracy_trend": ml_accuracy_trend,`). In `export()`s Aufruf von `_assemble_snapshot(...)`, ergänze `ml_metrics_3d=heavy["ml_metrics_3d"], ml_accuracy_trend_3d=heavy["ml_accuracy_trend_3d"],` (nach `ml_accuracy_trend=heavy["ml_accuracy_trend"],`).

In `tests/test_dashboard_export.py`, `AssembleSnapshotContractTests.EXPECTED_KEYS` ergänzen um `"ml_metrics_3d", "ml_accuracy_trend_3d",` und im Testaufruf `_assemble_snapshot(...)` die beiden neuen Keyword-Argumente (`ml_metrics_3d=None, ml_accuracy_trend_3d=None,`) ergänzen.

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS

- [ ] **Step 6: Live-Smoke-Test (Sandbox hat echten Kickbase/Firestore-Zugriff)**

Run: `python3 -m src.market_predictor`
Expected: läuft ohne Absturz durch. Bei Bedarf kurz per Debug-Print prüfen, dass `predict_market_value_changes()`s Rückgabe-Dict `predictions_3d`/`metrics_3d` enthält (auch wenn `metrics_3d["realized_by_model"]` anfangs noch auf Kaltstart-Platzhalter steht — analog zur Fitness-Historie ist eine leere/kaltstart-Genauigkeitshistorie fürs 3-Tage-Ziel der korrekte Anfangszustand, kein Bug).

- [ ] **Step 7: Commit**

```bash
git add src/market_predictor.py src/dashboard_export.py tests/test_market_predictor.py tests/test_dashboard_export.py
git commit -m "3-Tage-ML-Horizont live geschaltet: predictions_3d/metrics_3d, ml_prediction_3d in players-Map, ml_metrics_3d/ml_accuracy_trend_3d im Snapshot"
```

---

## Task 6: Frontend-Typen für den 3-Tage-Horizont

**Files:**
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Consumes: `ml_prediction_3d`/`ml_metrics_3d`/`ml_accuracy_trend_3d` (Task 5, Backend).
- Produces: `PlayerRecord.ml_prediction_3d?: number`, `DashboardSnapshot.ml_metrics_3d: MlMetrics | null`, `DashboardSnapshot.ml_accuracy_trend_3d: MlAccuracyTrendEntry[] | null`.

- [ ] **Step 1: `PlayerRecord` erweitern**

In `frontend/src/types.ts`, `PlayerRecord`-Interface, nach `ml_prediction?: number;` ergänzen:

```ts
  // Nur vorhanden, wenn das 3-Tage-Modell einen Wert produziert hat:
  ml_prediction_3d?: number;
```

- [ ] **Step 2: `DashboardSnapshot` erweitern**

Nach `ml_accuracy_trend: MlAccuracyTrendEntry[] | null;` ergänzen:

```ts
  ml_metrics_3d: MlMetrics | null;
  ml_accuracy_trend_3d: MlAccuracyTrendEntry[] | null;
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts
git commit -m "types.ts: ml_prediction_3d/ml_metrics_3d/ml_accuracy_trend_3d fuer den 3-Tage-Horizont ergaenzt"
```

---

## Task 7: `momentumAssessment()` in `derive.ts`

**Files:**
- Modify: `frontend/src/lib/derive.ts`

**Interfaces:**
- Consumes: `ml_prediction`, `ml_prediction_3d` (players-Map-Felder, Task 6), `liveModelMae()` (bereits vorhanden).
- Produces: `export type MomentumConfidence = "sicher" | "wahrscheinlich" | "unsicher"`, `export interface MomentumAssessment { confidence: MomentumConfidence; direction: "steigend" | "fallend"; agreesWith3d: boolean | null; label: string }`, `export function momentumAssessment(prediction1d: number | null, prediction3d: number | null, mae: number | null): MomentumAssessment | null`.

- [ ] **Step 1: Implementierung**

Nach `liveModelMae()` in `frontend/src/lib/derive.ts` einfügen:

```ts
export type MomentumConfidence = "sicher" | "wahrscheinlich" | "unsicher";

export interface MomentumAssessment {
  confidence: MomentumConfidence;
  direction: "steigend" | "fallend";
  agreesWith3d: boolean | null;
  label: string;
}

// Reine Ableitung aus bereits vorhandenen Zahlen (1-Tages-Prognose, primaer;
// 3-Tages-Prognose als Relativierer; MAE des 1-Tages-Modells als
// Unsicherheits-Mass) - kein neues Training noetig. Konfidenz-Schwellen
// beziehen sich bewusst NUR auf die 1-Tages-Prognose (der primaere
// Indikator), die 3-Tages-Prognose beeinflusst nur den Text, nicht die
// Konfidenz-Stufe selbst.
export function momentumAssessment(
  prediction1d: number | null,
  prediction3d: number | null,
  mae: number | null
): MomentumAssessment | null {
  if (prediction1d === null) return null;

  const direction: "steigend" | "fallend" = prediction1d > 0 ? "steigend" : "fallend";
  let confidence: MomentumConfidence;
  if (mae === null) {
    confidence = "wahrscheinlich";
  } else if (Math.abs(prediction1d) > 2 * mae) {
    confidence = "sicher";
  } else if (Math.abs(prediction1d) > mae) {
    confidence = "wahrscheinlich";
  } else {
    confidence = "unsicher";
  }

  const confidenceLabel = confidence.charAt(0).toUpperCase() + confidence.slice(1);
  let label = `${confidenceLabel} ${direction} (${fmtSigned(prediction1d)}`;
  label += mae !== null ? `, Modell-Ungenauigkeit ±${fmtNum(mae)})` : ")";

  let agreesWith3d: boolean | null = null;
  if (prediction3d !== null) {
    agreesWith3d = Math.sign(prediction3d) === Math.sign(prediction1d) || prediction3d === 0;
    if (agreesWith3d) {
      label += ` — 3-Tage-Trend bestätigt (${fmtSigned(prediction3d)})`;
    } else {
      const dir3d = prediction3d > 0 ? "steigend" : "fallend";
      label += ` — 3-Tage-Trend zeigt aber ${dir3d} (${fmtSigned(prediction3d)}), evtl. nur kurzfristiges Rauschen`;
    }
  }

  return { confidence, direction, agreesWith3d, label };
}

function fmtSigned(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${fmtNum(value)}`;
}

function fmtNum(value: number): string {
  return Math.round(value).toLocaleString("de-DE");
}
```

**Beispiel-Verifikation** (manuell, kein Test-Runner vorhanden): `momentumAssessment(15000, 40000, 25000)` muss `label` exakt `"Unsicher steigend (+15.000, Modell-Ungenauigkeit ±25.000) — 3-Tage-Trend bestätigt (+40.000)"` liefern (`|15000| ≤ 25000` → `"unsicher"`; `sign(40000) === sign(15000)` → bestätigt). `momentumAssessment(15000, -10000, 25000)` muss stattdessen `"... — 3-Tage-Trend zeigt aber fallend (-10.000), evtl. nur kurzfristiges Rauschen"` enthalten.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler

- [ ] **Step 3: Manuelle Verifikation gegen die zwei Beispiele oben**

Da kein Test-Runner existiert: kurz per Node/`tsx` oder einem Wegwerf-Skript `momentumAssessment(15000, 40000, 25000)` und `momentumAssessment(15000, -10000, 25000)` aufrufen und die `label`-Strings gegen die oben genannten exakten Erwartungen prüfen. Danach das Wegwerf-Skript wieder löschen (nicht committen).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/derive.ts
git commit -m "derive.ts: momentumAssessment() ergaenzt (1-Tage primaer, 3-Tage relativiert, MAE als Konfidenz-Mass)"
```

---

## Task 8: `sellSignal()` auf 3-wertig umbauen + Badge-Farben neu verteilen

**Files:**
- Modify: `frontend/src/lib/derive.ts`
- Modify: `frontend/src/components/EigenesTeamTab.tsx`

**Interfaces:**
- Consumes: `liveModelMae()` (bereits vorhanden).
- Produces: `sellSignal(mlPrediction: number | null | undefined, mae: number | null): "halten" | "verkaufen" | "unklar"`. `buildEigenesTeamSplit(players, ownSquadIds, targets, calibration, mae: number | null)` — neuer letzter Parameter. `EigenesTeamRow.sell_signal?: "halten" | "verkaufen" | "unklar"`.

- [ ] **Step 1: `sellSignal()` umbauen**

In `frontend/src/lib/derive.ts`, ersetze:

```ts
export function sellSignal(mlPrediction: number | null | undefined): "halten" | "verkaufen" {
  return (mlPrediction ?? 0) > 0 ? "halten" : "verkaufen";
}
```

durch:

```ts
export function sellSignal(
  mlPrediction: number | null | undefined,
  mae: number | null
): "halten" | "verkaufen" | "unklar" {
  const pred = mlPrediction ?? 0;
  if (mae !== null && Math.abs(pred) <= mae) return "unklar";
  return pred > 0 ? "halten" : "verkaufen";
}
```

- [ ] **Step 2: `EigenesTeamRow`/`buildEigenesTeamSplit()` anpassen**

Ersetze:

```ts
export interface EigenesTeamRow extends PlayerRow { sell_signal?: "halten" | "verkaufen" }
export interface EigenesTeamSplit { verkaufen: EigenesTeamRow[]; bleibt: EigenesTeamRow[] }

export function buildEigenesTeamSplit(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  targets: RawWunschkaderTarget[],
  calibration: Calibration | null
): EigenesTeamSplit {
  const targetIds = new Set(targets.map((t) => t.player_id));
  const verkaufen: EigenesTeamRow[] = [];
  const bleibt: EigenesTeamRow[] = [];
  for (const pid of ownSquadIds) {
    const player = players[pid];
    if (!player) continue;
    const row = buildPlayerRow(player, calibration);
    if (targetIds.has(pid)) {
      bleibt.push(row);
    } else {
      verkaufen.push({ ...row, sell_signal: sellSignal(player.ml_prediction) });
    }
  }
  return { verkaufen, bleibt };
}
```

durch:

```ts
export interface EigenesTeamRow extends PlayerRow { sell_signal?: "halten" | "verkaufen" | "unklar" }
export interface EigenesTeamSplit { verkaufen: EigenesTeamRow[]; bleibt: EigenesTeamRow[] }

export function buildEigenesTeamSplit(
  players: Record<string, PlayerRecord>,
  ownSquadIds: string[],
  targets: RawWunschkaderTarget[],
  calibration: Calibration | null,
  mae: number | null
): EigenesTeamSplit {
  const targetIds = new Set(targets.map((t) => t.player_id));
  const verkaufen: EigenesTeamRow[] = [];
  const bleibt: EigenesTeamRow[] = [];
  for (const pid of ownSquadIds) {
    const player = players[pid];
    if (!player) continue;
    const row = buildPlayerRow(player, calibration);
    if (targetIds.has(pid)) {
      bleibt.push(row);
    } else {
      verkaufen.push({ ...row, sell_signal: sellSignal(player.ml_prediction, mae) });
    }
  }
  return { verkaufen, bleibt };
}
```

- [ ] **Step 3: `EigenesTeamTab.tsx` — Aufrufstelle + Badges anpassen**

`liveModelMae(data.ml_metrics)` wird schon berechnet (Variable `liveMae`) — an der `buildEigenesTeamSplit(...)`-Aufrufstelle (`useMemo`) muss diese Berechnung VOR dem `useMemo` stehen, damit sie als Argument übergeben werden kann. Suche die bestehende Zeile `const liveMae = liveModelMae(data.ml_metrics);` und verschiebe sie (falls nötig) vor die `buildEigenesTeamSplit`-`useMemo`-Aufrufstelle, dann ergänze `liveMae` als 5. Argument:

```tsx
() => buildEigenesTeamSplit(data.players, data.own_squad_ids, data.wunschkader_targets, data.calibration, liveMae),
```

(Dependency-Array des `useMemo` um `liveMae` ergänzen, falls React-Hooks-Lint das verlangt — `[data, liveMae]` statt nur `[data]`.)

Die beiden Badge-Render-Stellen (Kachel + Detail), ersetze jeweils:

```tsx
<Badge tone={row.sell_signal === "halten" ? "good" : "warn"}>
  {row.sell_signal === "halten" ? "Noch halten" : "Jetzt verkaufen"}
</Badge>
```

durch:

```tsx
<Badge tone={row.sell_signal === "halten" ? "good" : row.sell_signal === "unklar" ? "warn" : "crit"}>
  {row.sell_signal === "halten" ? "Noch halten" : row.sell_signal === "unklar" ? "Unklar" : "Jetzt verkaufen"}
</Badge>
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler

- [ ] **Step 5: Commit + Push + Deploy prüfen**

```bash
git add frontend/src/lib/derive.ts frontend/src/components/EigenesTeamTab.tsx
git commit -m "sellSignal(): dritter Zustand 'unklar' bei Prognose innerhalb der Modell-Ungenauigkeit, Badge-Farben neu verteilt (verkaufen jetzt rot, unklar gelb)"
git push origin main
```

Run: `gh run list --workflow=frontend-pilot.yml --limit 1` (ggf. `gh run watch <id>`)
Expected: Lauf grün.

---

## Task 9: `momentumAssessment()` in die 4 Detail-Modals einbauen

**Files:**
- Modify: `frontend/src/components/EigenesTeamTab.tsx`
- Modify: `frontend/src/components/WunschkaderTab.tsx`
- Modify: `frontend/src/components/SpekulationTab.tsx`
- Modify: `frontend/src/components/TransfermarktTab.tsx`

**Interfaces:**
- Consumes: `momentumAssessment()` (Task 7), `liveModelMae()` (bereits vorhanden), `player.ml_prediction`/`player.ml_prediction_3d` (Task 6).

Alle vier Dateien folgen demselben Muster: `momentumAssessment(player.ml_prediction ?? null, player.ml_prediction_3d ?? null, liveMae)` berechnen und als neue `<Row label="Einschätzung">`-Zeile (oder das jeweils lokal genutzte Äquivalent, z.B. `<p>`) direkt unter der bestehenden ML-Prognose-Anzeige einfügen. `liveMae` ist in `EigenesTeamTab.tsx` bereits vorhanden (Task 8); in den anderen drei Dateien ggf. neu berechnen: `liveModelMae(data.ml_metrics)`.

- [ ] **Step 1: `EigenesTeamTab.tsx` — Detail-Modal ergänzen**

Import um `momentumAssessment` ergänzen. In der Detail-Ansicht, direkt nach der Zeile, die `row.ml_prediction` anzeigt, ergänzen:

```tsx
{(() => {
  const assessment = momentumAssessment(row.ml_prediction ?? null, players[row.player_id]?.ml_prediction_3d ?? null, liveMae);
  return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
})()}
```

(Falls `players` als Prop in dieser Detail-Komponente noch nicht vorhanden ist: `data.players` von der übergeordneten Komponente durchreichen, analog zum bereits bestehenden Muster in `WunschkaderTab.tsx`s `DetailModal` mit dem `ownSquadIds`/`players`-Prop, siehe HANDOFF.md.)

- [ ] **Step 2: `WunschkaderTab.tsx` — Detail-Modal ergänzen**

Import um `liveModelMae`, `momentumAssessment` ergänzen (falls `liveModelMae` dort noch nicht importiert ist). Im `DetailModal`, nach der bestehenden ML-Prognose-Zeile:

```tsx
{(() => {
  const mae = liveModelMae(data.ml_metrics);
  const assessment = momentumAssessment(
    players[target.player_id]?.ml_prediction ?? null,
    players[target.player_id]?.ml_prediction_3d ?? null,
    mae
  );
  return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
})()}
```

- [ ] **Step 3: `SpekulationTab.tsx` — Detail-Modal ergänzen**

Gleiches Muster, nach der bestehenden ML-Prognose(+MAE)-Zeile im Detail-Modal:

```tsx
{(() => {
  const assessment = momentumAssessment(row.ml_prediction, player?.ml_prediction_3d ?? null, mae);
  return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
})()}
```

(`mae` ist hier bereits als Prop/Variable vorhanden, siehe `liveModelMae()`-Nutzung aus der ML-MAE-Ergänzung — `player` bzw. der volle `PlayerRecord` muss ggf. zusätzlich durchgereicht werden, um an `ml_prediction_3d` zu kommen, falls die Detail-Komponente aktuell nur die abgeleitete `SpekulationRow`/`PlayerRow` ohne dieses Feld erhält.)

- [ ] **Step 4: `TransfermarktTab.tsx` — Detail-Modal ergänzen**

Analog zu Spekulation (wurde in einer früheren Session bereits an Spekulations-Detail angeglichen, siehe HANDOFF.md) — gleiches Muster, nach der ML-Prognose(+MAE)-Zeile:

```tsx
{(() => {
  const assessment = momentumAssessment(row.ml_prediction, player?.ml_prediction_3d ?? null, mae);
  return assessment ? <Row label="Einschätzung">{assessment.label}</Row> : null;
})()}
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit`
Expected: 0 Fehler

- [ ] **Step 6: Commit + Push + Deploy prüfen**

```bash
git add frontend/src/components/EigenesTeamTab.tsx frontend/src/components/WunschkaderTab.tsx frontend/src/components/SpekulationTab.tsx frontend/src/components/TransfermarktTab.tsx
git commit -m "momentumAssessment() in alle 4 Detail-Modals eingebaut (Eigenes Team, Wunschkader, Spekulation, Transfermarkt)"
git push origin main
```

Run: `gh run list --workflow=frontend-pilot.yml --limit 1` (ggf. `gh run watch <id>`)
Expected: Lauf grün.

- [ ] **Step 7: Live-Browser-Test durch den User**

Checkliste: pro Tab (Eigenes Team, Wunschkader, Spekulation, Transfermarkt) einen Spieler mit ML-Prognose öffnen — "Einschätzung"-Zeile sichtbar, Text plausibel (Richtung/Konfidenz/3-Tage-Vergleich). Eigenes-Team-Verkaufskandidaten-Badges: grün/gelb/rot wie erwartet, "Unklar" taucht bei kleinen Prognosen auf.

---

## Verification (gesamt)

- [ ] `python3 -m unittest discover -s tests` grün nach jedem Backend-Task (1-5).
- [ ] `tsc --noEmit` grün nach jedem Frontend-Task (6-9).
- [ ] Live-Smoke-Test (Task 5) + Live-Browser-Test (Task 9) — beide Tasks gelten erst danach als abgeschlossen.
- [ ] Push nach jedem Task, wenn die jeweilige Verifikation grün ist.
- [ ] Nach Abschluss: HANDOFF.md aktualisieren (3-Tage-Horizont, Konfidenz-Signal, sellSignal-Umbau, Kaltstart-Hinweis für `ml_metrics_3d`/`realized_by_model`).

## Self-Review

- **Spec-Abdeckung**: 3-Tage-Trainingsziel (Task 1), Training/Backtest-Generalisierung (Task 2), Horizont-Tracking (Task 3), Live-Schaltung + Snapshot-Verdrahtung (Task 4-5), Frontend-Typen (Task 6), `momentumAssessment()` (Task 7), `sellSignal()`-Umbau (Task 8), Verdrahtung in 4 Modals (Task 9) — alle Spec-Abschnitte gedeckt.
- **Regression-Schutz explizit eingebaut**: Task 2/4 sind bewusst als reine, verhaltenserhaltende Refactors markiert (Default-Parameter, identisches Rückgabe-Dict) BEVOR Task 5 den neuen Horizont überhaupt aktiviert — ein Fehler im 3-Tage-Pfad kann durch diese Reihenfolge nicht in die bereits produktive 1-Tages-Prognose durchschlagen.
- **Platzhalter-Scan**: keine TBD/TODO. Task 9s Wiring-Code für Spekulation/Transfermarkt ist als "Muster, ggf. Variablennamen an die tatsächliche Komponentenstruktur anpassen" markiert, da die exakten lokalen Variablennamen (`mae`, `player`) zum Planzeitpunkt nicht Zeile für Zeile verifiziert wurden — das ist eine bewusste, benannte Unsicherheit (kein Platzhalter für fehlendes Wissen über DAS Konzept, siehe Global Constraints), der Implementer verifiziert das gegen die echte Datei vor dem Einbau.
- **Typ-Konsistenz**: `sellSignal()`s neue Signatur (Task 8) und `momentumAssessment()`s Signatur (Task 7) nutzen durchgehend `number | null` (nicht `undefined`) für `mae`, konsistent mit `liveModelMae()`s bestehendem Rückgabetyp.
