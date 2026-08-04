# ML-Prognose: Baseline-Ehrlichkeit + Embargo-/Clip-Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Genauigkeits-Kennzahlen der ML-Marktwertprognose ehrlich machen
(Trägheits-Baseline-Vergleich, Trendwende-Trefferquote, Richtung/Betrag-
Trennung) und zwei damit verwandte Leak-Bugs beheben (fehlendes Embargo bei
Mehrtage-Horizonten, Ziel-Clip-Grenzen aus dem Gesamt-Corpus statt nur der
Vergangenheit).

**Architecture:** Siehe `docs/superpowers/specs/2026-08-04-ml-baseline-honesty-design.md`
für den vollen Kontext/die Begründung. Eine Implementierungs-Verfeinerung
gegenüber der Spec (verifiziert gegen den echten Code beim Schreiben dieses
Plans, kein Scope-/Verhaltens-Unterschied): statt EINES gemeinsamen
"Fold-Runners" für `_walk_forward_backtest`/`backfill_prediction_log` (die
Spec-Skizze) teilen sich beide nur die kleineren, echt gemeinsamen Bausteine
(`_apply_embargo`, `_clip_target`, `_score_counts_from_arrays`,
`_finalize_score_counts`) - weil beide Aufrufer unterschiedlich aggregieren
(Backtest poolt alle Folds zu EINER Kennzahl, Backfill schreibt EIN Dokument
PRO Fold/Tag). `_score_counts_from_arrays` (rohe Summen/Counter) +
`_finalize_score_counts` (daraus abgeleitete, gerundete Prozent-Kennzahlen)
sind zwei statt einer Funktion, weil `_finalize_score_counts` dadurch AUCH
von `_summarize_from_daily()` (aggregiert bereits gespeicherte Tages-Summen)
wiederverwendet werden kann, ohne die Metrik-Formel ein drittes Mal zu
schreiben - der eigentliche Kern von "eine Stelle, kein Drift".

**Tech Stack:** Python/pandas/sklearn (Backend), React/TypeScript (Frontend),
`unittest`/Vitest/Playwright-CT (Tests).

## Global Constraints

- Kommentare nur wo Logik nicht-offensichtlich ist. Modulinterne Funktionen
  mit führendem Unterscore.
- Parametrisieren statt duplizieren - keine zweite Kopie derselben
  Berechnung.
- Strukturell gleiche Parameter als Keyword-Argument übergeben, wo bereits
  etabliert (z.B. `target_col=`, `horizon_days=` in bestehenden Signaturen).
- Jeder Fix/jedes Feature braucht einen automatisierten Test, TDD (erst rot,
  dann grün), Mutation-Check.
- Bestehende, unveränderte Tests müssen nach jedem Task weiterhin grün sein
  (kein stillschweigender Verhaltens-Bruch an unbeteiligten Stellen).
- Frontend: Ableitungen/Vergleiche gehören nach `derive.ts`, nicht in die
  Tab-Komponente. Erklärtexte ans Seitenende der jeweiligen Sektion.
- `python -m pytest` (nicht bares `pytest`).
- Keine Firestore-Schema-Migration nötig (Nach-Abschluss-Backfill übernimmt
  das, siehe Ende dieses Plans) - kein defensiver Code für "Feld existiert
  vielleicht nicht", AUSSER an den beiden Stellen, wo bereits gespeicherte
  ALTE Tages-Dokumente aggregiert werden (`_summarize_from_daily`) - dort
  ist die Übergangsphase zwischen Deploy und dem manuellen Backfill real,
  kein Hypothetisches, `.get(feld, 0)`/`.get(feld, 0.0)` ist dort gerechtfertigt.

---

## File Structure

- Modify: `src/market_predictor.py` (Konstanten, `_engineer_features`, neue
  Helfer, `_train_and_evaluate`, `_walk_forward_backtest`,
  `backfill_prediction_log`, `_build_daily_accuracy_updates`,
  `_summarize_from_daily`, `_train_and_track_horizon`)
- Modify: `tests/test_market_predictor.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/lib/derive.ts` (+ `frontend/src/lib/derive.test.ts`)
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx`
- Create: `frontend/tests-ct/MlGenauigkeitTab.ct.tsx`

---

### Task 1: Grundbausteine — Konstanten-Umbenennung, Clip-Leck-Fix, neue reine Helfer

**Files:**
- Modify: `src/market_predictor.py:64-98` (Konstanten), `:380-468` (`_engineer_features`)
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Produces: `TARGET = "mv_target"`, `TARGET_3D = "mv_target_3d"` (vorher
  `"mv_target_clipped"`/`"mv_target_3d_clipped"` - ab jetzt ungeklippt).
  `_clip_target(unclipped: pd.Series) -> pd.Series`. `_apply_embargo(train: pd.DataFrame, cutoff, horizon_days: int) -> pd.DataFrame`.
  `_BASELINE_COLUMN_BY_HORIZON: dict[int, str]` (`{1: "mv_change_1d", 3: "mv_change_3d"}`).
  `_score_counts_from_arrays(y_actual, y_pred, baseline_pred) -> dict` (rohe
  Summen/Counter, Keys: `n`, `sign_correct`, `abs_error_sum`,
  `abs_error_sum_given_correct_sign`, `n_baseline`, `baseline_sign_correct`,
  `baseline_abs_error_sum`, `n_baseline_wrong`,
  `model_sign_correct_when_baseline_wrong`).
  `_finalize_score_counts(counts: dict) -> dict | None` (daraus abgeleitete,
  gerundete Kennzahlen: `n`, `sign_accuracy`, `mae`, `mae_given_correct_sign`,
  `baseline_sign_accuracy`, `baseline_mae`, `reversal_sign_accuracy`,
  `reversal_n` - `None` bei `n==0`).
  `_empty_counts() -> dict` (alle Keys von `_score_counts_from_arrays` auf 0/0.0).
- Diese Funktionen werden von Task 2-5 konsumiert.

- [ ] **Step 1: Failing Tests für die neuen reinen Helfer schreiben**

In `tests/test_market_predictor.py`, am Ende der Datei (nach dem letzten
Test) neue Testklassen einfügen:

```python
class ClipTargetTests(unittest.TestCase):
    def test_clips_using_only_given_series_quantiles(self):
        # Werte 0..99 plus ein Ausreisser 100000 - IQR-Clip muss den
        # Ausreisser kappen, den Rest unveraendert lassen.
        values = pd.Series(list(range(100)) + [100000])
        clipped = _clip_target(values)
        self.assertLess(clipped.iloc[-1], 100000)
        self.assertEqual(clipped.iloc[0], 0)
        self.assertEqual(clipped.iloc[50], 50)


class ApplyEmbargoTests(unittest.TestCase):
    def _train(self):
        return pd.DataFrame({
            "date": pd.to_datetime([
                "2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05",
            ]),
        })

    def test_horizon_1_is_noop(self):
        train = self._train()
        result = _apply_embargo(train, pd.Timestamp("2026-08-06"), horizon_days=1)
        self.assertEqual(len(result), 5)

    def test_horizon_3_excludes_last_two_days_before_cutoff(self):
        # cutoff=08-06, horizon=3: Zeilen mit Label ueber den Cutoff hinaus
        # sind 08-04 (Label -> 08-07) und 08-05 (Label -> 08-08) - genau
        # horizon_days-1=2 Tage, NICHT horizon_days=3 Tage (08-03 hat ein
        # Label das genau am Cutoff endet, 08-03+3=08-06 - das ist noch
        # KEIN Blick in die Zukunft DES Cutoffs, bleibt also drin).
        train = self._train()
        result = _apply_embargo(train, pd.Timestamp("2026-08-06"), horizon_days=3)
        self.assertEqual(
            list(result["date"].dt.date.astype(str)),
            ["2026-08-01", "2026-08-02", "2026-08-03"],
        )


class ScoreCountsFromArraysTests(unittest.TestCase):
    def test_counts_match_hand_computation(self):
        y_actual = [100, -50, 30, -10]
        y_pred = [80, -60, -5, -20]  # Zeile 3 (30 vs -5) hat falsches Vorzeichen
        baseline_pred = [90, 40, 30, -5]  # Zeile 2 (-50 vs 40) hat falsches Vorzeichen
        counts = _score_counts_from_arrays(y_actual, y_pred, baseline_pred)
        self.assertEqual(counts["n"], 4)
        self.assertEqual(counts["sign_correct"], 3)  # alle bis auf Zeile 3
        self.assertEqual(counts["n_baseline"], 4)
        self.assertEqual(counts["baseline_sign_correct"], 3)  # alle bis auf Zeile 2
        self.assertEqual(counts["n_baseline_wrong"], 1)
        # Zeile 2: Modell richtig (-50 vs -60, beide negativ), Baseline falsch
        self.assertEqual(counts["model_sign_correct_when_baseline_wrong"], 1)
        self.assertAlmostEqual(counts["abs_error_sum"], 20 + 10 + 35 + 10, places=5)
        # abs_error_sum_given_correct_sign: Zeilen 1,2,4 (Zeile 3 hat falsches Vorzeichen)
        self.assertAlmostEqual(counts["abs_error_sum_given_correct_sign"], 20 + 10 + 10, places=5)


