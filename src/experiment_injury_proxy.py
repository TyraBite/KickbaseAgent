"""Einmaliges Experiment-Skript (nach Lauf wieder loeschen, analog
experiment_hgb_tuning.py): testet ob mp_avg_3 (rollierender 3-Spiele-
Minutenschnitt, siehe market_predictor.py::_performance_frame) als
zusaetzliches Feature die Prognose verbessert - EINE Variable geaendert
(Feature-Set), Modell-Hyperparameter unveraendert, damit der Effekt isoliert
messbar ist (kein Vermischen mit dem bereits abgeschlossenen HGB-Tuning-
Experiment).

Gleiche Methodik wie experiment_hgb_tuning.py: Walk-Forward ueber dieselben
6 Zeit-Folds, ein Corpus-Build, kein Firestore-Zugriff.

Erfolgs-Kriterium (identisch zum Tuning-Experiment): Accuracy >=
Baseline+1pt UND MAE <= Baseline, gemessen am aktuellen Live-Modell
(HistGradientBoosting, sklearn-Standardwerte - das Tuning-Experiment fand
keine bessere Konfiguration)."""

import os
import sys

import numpy as np
from dotenv import load_dotenv
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

from src.kickbase_client import get_me, login
from src.market_predictor import (
    BACKTEST_FOLDS,
    BACKTEST_MIN_TRAIN_ROWS,
    FEATURES,
    RANDOM_STATE,
    TARGET,
    _build_corpus,
    _engineer_features,
)

FEATURES_WITH_INJURY_PROXY = FEATURES + ["mp_avg_3"]

MODEL_FACTORIES = {
    "HistGradientBoosting": lambda: HistGradientBoostingRegressor(random_state=RANDOM_STATE),
    "RandomForest": lambda: RandomForestRegressor(
        n_estimators=500,
        max_depth=20,
        min_samples_split=5,
        min_samples_leaf=2,
        max_features="sqrt",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    ),
}

FEATURE_SETS = {
    "baseline (ohne mp_avg_3)": FEATURES,
    "mit mp_avg_3": FEATURES_WITH_INJURY_PROXY,
}


def run_backtest(history_df) -> dict[str, dict]:
    dates = sorted(history_df["date"].unique())
    if len(dates) <= BACKTEST_FOLDS:
        raise RuntimeError(f"Zu wenig Tage fuer {BACKTEST_FOLDS} Folds: {len(dates)}")
    cutoffs = dates[-BACKTEST_FOLDS:]

    combos = [
        (model_name, feature_set_name)
        for model_name in MODEL_FACTORIES
        for feature_set_name in FEATURE_SETS
    ]
    sign_hits: dict[tuple, list[bool]] = {c: [] for c in combos}
    abs_errors: dict[tuple, list[float]] = {c: [] for c in combos}
    per_fold_accuracy: dict[tuple, list[float]] = {c: [] for c in combos}
    folds_run = 0

    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        y_test_actual = test["mv_target"]

        for model_name, feature_set_name in combos:
            features = FEATURE_SETS[feature_set_name]
            model = MODEL_FACTORIES[model_name]()
            model.fit(train[features], train[TARGET])
            y_pred = model.predict(test[features])
            hits = (np.sign(y_test_actual) == np.sign(y_pred)).tolist()
            errors = np.abs(y_test_actual - y_pred).tolist()
            combo = (model_name, feature_set_name)
            sign_hits[combo].extend(hits)
            abs_errors[combo].extend(errors)
            per_fold_accuracy[combo].append(float(np.mean(hits)) * 100 if hits else None)

    if not folds_run:
        raise RuntimeError("Kein Fold hatte genug Trainingsdaten")

    print(f"\n{folds_run} von {BACKTEST_FOLDS} Folds ausgewertet\n")
    results = {}
    for combo in combos:
        hits = sign_hits[combo]
        if not hits:
            continue
        fold_accs = [a for a in per_fold_accuracy[combo] if a is not None]
        results[combo] = {
            "sign_accuracy": round(float(np.mean(hits)) * 100, 1),
            "mae": round(float(np.mean(abs_errors[combo])), 0),
            "fold_std": round(float(np.std(fold_accs)), 1) if len(fold_accs) > 1 else 0.0,
            "n": len(hits),
        }

    print(f"{'Modell':<20} {'Feature-Set':<25} {'Accuracy':>10} {'MAE':>10} {'Fold-Std':>10} {'n':>6}")
    for (model_name, feature_set_name), r in results.items():
        print(
            f"{model_name:<20} {feature_set_name:<25} {r['sign_accuracy']:>9.1f}% "
            f"{r['mae']:>10.0f} {r['fold_std']:>9.1f}p {r['n']:>6}"
        )

    print(f"\nErfolgs-Kriterium (fuer HistGradientBoosting): Accuracy >= Baseline+1pt UND MAE <= Baseline")
    baseline = results.get(("HistGradientBoosting", "baseline (ohne mp_avg_3)"))
    with_proxy = results.get(("HistGradientBoosting", "mit mp_avg_3"))
    if baseline and with_proxy:
        print(f"Baseline: {baseline['sign_accuracy']}% / {baseline['mae']}")
        print(f"Mit Proxy: {with_proxy['sign_accuracy']}% / {with_proxy['mae']}")
        if with_proxy["sign_accuracy"] >= baseline["sign_accuracy"] + 1.0 and with_proxy["mae"] <= baseline["mae"]:
            print("Kriterium erfuellt - mp_avg_3 verbessert die Prognose.")
        else:
            print("Kriterium NICHT erfuellt - keine Verbesserung durch mp_avg_3 gefunden.")

    return results


if __name__ == "__main__":
    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)")

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    competition_id = get_me(token, league_id).get("cpi") or "1"

    print("Baue Corpus (einmalig, alle Kombinationen teilen sich dieselben Daten)...", file=sys.stderr)
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)
    print(f"{len(history_df)} Trainings-Zeilen im Corpus", file=sys.stderr)

    run_backtest(history_df)
