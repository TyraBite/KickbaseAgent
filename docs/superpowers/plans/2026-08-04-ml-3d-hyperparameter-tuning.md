# 3-Tage-Modell: embargo-korrekte Hyperparameter-Suche Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `_walk_forward_backtest()` wiederverwendbar für eine externe Hyperparameter-Suche machen (ohne die
Embargo-/Scoring-Logik zu duplizieren), und ein einmaliges Such-Skript bauen, das den 3-Tage-Horizont
(`TARGET_3D`) gegen RandomForest/HistGradientBoosting/LightGBM/XGBoost-Kandidaten testet.

**Architecture:** `_walk_forward_backtest()` bekommt zwei neue optionale Parameter (`candidates`, `n_folds`),
Default-Verhalten für alle bestehenden Aufrufer bleibt exakt unverändert. Das neue Skript
`src/experiment_target3d_tuning.py` ruft dieselbe Funktion mit einem einzelnen Test-Kandidaten und `n_folds=30`
auf — keine zweite Kopie der Fold-/Embargo-/Scoring-Logik.

**Tech Stack:** Python, sklearn (bereits Produktions-Dependency), LightGBM/XGBoost (nur experimentell, separates
`.venv-tuning/`, bereits in `.gitignore`).

## Global Constraints

- Kommentare nur wo Logik nicht-offensichtlich ist. Modulinterne Funktionen mit führendem Unterstrich.
- Parametrisieren statt duplizieren — keine zweite Kopie derselben Berechnung.
- Strukturell gleiche Parameter als Keyword-Argument übergeben, wo bereits etabliert.
- Jeder Fix/jedes Feature braucht einen automatisierten Test, TDD (erst rot, dann grün), Mutation-Check —
  AUSNAHME: das Such-Skript selbst (`src/experiment_target3d_tuning.py`) ist ein einmaliges Experiment, kein
  Produktionscode, etabliertes Repo-Muster ohne automatisierte Tests (siehe `git log` für vorherige
  `experiment_*.py`-Dateien). Task 1 (Produktionscode-Änderung) braucht sehr wohl Tests.
- Bestehende, unveränderte Tests müssen nach jedem Task weiterhin grün sein.
- `python -m pytest` (nicht bares `pytest`).
- Diese Suche deckt NUR `horizon_days=3` ab, nicht `horizon_days=1` (bereits separat getunt, siehe
  `_build_candidates()`-Docstring).

---

## Task 1: `_walk_forward_backtest()` um `candidates`/`n_folds`-Overrides erweitern

**Files:**
- Modify: `src/market_predictor.py:701-745` (Funktion `_walk_forward_backtest`)
- Test: `tests/test_market_predictor.py` (Klasse `WalkForwardBacktestTargetColTests`, ab Zeile 1143)

**Interfaces:**
- Produziert: `_walk_forward_backtest(history_df, target_col=TARGET, horizon_days=1, candidates=None,
  n_folds=None) -> dict | None` — bei `candidates=None` identisch zum bisherigen Verhalten (`_build_candidates()`
  wird pro Fold neu aufgerufen); bei `n_folds=None` identisch zum bisherigen `BACKTEST_FOLDS`-Wert (6).

- [ ] **Step 1: Zwei failing Tests schreiben**

In `tests/test_market_predictor.py`, innerhalb der Klasse `WalkForwardBacktestTargetColTests` (nutzt deren
bestehende `_history_df(self, target_col, n=210)`-Fixture), nach der letzten bestehenden Methode
(`test_embargo_is_actually_wired_into_the_backtest_for_horizon_3`) ergänzen:

```python
    def test_n_folds_override_changes_cutoff_count(self):
        df = self._history_df("alt_target")

        default_result = _walk_forward_backtest(df, target_col="alt_target")
        override_result = _walk_forward_backtest(df, target_col="alt_target", n_folds=10)

        self.assertIsNotNone(default_result)
        self.assertIsNotNone(override_result)
        self.assertEqual(default_result["n_folds"], 6)
        self.assertEqual(override_result["n_folds"], 10)

    def test_candidates_override_is_used_instead_of_build_candidates(self):
        from sklearn.dummy import DummyRegressor
        df = self._history_df("alt_target")
        trial_model = DummyRegressor(strategy="constant", constant=0.0)

        with patch("src.market_predictor._build_candidates") as mock_build:
            result = _walk_forward_backtest(
                df, target_col="alt_target", candidates={"Trial": trial_model},
            )

        mock_build.assert_not_called()
        self.assertIsNotNone(result)
        self.assertEqual(set(result["per_model"].keys()), {"Trial"})
```

- [ ] **Step 2: Tests laufen lassen, rot bestätigen**

Run: `python -m pytest tests/test_market_predictor.py -k "n_folds_override or candidates_override" -v`
Expected: FAIL — `_walk_forward_backtest() got an unexpected keyword argument 'candidates'` (bzw. `'n_folds'`).

- [ ] **Step 3: Funktion erweitern**

In `src/market_predictor.py`, Funktionssignatur (aktuell Zeile 701):

```python
def _walk_forward_backtest(history_df: pd.DataFrame, target_col: str = TARGET, horizon_days: int = 1) -> dict | None:
```

wird zu:

```python
def _walk_forward_backtest(
    history_df: pd.DataFrame,
    target_col: str = TARGET,
    horizon_days: int = 1,
    candidates: dict[str, object] | None = None,
    n_folds: int | None = None,
) -> dict | None:
```

Docstring (aktuell direkt darunter) um einen Satz ergänzen:

```python
    """Beantwortet direkt "wie waere die Prognose damals gewesen" - Training
    nur auf Zeilen VOR dem Cutoff (minus Embargo bei Mehrtage-Horizonten,
    siehe _apply_embargo), Test auf den Zeilen GENAU am Cutoff, verglichen
    gegen den tatsaechlichen (ungeklippten) Marktwert-Sprung UND gegen die
    Traegheits-Baseline. Poolt die rohen Counts JEDES Folds/Modells zu genau
    EINEM finalen _finalize_score_counts()-Aufruf pro Modell - mathematisch
    identisch zum vorherigen Verhalten (alle Rohwerte sammeln, am Ende
    einmal aggregieren, NICHT ein Schnitt aus gerundeten Pro-Fold-Prozenten,
    der Rundungsfehler aufsummieren wuerde). `candidates`/`n_folds` sind
    Overrides fuer externe Nutzung (Hyperparameter-Suche, siehe
    docs/superpowers/specs/2026-08-04-ml-3d-hyperparameter-tuning-design.md)
    - ohne sie ist das Verhalten fuer alle bestehenden Aufrufer unveraendert."""
```

Im Funktionskörper zwei Stellen ändern. Erstens, die Cutoff-Berechnung (aktuell):

```python
    dates = sorted(history_df["date"].unique())
    if len(dates) <= BACKTEST_FOLDS:
        return None
    cutoffs = dates[-BACKTEST_FOLDS:]
```

wird zu:

```python
    dates = sorted(history_df["date"].unique())
    folds_wanted = n_folds if n_folds is not None else BACKTEST_FOLDS
    if len(dates) <= folds_wanted:
        return None
    cutoffs = dates[-folds_wanted:]
```

Zweitens, innerhalb der `for cutoff in cutoffs:`-Schleife die Kandidaten-Zeile (aktuell):

```python
        # _build_candidates() statt eigener Kopie - vorher hatte dieser
        # Backtest eigene, von der echten Live-Prognose abweichende
        # Parameter, genau die Inkonsistenz-Klasse, die _build_candidates()s
        # Docstring schon fuer den Backfill-Pfad beschreibt.
        candidates = _build_candidates()
        for name, candidate in candidates.items():
```

wird zu:

```python
        # _build_candidates() statt eigener Kopie - vorher hatte dieser
        # Backtest eigene, von der echten Live-Prognose abweichende
        # Parameter, genau die Inkonsistenz-Klasse, die _build_candidates()s
        # Docstring schon fuer den Backfill-Pfad beschreibt. `candidates`-
        # Override (Hyperparameter-Suche) verwendet dieselbe(n) Instanz(en)
        # ueber alle Folds hinweg - .fit() trainiert bei RandomForest/
        # HistGradientBoosting/LightGBM/XGBoost jedes Mal komplett neu,
        # kein Zustand wird zwischen Folds mitgeschleppt.
        fold_candidates = candidates if candidates is not None else _build_candidates()
        for name, candidate in fold_candidates.items():
```

(Beachte: der Parameter heißt `candidates`, die lokale Variable in der Schleife jetzt `fold_candidates` - der
Parametername darf nicht durch die alte lokale Variable überschattet werden.)

- [ ] **Step 4: Tests laufen lassen, gruen bestaetigen**

Run: `python -m pytest tests/test_market_predictor.py -k "n_folds_override or candidates_override" -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Volle Testsuite laufen lassen (Regressionsschutz)**

Run: `python -m pytest tests/ -q`
Expected: alle bisherigen Tests weiterhin gruen (356 vorher + 2 neue = 358 passed) — insbesondere alle
bestehenden `WalkForwardBacktestTargetColTests`-Faelle, die die Funktion OHNE die neuen Parameter aufrufen,
duerfen sich nicht im Verhalten aendern.

- [ ] **Step 6: Mutation-Check**

Temporär `folds_wanted if n_folds is not None else BACKTEST_FOLDS` durch `BACKTEST_FOLDS` ersetzen (Override
faktisch ignorieren) - `test_n_folds_override_changes_cutoff_count` muss rot werden. Danach zurücknehmen und
grün bestätigen. Gleiches für `fold_candidates = candidates if candidates is not None else _build_candidates()`
→ `fold_candidates = _build_candidates()` (Override ignorieren) - `test_candidates_override_is_used_instead_of_build_candidates`
muss rot werden (weil `_build_candidates` dann doch aufgerufen wird). Danach zurücknehmen und grün bestätigen.

- [ ] **Step 7: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "ML: _walk_forward_backtest um candidates-/n_folds-Overrides erweitert"
```

---

## Task 2: Tuning-Skript fuer den 3-Tage-Horizont

**Files:**
- Create: `src/experiment_target3d_tuning.py`

**Interfaces:**
- Konsumiert: `_walk_forward_backtest` (Task 1, mit `candidates=`/`n_folds=`), `_build_candidates`, `_build_corpus`,
  `_engineer_features`, `_load_change_events_by_player`, `_load_news_events_by_player` (alle unveraendert aus
  `src/market_predictor.py`), `login`/`get_me`/`select_league` (aus `src/kickbase_client.py`).
- Produziert: nichts, was andere Tasks konsumieren - Endpunkt dieses Plans (reines Skript, kein Import-Ziel).

- [ ] **Step 1: `.venv-tuning` mit den zwei neuen experimentellen Dependencies aufsetzen**

```bash
python3 -m venv .venv-tuning
.venv-tuning/bin/pip install -r requirements.txt lightgbm xgboost
```

(`.venv-tuning/` ist bereits in `.gitignore` - kein neuer Eintrag noetig.)

- [ ] **Step 2: Skript schreiben**

Erstelle `src/experiment_target3d_tuning.py`:

```python
"""Einmaliges Experiment-Skript: embargo-korrekte Hyperparameter-Suche fuer
den 3-Tage-Horizont (TARGET_3D). Siehe
docs/superpowers/specs/2026-08-04-ml-3d-hyperparameter-tuning-design.md fuer
Kontext/Kriterium. Wird nach Gebrauch wieder geloescht (etabliertes
Repo-Muster fuer experiment_*.py) - kein Produktionscode, keine
automatisierten Tests."""

import os
import random
import time

from dotenv import load_dotenv

from src.kickbase_client import get_me, login, select_league
from src.market_predictor import (
    TARGET_3D,
    _build_corpus,
    _engineer_features,
    _load_change_events_by_player,
    _load_news_events_by_player,
    _walk_forward_backtest,
)

N_FOLDS = 30
HORIZON_DAYS = 3
TARGET_COL = TARGET_3D
CRITERION_ACCURACY_MARGIN_PT = 1
DEPENDENCY_MAE_THRESHOLD_PCT = 5
DEPENDENCY_ACCURACY_THRESHOLD_PT = 2


def _sample_random_forest():
    from sklearn.ensemble import RandomForestRegressor
    return RandomForestRegressor(
        n_estimators=random.choice([200, 300, 500, 800]),
        max_depth=random.choice([10, 15, 20, 25, 30, None]),
        min_samples_split=random.choice([2, 5, 10]),
        min_samples_leaf=random.choice([1, 2, 5, 10, 20]),
        max_features=random.choice(["sqrt", "log2", 0.5, 0.7]),
        n_jobs=-1,
        random_state=42,
    )


def _sample_hist_gradient_boosting():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(
        learning_rate=random.choice([0.01, 0.03, 0.05, 0.1]),
        max_iter=random.choice([100, 200, 300, 500]),
        max_leaf_nodes=random.choice([15, 31, 63, 127, 255]),
        min_samples_leaf=random.choice([10, 20, 30, 50]),
        l2_regularization=random.choice([0.0, 0.1, 1.0]),
        random_state=42,
    )


def _sample_lightgbm():
    from lightgbm import LGBMRegressor
    return LGBMRegressor(
        n_estimators=random.choice([100, 200, 300, 500]),
        learning_rate=random.choice([0.01, 0.03, 0.05, 0.1]),
        num_leaves=random.choice([15, 31, 63, 127]),
        min_child_samples=random.choice([10, 20, 30, 50]),
        reg_lambda=random.choice([0.0, 0.1, 1.0]),
        random_state=42,
        verbosity=-1,
    )


def _sample_xgboost():
    from xgboost import XGBRegressor
    return XGBRegressor(
        n_estimators=random.choice([100, 200, 300, 500]),
        learning_rate=random.choice([0.01, 0.03, 0.05, 0.1]),
        max_depth=random.choice([3, 5, 7, 9]),
        min_child_weight=random.choice([1, 5, 10, 20]),
        reg_lambda=random.choice([0.0, 0.1, 1.0]),
        random_state=42,
        verbosity=0,
    )


FAMILIES = {
    "RandomForest": _sample_random_forest,
    "HistGradientBoosting": _sample_hist_gradient_boosting,
    "LightGBM": _sample_lightgbm,
    "XGBoost": _sample_xgboost,
}
SKLEARN_FAMILIES = {"RandomForest", "HistGradientBoosting"}


def _print_metrics(label, metrics):
    print(
        f"{label}: sign_accuracy={metrics['sign_accuracy']}% mae={metrics['mae']} "
        f"reversal_sign_accuracy={metrics.get('reversal_sign_accuracy')} "
        f"reversal_n={metrics.get('reversal_n')} n={metrics['n']}"
    )


def main():
    load_dotenv()
    budget_hours = float(os.environ.get("TUNING_BUDGET_HOURS", "1.5"))
    email = os.environ["KICKBASE_EMAIL"]
    password = os.environ["KICKBASE_PASSWORD"]

    token, _user, leagues = login(email, password)
    league_id = select_league(leagues)["id"]
    me = get_me(token, league_id)
    competition_id = me.get("cpi") or "1"
    fitness_events = _load_change_events_by_player("fitness_history_log")
    starting_rank_events = _load_change_events_by_player("starting_rank_history_log")
    news_events = _load_news_events_by_player()
    corpus = _build_corpus(
        token, league_id, competition_id,
        fitness_events_by_player=fitness_events,
        starting_rank_events_by_player=starting_rank_events,
        news_events_by_player=news_events,
    )
    history_df, _today_df = _engineer_features(corpus)

    print(f"BASELINE (aktuelle _build_candidates()-Config, {N_FOLDS}-Fold, Embargo aktiv):")
    baseline_result = _walk_forward_backtest(
        history_df, target_col=TARGET_COL, horizon_days=HORIZON_DAYS, n_folds=N_FOLDS,
    )
    if baseline_result is None:
        print("Keine Baseline messbar (zu wenig Historie) - Abbruch.")
        return
    for name, metrics in baseline_result["per_model"].items():
        _print_metrics(f"BASELINE {name}", metrics)
    best_sklearn_baseline = min(baseline_result["per_model"].values(), key=lambda m: m["mae"])

    qualifying = []
    deadline = time.monotonic() + budget_hours * 3600
    last_config_seconds = 0.0
    trial_num = 0

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"Zeitbudget ({budget_hours}h) aufgebraucht - Suche wird beendet.")
            break
        if last_config_seconds and last_config_seconds * 1.3 > remaining:
            print(f"Sicherheitsmarge erreicht (Restbudget {remaining:.0f}s) - Suche wird sauber beendet.")
            break

        family = random.choice(list(FAMILIES.keys()))
        trial_model = FAMILIES[family]()
        trial_num += 1

        start = time.monotonic()
        result = _walk_forward_backtest(
            history_df, target_col=TARGET_COL, horizon_days=HORIZON_DAYS,
            candidates={family: trial_model}, n_folds=N_FOLDS,
        )
        last_config_seconds = time.monotonic() - start

        if result is None or family not in result["per_model"]:
            print(f"[{trial_num}] {family}: kein auswertbares Ergebnis (zu wenig Folds/Zeilen).")
            continue

        metrics = result["per_model"][family]
        meets_criterion = (
            metrics["sign_accuracy"] >= best_sklearn_baseline["sign_accuracy"] + CRITERION_ACCURACY_MARGIN_PT
            and metrics["mae"] <= best_sklearn_baseline["mae"]
        )
        _print_metrics(f"[{trial_num}] {family}{' QUALIFIZIERT' if meets_criterion else ''}", metrics)
        if meets_criterion:
            qualifying.append({"family": family, "params": trial_model.get_params(), "metrics": metrics})

    print("\nENDERGEBNIS (qualifizierende Konfigurationen, sortiert nach MAE, Trendwenden-Genauigkeit als Tiebreaker):")
    qualifying.sort(key=lambda e: (e["metrics"]["mae"], -(e["metrics"].get("reversal_sign_accuracy") or 0)))
    for entry in qualifying:
        print(
            f"{entry['family']}: mae={entry['metrics']['mae']} sign_accuracy={entry['metrics']['sign_accuracy']}% "
            f"reversal_sign_accuracy={entry['metrics'].get('reversal_sign_accuracy')} params={entry['params']}"
        )

    if not qualifying:
        print("\nKein Gewinner - Baseline bleibt bestehen.")
        return

    best_sklearn = next((e for e in qualifying if e["family"] in SKLEARN_FAMILIES), None)
    best_new_dep = next((e for e in qualifying if e["family"] not in SKLEARN_FAMILIES), None)
    if best_new_dep and best_sklearn:
        mae_improvement_pct = (
            (best_sklearn["metrics"]["mae"] - best_new_dep["metrics"]["mae"]) / best_sklearn["metrics"]["mae"] * 100
        )
        accuracy_improvement_pt = best_new_dep["metrics"]["sign_accuracy"] - best_sklearn["metrics"]["sign_accuracy"]
        print(
            f"\nLightGBM/XGBoost vs bester sklearn-Gewinner: "
            f"MAE {mae_improvement_pct:.1f}% besser, Accuracy {accuracy_improvement_pt:.1f}pt besser."
        )
        if mae_improvement_pct >= DEPENDENCY_MAE_THRESHOLD_PCT or accuracy_improvement_pt >= DEPENDENCY_ACCURACY_THRESHOLD_PT:
            print("=> Dependency-Schwelle erreicht, neue Familie empfohlen.")
        else:
            print("=> Dependency-Schwelle NICHT erreicht, sklearn-Gewinner empfohlen.")
    elif best_new_dep and not best_sklearn:
        print("\nNur eine neue-Dependency-Familie qualifiziert, kein sklearn-Vergleich moeglich - manuell pruefen.")
    else:
        print(f"\nEmpfehlung: {best_sklearn['family']} (bester qualifizierender sklearn-Kandidat).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Kurzer Smoke-Test (kein automatisierter Test - manuelle Verifikation, etabliertes Muster fuer
  Experiment-Skripte)**

```bash
FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/firebase-service-account.json" \
  TUNING_BUDGET_HOURS=0.03 .venv-tuning/bin/python -m src.experiment_target3d_tuning