class FinalizeScoreCountsTests(unittest.TestCase):
    def test_derives_rounded_percentages(self):
        counts = {
            "n": 4, "sign_correct": 3, "abs_error_sum": 75.0,
            "abs_error_sum_given_correct_sign": 40.0,
            "n_baseline": 4, "baseline_sign_correct": 3, "baseline_abs_error_sum": 90.0,
            "n_baseline_wrong": 1, "model_sign_correct_when_baseline_wrong": 1,
        }
        result = _finalize_score_counts(counts)
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["sign_accuracy"], 75.0)
        self.assertAlmostEqual(result["mae"], 18.75, places=2)
        self.assertAlmostEqual(result["mae_given_correct_sign"], 40.0 / 3, places=2)
        self.assertEqual(result["baseline_sign_accuracy"], 75.0)
        self.assertAlmostEqual(result["baseline_mae"], 22.5, places=2)
        self.assertEqual(result["reversal_sign_accuracy"], 100.0)
        self.assertEqual(result["reversal_n"], 1)

    def test_returns_none_when_n_zero(self):
        self.assertIsNone(_finalize_score_counts(_empty_counts()))

    def test_reversal_and_correct_sign_fields_are_none_when_denominator_zero(self):
        counts = _empty_counts()
        counts["n"] = 2
        counts["sign_correct"] = 0
        counts["abs_error_sum"] = 10.0
        counts["n_baseline"] = 0
        result = _finalize_score_counts(counts)
        self.assertIsNone(result["mae_given_correct_sign"])
        self.assertIsNone(result["baseline_sign_accuracy"])
        self.assertIsNone(result["baseline_mae"])
        self.assertIsNone(result["reversal_sign_accuracy"])
        self.assertEqual(result["reversal_n"], 0)


class EngineerFeaturesUnclippedTargetTests(unittest.TestCase):
    def test_mv_target_columns_are_not_clipped(self):
        # Ein Ausreisser-Sprung darf NICHT mehr geklippt werden - Clipping
        # passiert jetzt erst beim Training, pro Split/Fold.
        rows = []
        pid, tid = "p1", "t1"
        for i, mv in enumerate([1_000_000, 1_000_000, 1_000_000, 50_000_000]):
            rows.append({
                "player_id": pid, "team_id": tid, "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "mv": mv, "md": pd.NaT, "p": None, "mp": None, "mp_avg_3": None,
                "t1": tid, "t2": None, "t1g": None, "t2g": None,
            })
        df = pd.DataFrame(rows)
        history_df, _today_df = _engineer_features(df)
        self.assertIn("mv_target", history_df.columns)
        self.assertNotIn("mv_target_clipped", history_df.columns)
        self.assertNotIn("mv_target_3d_clipped", history_df.columns)
```

- [ ] **Step 2: Tests laufen lassen, rot bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k "ClipTarget or ApplyEmbargo or ScoreCountsFromArrays or FinalizeScoreCounts or EngineerFeaturesUnclippedTarget"`
Expected: FAIL - `_clip_target`/`_apply_embargo`/`_score_counts_from_arrays`/`_finalize_score_counts`/`_empty_counts` existieren noch nicht (`NameError`/`ImportError`), `mv_target_clipped` existiert noch.

- [ ] **Step 3: Konstanten umbenennen, `_engineer_features` ändern, neue Helfer schreiben**

In `src/market_predictor.py`, Zeile 73-74 ändern von:
```python
TARGET = "mv_target_clipped"
TARGET_3D = "mv_target_3d_clipped"
```
zu:
```python
TARGET = "mv_target"
TARGET_3D = "mv_target_3d"
```

Nach Zeile 98 (`SENTIMENT_WINDOW_DAYS = 7`) neue Konstante einfügen:
```python
# Baseline-Vorhersage fuer den jeweiligen Horizont: "morgen bewegt sich der
# Marktwert in dieselbe Richtung/Groesse wie der zuletzt bekannte Schritt
# derselben Laenge" - beide Spalten existieren schon als Features, kein
# neuer Fetch, kein neues Leck-Risiko (live verifiziert 2026-08-04: diese
# triviale Baseline trifft ueber die ganze Saison 90-99% Richtungsgenauigkeit,
# das ML-Modell muss das schlagen, um seinen Aufwand zu rechtfertigen -
# siehe docs/superpowers/specs/2026-08-04-ml-baseline-honesty-design.md).
_BASELINE_COLUMN_BY_HORIZON: dict[int, str] = {1: "mv_change_1d", 3: "mv_change_3d"}
```

In `_engineer_features()` (aktuell Zeilen 449-457), den globalen Clip-Block
KOMPLETT entfernen:
```python
    q1 = df["mv_target"].quantile(0.25)
    q3 = df["mv_target"].quantile(0.75)
    iqr = q3 - q1
    df["mv_target_clipped"] = df["mv_target"].clip(q1 - 2.5 * iqr, q3 + 2.5 * iqr)

    q1_3d = df["mv_target_3d"].quantile(0.25)
    q3_3d = df["mv_target_3d"].quantile(0.75)
    iqr_3d = q3_3d - q1_3d
    df["mv_target_3d_clipped"] = df["mv_target_3d"].clip(q1_3d - 2.5 * iqr_3d, q3_3d + 2.5 * iqr_3d)
```
(diese 8 Zeilen ersatzlos löschen - Begründung als Kommentar an der Stelle,
wo `mv_target`/`mv_target_3d` gesetzt werden, ergänzen: `# Bewusst UNGEKLIPPT
- Clipping passiert erst beim Training, pro Train-Split/-Fold (siehe
_clip_target()), sonst kennen die Clip-Grenzen die Zukunft jedes
Backtest-Cutoffs (Ziel-Clip-Leck, live gefunden 2026-08-04).`)

Die `history_df.dropna(subset=[...])`-Zeile (aktuell Zeile 464-466) ändern
von:
```python
    history_df = history_df.dropna(
        subset=["mv_change_1d", "next_md", "days_to_next", "mv_next_day", "mv_target", "mv_target_clipped"]
    )
```
zu (redundanten Eintrag entfernen, `mv_target` ist schon drin):
```python
    history_df = history_df.dropna(
        subset=["mv_change_1d", "next_md", "days_to_next", "mv_next_day", "mv_target"]
    )
```

Nach `_build_candidates()` (nach Zeile 524), vier neue Funktionen einfügen:

```python
def _clip_target(unclipped: pd.Series) -> pd.Series:
    """IQR-Clip ueber die gegebene Serie. Aufrufer uebergeben NUR die
    Trainings-Teilmenge (nie den gesamten Corpus) - die Clip-Grenzen duerfen
    keine Information aus der Zukunft des jeweiligen Cutoffs/Splits
    enthalten (Ziel-Clip-Leck-Fix, live gefunden 2026-08-04)."""
    q1 = unclipped.quantile(0.25)
    q3 = unclipped.quantile(0.75)
    iqr = q3 - q1
    return unclipped.clip(q1 - 2.5 * iqr, q3 + 2.5 * iqr)


def _apply_embargo(train: pd.DataFrame, cutoff, horizon_days: int) -> pd.DataFrame:
    """Schliesst Trainings-Zeilen aus, deren Ziel-Label Marktwerte NACH dem
    Cutoff kennt (Data Leakage bei Mehrtage-Horizonten). Eine Zeile mit
    Datum d hat ein Label, das mv(d + horizon_days) nutzt - das ist ein Leck
    wenn d + horizon_days > cutoff, d.h. d > cutoff - horizon_days. Bei
    Tagesgranularitaet betrifft das genau horizon_days - 1 Tage vor dem
    Cutoff (NICHT horizon_days Tage - eine Zeile horizon_days Tage vor dem
    Cutoff hat ein Label, das GENAU am Cutoff endet, das ist noch kein
    Blick in dessen Zukunft). Bei horizon_days<=1 ist embargo ein No-Op:
    train enthaelt wegen train[date<cutoff] ohnehin keine Zeile, deren Label
    ueber den Cutoff hinausreicht."""
    if horizon_days <= 1:
        return train
    embargo_start = cutoff - pd.Timedelta(days=horizon_days - 1)
    return train[train["date"] < embargo_start]


def _score_counts_from_arrays(y_actual, y_pred, baseline_pred) -> dict:
    """Rohe Summen/Counter aus EINEM Batch (ein Fold oder ein Split) -
    absichtlich UNGERUNDET und nicht zu Prozent-Kennzahlen verdichtet, damit
    _walk_forward_backtest() mehrere Folds aufsummieren kann, BEVOR einmal
    (nicht pro Fold) _finalize_score_counts() aufgerufen wird - identisches
    Prinzip wie das bisherige sign_hits/abs_errors-Pooling, nur ueber Counts
    statt Rohlisten. `n_baseline` ist hier immer gleich `n` (baseline_pred
    kommt aus derselben, bereits NaN-gefilterten DataFrame-Zeile wie
    y_actual) - im Live-Tagespfad (_build_daily_accuracy_updates) kann
    n_baseline dagegen kleiner als n sein, wenn der Baseline-Lookup fehlt."""
    y_actual = np.asarray(y_actual, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    baseline_pred = np.asarray(baseline_pred, dtype=float)

    sign_correct = np.sign(y_actual) == np.sign(y_pred)
    baseline_sign_correct = np.sign(y_actual) == np.sign(baseline_pred)
    baseline_wrong = ~baseline_sign_correct
    abs_error = np.abs(y_actual - y_pred)

    return {
        "n": int(len(y_actual)),
        "sign_correct": int(sign_correct.sum()),
        "abs_error_sum": float(abs_error.sum()),
        "abs_error_sum_given_correct_sign": float(abs_error[sign_correct].sum()),
        "n_baseline": int(len(y_actual)),
        "baseline_sign_correct": int(baseline_sign_correct.sum()),
        "baseline_abs_error_sum": float(np.abs(y_actual - baseline_pred).sum()),
        "n_baseline_wrong": int(baseline_wrong.sum()),
        "model_sign_correct_when_baseline_wrong": int(sign_correct[baseline_wrong].sum()),
    }


def _empty_counts() -> dict:
    return {
        "n": 0, "sign_correct": 0, "abs_error_sum": 0.0,
        "abs_error_sum_given_correct_sign": 0.0,
        "n_baseline": 0, "baseline_sign_correct": 0, "baseline_abs_error_sum": 0.0,
        "n_baseline_wrong": 0, "model_sign_correct_when_baseline_wrong": 0,
    }


def _finalize_score_counts(counts: dict) -> dict | None:
    """Wandelt rohe Summen/Counter (aus _score_counts_from_arrays() ODER
    aufsummiert aus mehreren ml_accuracy_daily-Tagesdokumenten in
    _summarize_from_daily()) in die finalen, gerundeten Kennzahlen um -
    EINE Stelle fuer die Metrik-Definition, egal ob aus einem einzelnen
    Batch oder einem Zeitfenster ueber gespeicherte Tage berechnet. `None`
    bei n==0 (nichts zu berichten)."""
    n = counts["n"]
    if n == 0:
        return None
    sign_accuracy = counts["sign_correct"] / n * 100
    mae = counts["abs_error_sum"] / n
    mae_given_correct_sign = (
        counts["abs_error_sum_given_correct_sign"] / counts["sign_correct"]
        if counts["sign_correct"] else None
    )
    n_baseline = counts["n_baseline"]
    baseline_sign_accuracy = counts["baseline_sign_correct"] / n_baseline * 100 if n_baseline else None
    baseline_mae = counts["baseline_abs_error_sum"] / n_baseline if n_baseline else None
    n_baseline_wrong = counts["n_baseline_wrong"]
    reversal_sign_accuracy = (
        counts["model_sign_correct_when_baseline_wrong"] / n_baseline_wrong * 100
        if n_baseline_wrong else None
    )
    return {
        "n": n,
        "sign_accuracy": round(sign_accuracy, 1),
        "mae": round(mae, 2),
        "mae_given_correct_sign": round(mae_given_correct_sign, 2) if mae_given_correct_sign is not None else None,
        "baseline_sign_accuracy": round(baseline_sign_accuracy, 1) if baseline_sign_accuracy is not None else None,
        "baseline_mae": round(baseline_mae, 2) if baseline_mae is not None else None,
        "reversal_sign_accuracy": round(reversal_sign_accuracy, 1) if reversal_sign_accuracy is not None else None,
        "reversal_n": n_baseline_wrong,
    }
```

- [ ] **Step 4: Tests laufen lassen, grün bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k "ClipTarget or ApplyEmbargo or ScoreCountsFromArrays or FinalizeScoreCounts or EngineerFeaturesUnclippedTarget"`
Expected: PASS.

- [ ] **Step 5: Vollen Testlauf gegen Regressionen prüfen**

Run: `python -m pytest tests/test_market_predictor.py -v`
Expected: Alle bisherigen Tests bleiben grün AUSSER (bewusst, werden in
Task 2-4 behoben): Tests, die `mv_target_clipped`/`mv_target_3d_clipped`
referenzieren oder `_train_and_evaluate`/`_walk_forward_backtest`/
`backfill_prediction_log` direkt mit den alten Spaltennamen aufrufen. Notiere
welche das genau sind (für Task 2-4).

- [ ] **Step 6: Mutation-Check**

`_apply_embargo`: horizon_days-1-Grenze kurz auf `horizon_days` ändern,
`test_horizon_3_excludes_last_two_days_before_cutoff` muss rot werden
(erwartet dann `["2026-08-01", "2026-08-02"]` statt drei Einträge - Test
schlägt fehl weil er noch drei erwartet). Danach zurücksetzen. `_clip_target`
kurz `return unclipped` (No-Op) machen, `test_clips_using_only_given_series_quantiles`
muss rot werden. Danach zurücksetzen.

- [ ] **Step 7: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "ML: TARGET/TARGET_3D ungeklippt, Clip-Leck-Fix, Embargo-Helfer + Baseline-Score-Grundbausteine"
```

---

### Task 2: `_train_and_evaluate` — Embargo + Clip-Fix + Baseline-Kennzahlen

**Files:**
- Modify: `src/market_predictor.py:50` (Import), `:527-585` (`_train_and_evaluate`), `:1002` (Call-Site in `_train_and_track_horizon`)
- Test: `tests/test_market_predictor.py` (Klasse `TrainAndEvaluateTargetColTests`, Zeilen 879-918 laut aktuellem Stand)

**Interfaces:**
- Consumes: `_clip_target`, `_apply_embargo`, `_BASELINE_COLUMN_BY_HORIZON`, `_score_counts_from_arrays`, `_finalize_score_counts` (Task 1).
- Produces: `_train_and_evaluate(history_df, target_col=TARGET, horizon_days=1) -> tuple[dict, dict] | None` - `metrics["per_model"][name]` enthält jetzt zusätzlich zu `rmse`/`r2` alle Felder aus `_finalize_score_counts` (inkl. `sign_accuracy`, `mae`, `baseline_sign_accuracy`, ...). `mean_absolute_error`-Import wird nicht mehr gebraucht (MAE kommt jetzt aus `_finalize_score_counts`) - aus dem Import in Zeile 50 entfernen.

- [ ] **Step 1: Bestehende Fixture korrigieren**

`TrainAndEvaluateTargetColTests._history_df()` (Zeilen 880-898) hat eine
hart benannte Spalte `"mv_target_clipped"` (Zeile 895).
`test_default_target_col_is_backward_compatible` (Zeile 900-903) ruft
`_train_and_evaluate(df)` MIT DEM DEFAULT-`target_col` auf - der Default
ist nach Task 1 `TARGET = "mv_target"`, nicht mehr `"mv_target_clipped"` -
diese Spalte existiert in der Fixture nicht mehr unter dem neuen Namen,
der Test würde mit `KeyError` brechen. Ändere Zeile 895 von:
```python
            "mv_target_clipped": rng.randn(n) * 5000,
```
zu:
```python
            "mv_target": rng.randn(n) * 5000,
```
`"alt_target_clipped"` (Zeile 896, für die beiden anderen Tests mit
explizit übergebenem `target_col="alt_target_clipped"`) bleibt unverändert
- das ist ein beliebiger Parameterwert, an keine Spalten-Suffix-Konvention
mehr gebunden, funktioniert unter jedem Namen.

- [ ] **Step 2: `_train_and_evaluate` failing Test für Baseline-Feld schreiben**

In `tests/test_market_predictor.py`, nach der bestehenden `TrainAndEvaluateTargetColTests`-Klasse:

```python
class TrainAndEvaluateBaselineAndEmbargoTests(unittest.TestCase):
    def _history_df(self, n=250):
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rng = np.random.default_rng(42)
        return pd.DataFrame({
            "date": dates,
            "p": rng.normal(size=n),
            "mv": rng.normal(size=n) * 1000 + 1_000_000,
            "days_to_next": rng.integers(1, 7, size=n),
            "mv_change_1d": rng.normal(size=n) * 500,
            "mv_trend_1d": rng.normal(size=n) * 0.01,
            "mv_change_3d": rng.normal(size=n) * 800,
            "mv_vol_3d": rng.normal(size=n) * 100,
            "mv_trend_7d": rng.normal(size=n) * 0.02,
            "market_divergence": rng.normal(size=n) + 1,
            "days_since_last_status_change": rng.integers(0, 90, size=n),
            "status_change_count_90d": rng.integers(0, 5, size=n),
            "days_since_last_starting_rank_change": rng.integers(0, 90, size=n),
            "starting_rank_change_count_90d": rng.integers(0, 5, size=n),
            "avg_sentiment_7d": rng.normal(size=n) * 0.1,
            "news_volume_7d": rng.integers(0, 10, size=n),
            TARGET: rng.normal(size=n) * 500,
        })

    def test_per_model_metrics_include_baseline_fields(self):
        result = _train_and_evaluate(self._history_df(), TARGET, horizon_days=1)
        self.assertIsNotNone(result)
        _models, metrics = result
        for name in ("RandomForest", "HistGradientBoosting"):
            self.assertIn("baseline_sign_accuracy", metrics["per_model"][name])
            self.assertIn("reversal_n", metrics["per_model"][name])

    def test_embargoes_last_two_days_before_split_for_horizon_3(self):
        # horizon_days=3 mit derselben Fixture darf nicht crashen und muss
        # denselben Embargo-Mechanismus wie die anderen Aufrufer nutzen -
        # verifiziert hier nur "laeuft durch, produziert Metriken", der
        # exakte Embargo-Mechanismus selbst ist in ApplyEmbargoTests (Task 1)
        # abgedeckt.
        df = self._history_df()
        df[TARGET_3D] = df[TARGET] * 1.5
        result = _train_and_evaluate(df, TARGET_3D, horizon_days=3)
        self.assertIsNotNone(result)
```

- [ ] **Step 3: Test laufen lassen, rot bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k TrainAndEvaluateBaselineAndEmbargo`
Expected: FAIL - `_train_and_evaluate()` akzeptiert noch kein `horizon_days`, `per_model`-Einträge haben noch keine Baseline-Felder.

- [ ] **Step 4: `_train_and_evaluate` umbauen**

In `src/market_predictor.py`, Zeile 50, `mean_absolute_error` aus dem Import entfernen:
```python
from sklearn.metrics import mean_squared_error, r2_score
```

`_train_and_evaluate` (Zeilen 527-585) komplett ersetzen durch:
```python
def _train_and_evaluate(history_df: pd.DataFrame, target_col: str = TARGET, horizon_days: int = 1):
    """Trainiert zwei Modell-Kandidaten per Zeit-Split (75/25, kein Shuffle,
    verhindert Data Leakage) - RandomForestRegressor gegen
    HistGradientBoostingRegressor. Gibt (models, metrics) oder None zurueck,
    wenn zu wenig Daten fuer einen sinnvollen Split/Training vorhanden sind.
    `models` enthaelt ALLE trainierten Kandidaten. `horizon_days` steuert
    zwei Dinge: welche Spalte als Traegheits-Baseline dient
    (_BASELINE_COLUMN_BY_HORIZON) und ob der Split-Rand embargoiert werden
    muss (_apply_embargo - bei Mehrtage-Horizonten hat eine Trainings-Zeile
    kurz vor split_date sonst ein Label, das Marktwerte NACH split_date
    kennt, exakt dieselbe Leak-Klasse wie beim Walk-Forward-Backtest)."""
    df = history_df.dropna(subset=[target_col])
    if len(df) < MIN_TRAINING_ROWS:
        return None

    df = df.sort_values("date").reset_index(drop=True)
    split_idx = int(len(df) * 0.75)
    split_date = df["date"].iloc[split_idx]
    train = df[df["date"] < split_date]
    train = _apply_embargo(train, split_date, horizon_days)
    test = df[df["date"] >= split_date]

    if train.empty or test.empty:
        return None

    x_train = train[FEATURES]
    y_train = _clip_target(train[target_col])
    x_test = test[FEATURES]
    y_test_actual = test[target_col]
    baseline_pred = test[_BASELINE_COLUMN_BY_HORIZON[horizon_days]]

    candidates = _build_candidates()

    models: dict[str, object] = {}
    per_model_metrics: dict[str, dict] = {}
    for name, candidate in candidates.items():
        candidate.fit(x_train, y_train)
        y_pred = candidate.predict(x_test)
        r2 = r2_score(y_test_actual, y_pred)
        rmse = mean_squared_error(y_test_actual, y_pred) ** 0.5
        counts = _score_counts_from_arrays(y_test_actual, y_pred, baseline_pred)
        finalized = _finalize_score_counts(counts)
        models[name] = candidate
        per_model_metrics[name] = {"rmse": round(rmse, 2), "r2": round(r2, 3), **finalized}

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

In `_train_and_track_horizon` (Zeile 1002), Call-Site anpassen:
```python
    trained = _train_and_evaluate(history_df, target_col, horizon_days)
```

- [ ] **Step 5: Tests laufen lassen, grün bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k "TrainAndEvaluate"`
Expected: PASS (sowohl die neue Klasse als auch die bestehende
`TrainAndEvaluateTargetColTests`).

- [ ] **Step 6: Vollen Testlauf, Mutation-Check, Commit**

Run: `python -m pytest tests/test_market_predictor.py -v` (nur noch
Task-3/4-bezogene Tests dürfen jetzt noch rot sein, siehe Notiz aus Task 1
Step 5).

Mutation-Check: in `_train_and_evaluate`, `_apply_embargo(train, split_date, horizon_days)`
kurz durch `train` (ohne Embargo) ersetzen -
`test_embargoes_last_two_days_before_split_for_horizon_3` darf dabei NICHT
rot werden (der Test prüft nur "läuft durch", nicht den Embargo-Effekt
selbst - falls das auffällt, ist das ok, der Embargo-Mechanismus selbst ist
schon in Task 1 mutation-verifiziert; hier nur sicherstellen, dass die neue
horizon_days-Verdrahtung selbst nicht versehentlich weggelassen wurde, z.B.
indem `horizon_days` kurz hart auf `1` gesetzt wird und geprüft wird, dass
dann `_BASELINE_COLUMN_BY_HORIZON[1]` statt `[3]` genutzt würde - ein
Bug hier würde bei horizon_days=3 einen KeyError werfen, nicht leise
falsche Werte produzieren, das ist der eigentliche Schutz).

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "ML: _train_and_evaluate mit Embargo + Baseline-/Trendwende-Kennzahlen"
```

---

### Task 3: `_walk_forward_backtest` — Embargo + Clip-Fix + gepoolte Baseline-Kennzahlen

**Files:**
- Modify: `src/market_predictor.py:588-659`, `:1008` (Call-Site)
- Test: `tests/test_market_predictor.py` (Klasse `WalkForwardBacktestTargetColTests`, Zeilen 919-969 laut aktuellem Stand)

**Interfaces:**
- Consumes: dieselben Helfer wie Task 2.
- Produces: `_walk_forward_backtest(history_df, target_col=TARGET, horizon_days=1) -> {"n_folds": int, "per_model": {name: {...alle Felder aus _finalize_score_counts}}} | None`.

- [ ] **Step 1: Bestehenden NaN-Test migrieren + neuen Baseline-Test hinzufügen (failing zuerst)**

`WalkForwardBacktestTargetColTests._history_df()` (aktuell Zeilen 920-938)
hat exakt dasselbe `unclipped_col`-Muster wie
`BackfillPredictionLogTargetColTests` (Task 4) - `target_col` ist jetzt die
einzige (ungeklippte) Zielspalte. Ändere `_history_df` (Zeilen 921-938) zu:
```python
    def _history_df(self, target_col, n=210):
        import numpy as np
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rng = np.random.RandomState(7)
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            "avg_sentiment_7d": 0, "news_volume_7d": 0,
            target_col: rng.randn(n) * 5000,
        })
        return df
```

In `test_partial_nan_test_rows_are_dropped_not_averaged_into_nan` (Zeilen
940-969), Zeilen 947-955 ändern von:
```python
        target_col = "alt_target_clipped"
        unclipped_col = "alt_target"
        df = self._history_df(target_col)
        extra_row = df.iloc[[-1]].copy()
        extra_row["player_id"] = "p2"
        extra_row[unclipped_col] = None
        df = pd.concat([df, extra_row], ignore_index=True)
```
zu:
```python
        target_col = "alt_target"
        df = self._history_df(target_col)
        extra_row = df.iloc[[-1]].copy()
        extra_row["player_id"] = "p2"
        extra_row[target_col] = None
        df = pd.concat([df, extra_row], ignore_index=True)
```
(Rest der Methode - `_walk_forward_backtest(df, target_col=target_col)`,
`self.assertEqual(result["n_folds"], 6)`, `model_metrics["n"] == 6` -
bleibt unverändert, referenziert bereits die richtigen Keys.)

Füge eine neue Testmethode in derselben Klasse hinzu:
```python
    def test_per_model_metrics_include_baseline_fields(self):
        result = _walk_forward_backtest(self._history_df("alt_target"), target_col="alt_target", horizon_days=1)
        self.assertIsNotNone(result)
        for name in result["per_model"]:
            self.assertIn("baseline_sign_accuracy", result["per_model"][name])
            self.assertIn("reversal_n", result["per_model"][name])
```

- [ ] **Step 2: Tests laufen lassen, rot bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k WalkForwardBacktest`
Expected: FAIL - `unclipped_col`-Referenz wirft `AttributeError`/`KeyError`
(Spalte existiert nicht mehr), Baseline-Felder fehlen.

- [ ] **Step 3: `_walk_forward_backtest` umbauen**

Komplett ersetzen (Zeilen 588-659) durch:
```python
def _walk_forward_backtest(history_df: pd.DataFrame, target_col: str = TARGET, horizon_days: int = 1) -> dict | None:
    """Beantwortet direkt "wie waere die Prognose damals gewesen" - Training
    nur auf Zeilen VOR dem Cutoff (minus Embargo bei Mehrtage-Horizonten,
    siehe _apply_embargo), Test auf den Zeilen GENAU am Cutoff, verglichen
    gegen den tatsaechlichen (ungeklippten) Marktwert-Sprung UND gegen die
    Traegheits-Baseline. Poolt die rohen Counts JEDES Folds/Modells zu genau
    EINEM finalen _finalize_score_counts()-Aufruf pro Modell - mathematisch
    identisch zum vorherigen Verhalten (alle Rohwerte sammeln, am Ende
    einmal aggregieren, NICHT ein Schnitt aus gerundeten Pro-Fold-Prozenten,
    der Rundungsfehler aufsummieren wuerde)."""
    dates = sorted(history_df["date"].unique())
    if len(dates) <= BACKTEST_FOLDS:
        return None
    cutoffs = dates[-BACKTEST_FOLDS:]
    baseline_col = _BASELINE_COLUMN_BY_HORIZON[horizon_days]

    pooled_counts: dict[str, dict] = {}
    folds_run = 0
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff].dropna(subset=[target_col])
        train = _apply_embargo(train, cutoff, horizon_days)
        test = history_df[history_df["date"] == cutoff].dropna(subset=[target_col])
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train = train[FEATURES]
        y_train = _clip_target(train[target_col])
        x_test = test[FEATURES]
        y_test_actual = test[target_col]
        baseline_pred = test[baseline_col]

        # _build_candidates() statt eigener Kopie - vorher hatte dieser
        # Backtest eigene, von der echten Live-Prognose abweichende
        # Parameter, genau die Inkonsistenz-Klasse, die _build_candidates()s
        # Docstring schon fuer den Backfill-Pfad beschreibt.
        candidates = _build_candidates()
        for name, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            counts = _score_counts_from_arrays(y_test_actual, y_pred, baseline_pred)
            existing = pooled_counts.setdefault(name, _empty_counts())
            for key in existing:
                existing[key] += counts[key]

    if not folds_run:
        return None

    per_model = {}
    for name, counts in pooled_counts.items():
        finalized = _finalize_score_counts(counts)
        if finalized is not None:
            per_model[name] = finalized
    if not per_model:
        return None
    return {"n_folds": folds_run, "per_model": per_model}
```

In `_train_and_track_horizon` (Zeile 1008), Call-Site anpassen:
```python
    backtest = _walk_forward_backtest(history_df, target_col, horizon_days)
```

- [ ] **Step 4: Tests laufen lassen, grün bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k WalkForwardBacktest`
Expected: PASS.

- [ ] **Step 5: Vollen Testlauf, Mutation-Check, Commit**

Run: `python -m pytest tests/test_market_predictor.py -v` (nur noch
Task-4-bezogene Tests dürfen jetzt noch rot sein).

Mutation-Check: `_apply_embargo(train, cutoff, horizon_days)`-Zeile kurz
durch `train` ersetzen (Embargo weg) - falls ein Test in dieser Klasse das
NICHT auffängt, einen gezielten Regressionstest ergänzen, der bei
`horizon_days=3` mit einer Fixture, deren letzte 2 Tage vor einem Cutoff ein
extrem abweichendes Label haben, prüft, dass sich `sign_accuracy` mit vs.
ohne Embargo unterscheidet (roter Test ohne den Fix, grün mit dem Fix).

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "ML: _walk_forward_backtest mit Embargo + gepoolten Baseline-/Trendwende-Kennzahlen"
```

---

### Task 4: `backfill_prediction_log` — Embargo + Clip-Fix + Pro-Tag-Baseline-Kennzahlen

**Files:**
- Modify: `src/market_predictor.py:662-756`
- Test: `tests/test_market_predictor.py` (Klasse `BackfillPredictionLogTargetColTests`, Zeilen 296-361 laut aktuellem Stand)

**Interfaces:**
- Consumes: dieselben Helfer wie Task 2/3.
- Produces: `backfill_prediction_log(days=90, target_col=TARGET, horizon_days=1) -> {"folds_run": int, "days_written": int}` - jedes geschriebene `ml_accuracy_daily`-Dokument enthält jetzt zusätzlich zu `n`/`sign_correct`/`abs_error_sum` die 6 neuen rohen Felder aus `_score_counts_from_arrays` (`abs_error_sum_given_correct_sign`, `n_baseline`, `baseline_sign_correct`, `baseline_abs_error_sum`, `n_baseline_wrong`, `model_sign_correct_when_baseline_wrong`).

- [ ] **Step 1: Bestehenden NaN-Test migrieren + neuen Baseline-Test hinzufügen (failing zuerst)**

`BackfillPredictionLogTargetColTests._history_df()` (aktuell Zeilen
296-315) baut sowohl `target_col` als auch eine separate, unabhängig
zufällige `unclipped_col`-Spalte (`unclipped_col = target_col.removesuffix("_clipped")`).
Diese Trennung existiert nach dem Umbau nicht mehr - `target_col` IST jetzt
die einzige (ungeklippte) Zielspalte. Ändere `_history_df` (Zeilen 297-315)
zu:
```python
    def _history_df(self, target_col, n=210):
        import numpy as np
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rng = np.random.RandomState(7)
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            "avg_sentiment_7d": 0, "news_volume_7d": 0,
            target_col: rng.randn(n) * 5000,
        })
        return df
```

In `test_partial_nan_test_rows_are_dropped_not_averaged_into_nan` (Zeilen
325-360), Zeilen 333-338 ändern von:
```python
        target_col = "alt_target_clipped"
        unclipped_col = "alt_target"
        df = self._history_df(target_col)
        extra_row = df.iloc[[-1]].copy()
        extra_row["player_id"] = "p2"
        extra_row[unclipped_col] = None
```
zu:
```python
        target_col = "alt_target"
        df = self._history_df(target_col)
        extra_row = df.iloc[[-1]].copy()
        extra_row["player_id"] = "p2"
        extra_row[target_col] = None
```
(Rest der Methode - Aufruf, Assertions - bleibt unverändert, referenziert
bereits `entry["abs_error_sum"]`/`entry["n"]`, keine `unclipped_col`-Bezüge
mehr dort.)

Füge eine neue Testmethode in derselben Klasse hinzu, mit demselben
Mocking-Stil (identische `@patch`-Dekoratoren wie die bestehende Methode):
```python
    @patch("src.market_predictor.firestore_db.upsert_accuracy_daily")
    @patch("src.market_predictor.firestore_db.connect", return_value="fake_client")
    @patch("src.market_predictor._load_change_events_by_player", return_value={})
    @patch("src.market_predictor._build_corpus", return_value=None)
    @patch("src.market_predictor.get_me", return_value={"cpi": "1"})
    @patch("src.market_predictor.select_league", return_value={"id": "league1"})
    @patch("src.market_predictor.login", return_value=("token", {}, []))
    @patch("src.market_predictor._engineer_features")
    def test_daily_updates_include_baseline_fields(
        self, mock_engineer, mock_login, mock_select_league, mock_get_me,
        mock_build_corpus, mock_fitness_events, mock_connect, mock_upsert,
    ):
        target_col = "alt_target"
        df = self._history_df(target_col)
        mock_engineer.return_value = (df, pd.DataFrame())

        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "e", "KICKBASE_PASSWORD": "p", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ):
            result = backfill_prediction_log(3, target_col=target_col, horizon_days=1)

        self.assertGreater(result["folds_run"], 0)
        entries = mock_upsert.call_args[0][1]
        self.assertTrue(entries)
        for entry in entries:
            self.assertIn("baseline_sign_correct", entry)
            self.assertIn("n_baseline_wrong", entry)
            self.assertIn("model_sign_correct_when_baseline_wrong", entry)
```

- [ ] **Step 2: Tests laufen lassen, rot bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k BackfillPredictionLog`
Expected: FAIL.

- [ ] **Step 3: `backfill_prediction_log` umbauen**

In `src/market_predictor.py`, den Fold-Loop-Körper (aktuell ca. Zeilen
710-743) ersetzen. Vorher/Nachher-Kontext (Setup davor und Firestore-Write
danach bleiben unverändert):