```

Erwartet (dauert ca. 2 Minuten): `BASELINE RandomForest: ...` und `BASELINE HistGradientBoosting: ...` Zeilen,
danach mindestens 1-2 `[N] <Familie>: ...`-Zeilen, danach `Zeitbudget (0.03h) aufgebraucht` oder
`Sicherheitsmarge erreicht`, danach `ENDERGEBNIS (...)`. Kein Crash, kein Traceback. Falls ein Traceback auftritt:
Fehler beheben, bevor der lange Lauf gestartet wird (Kosten eines gescheiterten 11h-Laufs sind hoch).

- [ ] **Step 4: Commit**

```bash
git add src/experiment_target3d_tuning.py
git commit -m "ML: Experiment-Skript fuer embargo-korrekte 3T-Hyperparameter-Suche"
```

---

## Nach den Tasks (Haupt-Thread, kein Subagent)

1. Vollen 11h-Lauf starten (Hintergrundprozess in der Sandbox):
   ```bash
   FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/firebase-service-account.json" \
     TUNING_BUDGET_HOURS=11 .venv-tuning/bin/python -m src.experiment_target3d_tuning \
     > tuning-results/target3d.log 2>&1
   ```
2. Fortschritt in ~45-60min-Abstaenden pruefen (kein Dauer-Polling), bis der Lauf durch ist.
3. Ergebnis dokumentieren: `docs/superpowers/plans/2026-08-04-ml-3d-tuning-results.md` (Format analog zu
   `docs/superpowers/plans/2026-08-01-ml-3d-tuning-results.md`) - unabhaengig vom Ausgang (auch "kein Gewinner"
   ist ein valides Ergebnis).
4. **Nur falls ein Gewinner das Kriterium erfuellt:** kleiner Folge-Task (mit den jetzt bekannten echten Werten)
   - `_build_candidates()` parametrisieren (`horizon_days: int = 1`), 3T-Eintrag mit den gefundenen
   Hyperparametern, `BuildCandidatesTests` um den 3T-Fall erweitern, alle drei Call-Sites (`_train_and_evaluate`,
   `_walk_forward_backtest`, `backfill_prediction_log`) reichen ihr vorhandenes `horizon_days` durch. Falls
   LightGBM/XGBoost gewinnt: Dependency in `requirements.txt` pinnen, in `dashboard-marktwerte.yml` UND
   `dashboard.yml` verdrahten.
5. `src/experiment_target3d_tuning.py` per `git rm` entfernen (unabhaengig vom Ausgang, etabliertes Muster).
6. PR erstellen (`gh pr create` + `gh pr merge --auto --squash`), auf gruene Checks warten.
7. Nach Merge (nur falls ein Gewinner uebernommen wurde): Backfill (beide Horizonte, Skript-Datei) + erzwungener
   Heavy-Lauf, danach alte vs. neue 3T-MAE ehrlich vergleichen und dem User mitteilen.