```python
    dates = sorted(history_df["date"].unique())
    cutoffs = dates[-days:] if len(dates) > days else dates
    baseline_col = _BASELINE_COLUMN_BY_HORIZON[horizon_days]

    daily_updates = []
    folds_run = 0
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff].dropna(subset=[target_col])
        train = _apply_embargo(train, cutoff, horizon_days)
        test = history_df[history_df["date"] == cutoff].dropna(subset=[target_col])
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train = train[FEATURES]
        y_train = _clip_target(train[target_col])
        x_test = test[FEATURES]
        y_test_actual = test[target_col]
        baseline_pred = test[baseline_col]
        cutoff_date = pd.Timestamp(cutoff).date().isoformat()

        candidates = _build_candidates()
        for model_type, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            counts = _score_counts_from_arrays(y_test_actual, y_pred, baseline_pred)
            daily_updates.append({
                "date": cutoff_date, "model_type": model_type, "horizon_days": horizon_days,
                **counts,
            })
```

Entferne dabei den alten `unclipped_col = target_col.removesuffix("_clipped")`-
Docstring-Absatz bzw. passe ihn an (der Mechanismus existiert nicht mehr).

- [ ] **Step 4: Tests laufen lassen, grün bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k BackfillPredictionLog`
Expected: PASS.

- [ ] **Step 5: Vollen Testlauf, Mutation-Check, Commit**

Run: `python -m pytest tests/test_market_predictor.py -v` - JETZT müssen
ALLE Tests in dieser Datei grün sein (Task 1-4 zusammen decken alle
Umbau-Stellen ab).

Mutation-Check: analog Task 3.

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "ML: backfill_prediction_log mit Embargo + Pro-Tag-Baseline-Kennzahlen"
```

---

### Task 5: Live-Tagespfad — `_build_daily_accuracy_updates` + `_summarize_from_daily`

**Files:**
- Modify: `src/market_predictor.py:876-931` (`_build_daily_accuracy_updates`, `_summarize_from_daily`, `_realized_by_model_from_daily`)
- Test: `tests/test_market_predictor.py` (Klassen `BuildDailyAccuracyUpdatesTests`, `HorizonAwareAccuracyUpdatesTests`, `SummarizeFromDailyTests`, `RealizedByModelFromDailyTests`)

**Interfaces:**
- Consumes: `_finalize_score_counts` (Task 1). NICHT `_score_counts_from_arrays`
  (das ist Array-batch-basiert; dieser Pfad akkumuliert Skalar-für-Skalar
  über eine Liste von Log-Einträgen mit `mv_lookup`-Zugriff pro Zeile -
  andere Form, gleiche Formel).
- Produces: `ml_accuracy_daily`-Dokumente mit 6 neuen Feldern (siehe Task 4).
  `_summarize_from_daily(...) -> dict | None` liefert jetzt dieselben Felder
  wie `_finalize_score_counts` (statt nur `n`/`sign_accuracy`/`mae`).

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_market_predictor.py`, `BuildDailyAccuracyUpdatesTests`
erweitern um:
```python
    def test_baseline_fields_use_prior_horizon_window(self):
        entries = [
            {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100},
        ]
        mv_lookup = {
            ("p1", "2026-07-26"): 900.0,   # Tag davor (fuer Baseline: 1000-900=100)
            ("p1", "2026-07-27"): 1000.0,
            ("p1", "2026-07-28"): 1150.0,  # tatsaechlicher Sprung: +150
        }
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-29", horizon_days=1)
        self.assertEqual(len(result), 1)
        doc = result[0]
        self.assertEqual(doc["n_baseline"], 1)
        self.assertEqual(doc["baseline_sign_correct"], 1)  # Baseline +100, tatsaechlich +150, beide positiv
        self.assertAlmostEqual(doc["baseline_abs_error_sum"], 50.0)  # |100-150|
        self.assertEqual(doc["n_baseline_wrong"], 0)
        self.assertEqual(doc["abs_error_sum_given_correct_sign"], 50.0)  # Modell-Vorhersage 100 hat auch richtiges Vorzeichen

    def test_missing_prior_window_value_leaves_baseline_fields_at_zero(self):
        entries = [
            {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100},
        ]
        mv_lookup = {
            ("p1", "2026-07-27"): 1000.0,
            ("p1", "2026-07-28"): 1150.0,
            # kein Wert fuer 2026-07-26 (Tag davor) - Baseline nicht berechenbar
        }
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-29", horizon_days=1)
        self.assertEqual(result[0]["n_baseline"], 0)
        self.assertEqual(result[0]["n"], 1)  # Haupt-Metrik bleibt trotzdem auswertbar
```

`SummarizeFromDailyTests` erweitern um:
```python
    def test_derives_baseline_and_reversal_fields_from_summed_counts(self):
        daily = [
            {
                "date": "2026-07-27", "n": 2, "sign_correct": 2, "abs_error_sum": 100.0,
                "abs_error_sum_given_correct_sign": 100.0,
                "n_baseline": 2, "baseline_sign_correct": 1, "baseline_abs_error_sum": 200.0,
                "n_baseline_wrong": 1, "model_sign_correct_when_baseline_wrong": 1,
            },
        ]
        result = _summarize_from_daily(daily, "2026-07-28", 7)
        self.assertEqual(result["baseline_sign_accuracy"], 50.0)
        self.assertEqual(result["reversal_sign_accuracy"], 100.0)
        self.assertEqual(result["reversal_n"], 1)

    def test_old_shaped_daily_docs_without_new_fields_still_work(self):
        # Uebergangsphase zwischen Deploy und Backfill-Neulauf - reale, keine
        # hypothetische Situation (siehe Nach-Abschluss-Schritt im Plan).
        daily = [{"date": "2026-07-20", "n": 450, "sign_correct": 300, "abs_error_sum": 45000.0}]
        result = _summarize_from_daily(daily, "2026-07-28", 30)
        self.assertIsNone(result["baseline_sign_accuracy"])
        self.assertEqual(result["reversal_n"], 0)
```

- [ ] **Step 2: Tests laufen lassen, rot bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k "BuildDailyAccuracyUpdates or SummarizeFromDaily"`
Expected: FAIL - neue Felder fehlen in Ergebnis-Dicts.

- [ ] **Step 3: `_build_daily_accuracy_updates` umbauen**

Ersetze die Funktion (aktuell Zeilen 876-915) durch:
```python
def _build_daily_accuracy_updates(recent_entries: list[dict], mv_lookup: dict, today: str, horizon_days: int) -> list[dict]:
    """Wertet alle in recent_entries bereits auswertbaren Eintraege aus und
    aggregiert sie zu EINEM Dokument pro (date, model_type) - inkl. der
    Traegheits-Baseline (Vorhersage = tatsaechlicher Sprung ueber das
    VORHERIGE horizon_days-Fenster, z.B. mv_change_1d/mv_change_3d am
    Ursprungs-Feature-Tag entspricht) und der Trendwende-Teilmenge (Tage, an
    denen die Baseline falsch lag). `n_baseline` kann kleiner als `n` sein,
    wenn der Marktwert des vorherigen Fensters in mv_lookup fehlt (z.B. ganz
    am Anfang der getrackten Historie eines Spielers) - eigener Nenner statt
    stillschweigend auf 0 zu fallen."""
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
        bucket = agg.setdefault(key, {
            "date": date, "model_type": model_type, "horizon_days": horizon_days,
            **_empty_counts(),
        })
        bucket["n"] += 1
        bucket["sign_correct"] += int(sign_correct)
        bucket["abs_error_sum"] += abs_error
        if sign_correct:
            bucket["abs_error_sum_given_correct_sign"] += abs_error

        prev_date = (datetime.date.fromisoformat(date) - datetime.timedelta(days=horizon_days)).isoformat()
        mv_prev = mv_lookup.get((entry["player_id"], prev_date))
        if mv_prev is not None:
            baseline_pred = mv_then - mv_prev
            baseline_sign_correct = bool(np.sign(baseline_pred) == np.sign(actual_delta))
            bucket["n_baseline"] += 1
            bucket["baseline_sign_correct"] += int(baseline_sign_correct)
            bucket["baseline_abs_error_sum"] += abs(baseline_pred - actual_delta)
            if not baseline_sign_correct:
                bucket["n_baseline_wrong"] += 1
                if sign_correct:
                    bucket["model_sign_correct_when_baseline_wrong"] += 1
    return list(agg.values())
```

- [ ] **Step 4: `_summarize_from_daily` umbauen**

Ersetze die Funktion (aktuell Zeilen 861-873) durch:
```python
def _summarize_from_daily(daily_docs: list[dict], today: str, days: int) -> dict | None:
    """Wie zuvor, aber summiert jetzt auch die 6 Baseline-/Trendwende-Felder
    ueber das Fenster und uebergibt alles an _finalize_score_counts() - EINE
    Stelle fuer die Metrik-Definition, ob aus einem einzelnen Batch (siehe
    _score_counts_from_arrays()) oder aus vielen gespeicherten Tagen
    berechnet. `.get(feld, 0)` fuer die neuen Felder: echte, keine
    hypothetische Uebergangsphase zwischen Deploy und dem manuellen
    Backfill-Neulauf, in der aeltere Tages-Dokumente diese Felder noch
    nicht haben."""
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    window = [d for d in daily_docs if d["date"] >= cutoff]
    counts = {
        "n": sum(d["n"] for d in window),
        "sign_correct": sum(d["sign_correct"] for d in window),
        "abs_error_sum": sum(d["abs_error_sum"] for d in window),
        "abs_error_sum_given_correct_sign": sum(d.get("abs_error_sum_given_correct_sign", 0.0) for d in window),
        "n_baseline": sum(d.get("n_baseline", 0) for d in window),
        "baseline_sign_correct": sum(d.get("baseline_sign_correct", 0) for d in window),
        "baseline_abs_error_sum": sum(d.get("baseline_abs_error_sum", 0.0) for d in window),
        "n_baseline_wrong": sum(d.get("n_baseline_wrong", 0) for d in window),
        "model_sign_correct_when_baseline_wrong": sum(d.get("model_sign_correct_when_baseline_wrong", 0) for d in window),
    }
    return _finalize_score_counts(counts)
```

Prüfe `_realized_by_model_from_daily` (Zeilen 918-931) - ruft nur
`_summarize_from_daily` pro Fenster auf, braucht KEINE Änderung (das
erweiterte Rückgabe-Dict fließt automatisch durch).

- [ ] **Step 5: Tests laufen lassen, grün bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -v -k "BuildDailyAccuracyUpdates or SummarizeFromDaily or RealizedByModelFromDaily or HorizonAwareAccuracyUpdates"`
Expected: PASS - **inklusive der bereits bestehenden, unveränderten Tests**
(`test_aggregates_over_window` mit dem alten `n`/`sign_accuracy`-Format muss
weiterhin exakt dieselben Werte liefern).

- [ ] **Step 6: Vollen Testlauf, Mutation-Check, Commit**

Run: `python -m pytest tests/test_market_predictor.py -v`
Expected: ALLE Tests der Datei grün.

Mutation-Check: in `_build_daily_accuracy_updates`, die
`prev_date`-Berechnung kurz auf `date` selbst (statt `date - horizon_days`)
setzen - `test_baseline_fields_use_prior_horizon_window` muss rot werden.

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "ML: Live-Tagespfad (Firestore ml_accuracy_daily) mit Baseline-/Trendwende-Feldern"
```

---

### Task 6: Frontend — `types.ts` + `derive.ts`

**Files:**
- Modify: `frontend/src/types.ts:86-117` (oder aktuelle Zeilen zum Zeitpunkt der Umsetzung - vor dem Schreiben verifizieren)
- Modify: `frontend/src/lib/derive.ts`
- Test: `frontend/src/lib/derive.test.ts`

**Interfaces:**
- Consumes: Backend liefert die Felder 1:1 (Task 5).
- Produces: `MlRealizedWindow` (erweitert), `MlPerModelMetrics` (erweitert),
  `mlBaselineDeltaPct(realized: MlRealizedWindow | null | undefined): number | null`.

- [ ] **Step 1: Failing Vitest-Test schreiben**

In `frontend/src/lib/derive.test.ts` (am Ende anfügen):
```ts
describe("mlBaselineDeltaPct", () => {
  it("gibt die Differenz Modell- minus Baseline-Trefferquote in Prozentpunkten zurueck", () => {
    const realized = { n: 10, sign_accuracy: 75, mae: 100, mae_given_correct_sign: 80,
      baseline_sign_accuracy: 60, baseline_mae: 120, reversal_sign_accuracy: 50, reversal_n: 2 };
    expect(mlBaselineDeltaPct(realized)).toBeCloseTo(15, 5);
  });

  it("gibt null zurueck wenn keine Baseline-Daten vorhanden sind", () => {
    const realized = { n: 10, sign_accuracy: 75, mae: 100, mae_given_correct_sign: null,
      baseline_sign_accuracy: null, baseline_mae: null, reversal_sign_accuracy: null, reversal_n: 0 };
    expect(mlBaselineDeltaPct(realized)).toBeNull();
  });

  it("gibt null zurueck bei fehlendem realized-Objekt", () => {
    expect(mlBaselineDeltaPct(null)).toBeNull();
    expect(mlBaselineDeltaPct(undefined)).toBeNull();
  });
});
```
(Import von `mlBaselineDeltaPct` und `MlRealizedWindow` am Dateikopf
ergänzen, entsprechend dem bestehenden Import-Stil dieser Test-Datei.)

- [ ] **Step 2: Test laufen lassen, rot bestätigen**

Run: `cd frontend && npx vitest run derive.test.ts -t mlBaselineDeltaPct`
Expected: FAIL - `mlBaselineDeltaPct` existiert nicht, TS-Compile-Fehler.

- [ ] **Step 3: `types.ts` erweitern**

Lies den aktuellen Stand von `MlPerModelMetrics`/`MlRealizedWindow` in
`frontend/src/types.ts` (Zeilen ~86-117 laut letztem Stand, vor dem
Schreiben gegen die echte Datei verifizieren, Task 2-5 könnten die
Zeilennummern nicht verschoben haben, aber sicherheitshalber prüfen). Ändere:
```ts
export interface MlPerModelMetrics {
  rmse: number; mae: number; r2: number; sign_accuracy: number;
  mae_given_correct_sign: number | null;
  baseline_sign_accuracy: number | null;
  baseline_mae: number | null;
  reversal_sign_accuracy: number | null;
  reversal_n: number;
}
export interface MlRealizedWindow {
  n: number; sign_accuracy: number; mae: number;
  mae_given_correct_sign: number | null;
  baseline_sign_accuracy: number | null;
  baseline_mae: number | null;
  reversal_sign_accuracy: number | null;
  reversal_n: number;
}
```
(Rest der Interfaces - `MlMetrics`, `MlAccuracyTrendEntry` - unverändert.)

- [ ] **Step 4: `derive.ts` erweitern**

In `frontend/src/lib/derive.ts`, an einer thematisch passenden Stelle (z.B.
nahe anderen ML-bezogenen Ableitungen, falls vorhanden - sonst ans Ende):
```ts
import type { MlRealizedWindow } from "../types";

export function mlBaselineDeltaPct(realized: MlRealizedWindow | null | undefined): number | null {
  if (!realized || realized.baseline_sign_accuracy == null) return null;
  return realized.sign_accuracy - realized.baseline_sign_accuracy;
}
```
(Falls `derive.ts` bereits einen `MlRealizedWindow`-Import hat oder anders
importiert, an den bestehenden Stil anpassen statt einen zweiten
Import-Block zu erzeugen.)

- [ ] **Step 5: Test laufen lassen, grün bestätigen**

Run: `cd frontend && npx vitest run derive.test.ts -t mlBaselineDeltaPct`
Expected: PASS.

- [ ] **Step 6: TypeScript-Build + vollen Vitest-Lauf prüfen**

Run: `cd frontend && npm run build && npx vitest run`
Expected: Build ohne TS-Fehler (bestätigt, dass keine andere Stelle mit den
alten, schmaleren Interfaces bricht), alle Vitest-Tests grün.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types.ts frontend/src/lib/derive.ts frontend/src/lib/derive.test.ts
git commit -m "Frontend: MlRealizedWindow/MlPerModelMetrics um Baseline-/Trendwende-Felder erweitert, mlBaselineDeltaPct-Ableitung"
```

---

### Task 7: Frontend — `MlGenauigkeitTab.tsx` Anzeige + neuer CT-Test

**Files:**
- Modify: `frontend/src/components/MlGenauigkeitTab.tsx:93-141` (`HeadToHeadBlock`)
- Create: `frontend/tests-ct/MlGenauigkeitTab.ct.tsx`

**Interfaces:**
- Consumes: `mlBaselineDeltaPct` (Task 6), `fmtAccPct` (lokal in dieser
  Datei, Zeilen 27-30, unverändert), `fmtNum` (aus `../format`, unverändert).

- [ ] **Step 1: Failing CT-Test schreiben**

Erstelle `frontend/tests-ct/MlGenauigkeitTab.ct.tsx`:
```tsx
import { test, expect } from "@playwright/experimental-ct-react";
import MlGenauigkeitTab from "../src/components/MlGenauigkeitTab";
import { buildFixtureSnapshot, FIXTURE_ML_METRICS, FIXTURE_ML_TREND } from "../src/test-fixtures/dashboardSnapshot.fixture";

test.describe("MlGenauigkeitTab - Baseline-/Trendwende-Anzeige", () => {
  test("zeigt Baseline-Delta, Trendwende-Trefferquote mit n, und MAE-bei-richtiger-Richtung", async ({ mount }) => {
    const metrics = {
      ...FIXTURE_ML_METRICS,
      realized_by_model: {
        RandomForest: {
          realized_30d: {
            n: 120, sign_accuracy: 72.5, mae: 25000,
            mae_given_correct_sign: 18000,
            baseline_sign_accuracy: 60.0, baseline_mae: 30000,
            reversal_sign_accuracy: 55.0, reversal_n: 18,
          },
          realized_7d: null,
        },
        HistGradientBoosting: {
          realized_30d: {
            n: 120, sign_accuracy: 70.0, mae: 26000,
            mae_given_correct_sign: 19000,
            baseline_sign_accuracy: 60.0, baseline_mae: 30000,
            reversal_sign_accuracy: 50.0, reversal_n: 18,
          },
          realized_7d: null,
        },
      },
    };
    const snapshot = buildFixtureSnapshot({ ml_metrics: metrics, ml_accuracy_trend: FIXTURE_ML_TREND });

    const component = await mount(<MlGenauigkeitTab data={snapshot} />);

    // Baseline-Delta: 72.5 - 60.0 = +12.5pp
    await expect(component.getByText(/\+12\.5%/)).toBeVisible();
    // Trendwende mit Stichprobengroesse
    await expect(component.getByText(/n=18/)).toBeVisible();
    await expect(component.getByText(/55\.0%/)).toBeVisible();
    // MAE bei richtiger Richtung
    await expect(component.getByText(/18000|18\.000|18,000/)).toBeVisible();
  });

  test("zeigt Traegheits-Baseline-Erklaertext am Ende der Sektion", async ({ mount }) => {
    const metrics = {
      ...FIXTURE_ML_METRICS,
      realized_by_model: {
        RandomForest: {
          realized_30d: {
            n: 5, sign_accuracy: 60.0, mae: 25000, mae_given_correct_sign: null,
            baseline_sign_accuracy: null, baseline_mae: null, reversal_sign_accuracy: null, reversal_n: 0,
          },
          realized_7d: null,
        },
        HistGradientBoosting: { realized_30d: null, realized_7d: null },
      },
    };
    const snapshot = buildFixtureSnapshot({ ml_metrics: metrics, ml_accuracy_trend: FIXTURE_ML_TREND });
    const component = await mount(<MlGenauigkeitTab data={snapshot} />);
    await expect(component.getByText(/Trägheits-Annahme/)).toBeVisible();
  });
});
```
(Komponenten-Signatur verifiziert: `export default function MlGenauigkeitTab({ data }: { data: DashboardSnapshot })`
- nur `data`, kein weiterer Prop.)

- [ ] **Step 2: Test laufen lassen, rot bestätigen**

Run (im Sandbox-Setup ggf. `LD_LIBRARY_PATH` für Chromium nötig, siehe
frühere Sessions/HANDOFF für den genauen Workaround):
```bash
cd frontend && npx playwright test -c playwright-ct.config.ts MlGenauigkeitTab.ct.tsx
```
Expected: FAIL - die neuen Texte/Zahlen existieren noch nicht in der
Komponente.

- [ ] **Step 3: `HeadToHeadBlock` erweitern**

In `frontend/src/components/MlGenauigkeitTab.tsx`, Import-Zeile 2 um die
neue Ableitung ergänzen (Datei-Kopf, Zeile 2 aktuell):
```ts
import type { BidPremiumOutcomeCounts, DashboardSnapshot, MlAccuracyTrendEntry, MlMetrics, MlModelType } from "../types";
```
wird zu (zusätzliche Zeile):
```ts
import { mlBaselineDeltaPct } from "../lib/derive";
```

Den Render-Block innerhalb `realized ? (...)` (aktuell Zeile 122-129)
ersetzen durch:
```tsx
                {realized ? (
                  <>
                    Richtung korrekt <b>{fmtAccPct(realized.sign_accuracy)}</b> · MAE <b>{fmtNum(realized.mae)}</b> · n={realized.n}
                    {realized.baseline_sign_accuracy != null && (
                      <>
                        {" "}
                        · ggü. Trägheits-Annahme{" "}
                        <b>
                          {mlBaselineDeltaPct(realized)! >= 0 ? "+" : ""}
                          {fmtAccPct(mlBaselineDeltaPct(realized)!)}
                        </b>
                      </>
                    )}
                    {realized.mae_given_correct_sign != null && (
                      <>
                        {" "}
                        · MAE bei richtiger Richtung <b>{fmtNum(realized.mae_given_correct_sign)}</b>
                      </>
                    )}
                    <br />
                    {realized.reversal_sign_accuracy != null ? (
                      <>
                        Bei Trendwenden (n={realized.reversal_n}): <b>{fmtAccPct(realized.reversal_sign_accuracy)}</b> richtig
                      </>
                    ) : (
                      <>Bei Trendwenden: noch keine Fälle im Fenster (n={realized.reversal_n})</>
                    )}
                  </>
                ) : (
                  "Noch keine abgeschlossenen Prognosen im 30-Tage-Fenster"
                )}
```

Den Erklärtext am Ende des Blocks (aktuell Zeile 135-138) ergänzen (NICHT
ersetzen, zusätzlich anfügen):
```tsx
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        "Trägheits-Annahme" = triviale Vergleichs-Prognose ("Richtung bleibt wie beim letzten bekannten Schritt
        derselben Länge") – zeigt, ob das Modell mehr kann als reine Markt-Trägheit. "Trendwenden" = Tage, an denen
        die Trägheits-Annahme falsch lag; MAE bei richtiger Richtung trennt Betragsgenauigkeit von Richtungsfehlern.
      </p>
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

Run: `cd frontend && npx playwright test -c playwright-ct.config.ts MlGenauigkeitTab.ct.tsx`
Expected: PASS.

- [ ] **Step 5: Dark-Mode-Gegencheck**

Per CLAUDE.md-Regel: neue Textfarben im Dark Mode prüfen. Die neuen
Elemente nutzen ausschließlich bereits im selben Block etablierte Klassen
(`text-slate-500 dark:text-slate-400`, `<b>` ohne eigene Farbklasse, erbt
umgebenden Text) - keine neue Farbklasse eingeführt, aber trotzdem einmal
per Dev-Server/Browser-Screenshot (hell + dunkel) visuell gegenprüfen, dass
nichts unlesbar ist.

- [ ] **Step 6: Vollen Frontend-Testlauf**

Run: `cd frontend && npm run build && npx vitest run && npx playwright test -c playwright-ct.config.ts`
Expected: Build clean, alle Vitest- und Playwright-CT-Tests grün (inkl. aller
bereits bestehenden - keine Regression durch die Typ-Erweiterung).

- [ ] **Step 7: Mutation-Check**

`mlBaselineDeltaPct(realized)!`-Aufruf im JSX kurz durch einen fest
verdrahteten Wert ersetzen (z.B. `"+0.0%"` statt der echten Berechnung) -
der erste CT-Test muss dabei rot werden (erwartet `+12.5%`).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/MlGenauigkeitTab.tsx frontend/tests-ct/MlGenauigkeitTab.ct.tsx
git commit -m "Frontend: MlGenauigkeitTab zeigt Baseline-Delta, Trendwende-Trefferquote+n, MAE-Split"
```

---

## Nach Abschluss (Haupt-Thread, kein Subagent)

1. PR erstellen (`gh pr create`), auto-merge aktivieren (`gh pr merge --auto --squash`), auf grüne Required Checks warten.
2. Nach Merge: Heavy-Lauf erzwingen (`gh workflow run dashboard-marktwerte.yml`) - CLAUDE.md-Pflicht nach Schema-Wechsel.
3. `backfill_prediction_log(days=90)` einmalig manuell laufen lassen (Skript-Datei im Repo-Root oder Scratchpad, `python3 datei.py` - kein inline `python3 -c`, das wird geblockt). Für BEIDE Horizonte (`horizon_days=1` und `horizon_days=3`, mit `target_col=TARGET_3D` für letzteren).
4. Alte vs. neue 3-Tage-Genauigkeit vergleichen (alte Werte aus `ml_accuracy_trend_3d`/`ml_metrics_3d` bereits aus dieser Session bekannt) - Ergebnis dem User explizit mitteilen, auch wenn's durch den Embargo-/Clip-Fix schlechter aussieht (CLAUDE.md-Pflicht, keine stille Korrektur einer bereits gezeigten Zahl).
5. `HANDOFF.md`: den Embargo-Bug-Eintrag (`market_predictor.py::_walk_forward_backtest() hat kein Embargo...`) und den in dieser Session dokumentierten Clip-Leck-Fund entfernen bzw. als erledigt markieren; ggf. Notiz zur neu bewerteten 3T-Zahl ergänzen; den `6b08e2cf`-Sentiment-Eintrag unverändert lassen (nicht Teil dieser Runde).
6. Firestore `feedback/current`: falls dieses Vorhaben aus einem konkreten Feedback-Item entstanden ist, dessen Status prüfen (in diesem Fall: kein einzelnes Item, User-initiierter Fokus-Wechsel im Chat - kein Firestore-Status zu setzen).
