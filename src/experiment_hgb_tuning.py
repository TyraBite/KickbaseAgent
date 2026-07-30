"""Einmaliges Experiment-Skript (nach Lauf wieder loeschen, analog
backfill_bought_by_self.py): vergleicht eine kleine, handverlesene Auswahl
HistGradientBoosting-Hyperparameter-Konfigurationen gegen die aktuelle
Baseline (RF + HGB mit sklearn-Standardwerten) - ueber denselben
Walk-Forward-Aufbau wie market_predictor._walk_forward_backtest() (zeit-
geordnete Folds, kein Data Leakage), aber mit konfigurierbaren Kandidaten
statt der dort hart codierten zwei.

Bewusst KEIN vollstaendiges Grid/keine sklearn-GridSearchCV/RandomizedSearchCV:
nur 6 Zeit-Folds, eine Liga - je mehr Konfigs gegen genau diese Folds
getestet werden, desto groesser das Risiko, dass eine rein durch Zufall auf
dieser Fold-Aufteilung gewinnt (Multiple-Comparisons). sklearns
automatische Suche setzt zudem zufaelliges Mischen voraus, was dem
zeit-geordneten Walk-Forward-Aufbau widerspraeche (siehe Docstring dort).

Corpus wird EINMAL gebaut, alle Konfigs laufen gegen denselben In-Memory-
DataFrame - keine wiederholten Kickbase-API-Calls pro Konfig. Reines
Lese-Experiment, kein Firestore-Zugriff, keine Seiteneffekte."""

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

CANDIDATE_CONFIGS = {
    "baseline_hgb (sklearn-Standard, aktuell live)": HistGradientBoostingRegressor(
        random_state=RANDOM_STATE
    ),
    "baseline_rf (aktuelle Live-Config)": RandomForestRegressor(
        n_estimators=500,
        max_depth=20,
        min_samples_split=5,
        min_samples_leaf=2,
        max_features="sqrt",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    ),
    "hgb_lr05_iter300": HistGradientBoostingRegressor(
        learning_rate=0.05, max_iter=300, random_state=RANDOM_STATE
    ),
    "hgb_lr05_iter300_leaves15": HistGradientBoostingRegressor(
        learning_rate=0.05, max_iter=300, max_leaf_nodes=15, random_state=RANDOM_STATE
    ),
    "hgb_lr05_iter300_leaves63": HistGradientBoostingRegressor(
        learning_rate=0.05, max_iter=300, max_leaf_nodes=63, random_state=RANDOM_STATE
    ),
    "hgb_lr02_iter100": HistGradientBoostingRegressor(
        learning_rate=0.2, max_iter=100, random_state=RANDOM_STATE
    ),
    "hgb_lr02_iter100_leaves63": HistGradientBoostingRegressor(
        learning_rate=0.2, max_iter=100, max_leaf_nodes=63, random_state=RANDOM_STATE
    ),
    "hgb_lr01_iter200_leaves15": HistGradientBoostingRegressor(
        learning_rate=0.1, max_iter=200, max_leaf_nodes=15, random_state=RANDOM_STATE
    ),
}


def run_backtest(history_df, configs: dict[str, object]) -> dict[str, dict]:
    dates = sorted(history_df["date"].unique())
    if len(dates) <= BACKTEST_FOLDS:
        raise RuntimeError(f"Zu wenig Tage fuer {BACKTEST_FOLDS} Folds: {len(dates)}")
    cutoffs = dates[-BACKTEST_FOLDS:]

    sign_hits: dict[str, list[bool]] = {name: [] for name in configs}
    abs_errors: dict[str, list[float]] = {name: [] for name in configs}
    per_fold_accuracy: dict[str, list[float]] = {name: [] for name in configs}
    folds_run = 0

    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[TARGET]
        x_test = test[FEATURES]
        y_test_actual = test["mv_target"]

        for name, model in configs.items():
            model.fit(x_train, y_train)
            y_pred = model.predict(x_test)
            hits = (np.sign(y_test_actual) == np.sign(y_pred)).tolist()
            errors = np.abs(y_test_actual - y_pred).tolist()
            sign_hits[name].extend(hits)
            abs_errors[name].extend(errors)
            per_fold_accuracy[name].append(float(np.mean(hits)) * 100 if hits else None)

    if not folds_run:
        raise RuntimeError("Kein Fold hatte genug Trainingsdaten")

    print(f"\n{folds_run} von {BACKTEST_FOLDS} Folds ausgewertet\n")
    results = {}
    for name in configs:
        hits = sign_hits[name]
        if not hits:
            continue
        fold_accs = [a for a in per_fold_accuracy[name] if a is not None]
        results[name] = {
            "sign_accuracy": round(float(np.mean(hits)) * 100, 1),
            "mae": round(float(np.mean(abs_errors[name])), 0),
            "fold_std": round(float(np.std(fold_accs)), 1) if len(fold_accs) > 1 else 0.0,
            "n": len(hits),
        }

    print(f"{'Config':<45} {'Accuracy':>10} {'MAE':>10} {'Fold-Std':>10} {'n':>6}")
    for name, r in results.items():
        print(f"{name:<45} {r['sign_accuracy']:>9.1f}% {r['mae']:>10.0f} {r['fold_std']:>9.1f}p {r['n']:>6}")

    baseline = results.get("baseline_hgb (sklearn-Standard, aktuell live)")
    if baseline:
        print(f"\nErfolgs-Kriterium: Accuracy >= Baseline+1pt UND MAE <= Baseline, Baseline = {baseline['sign_accuracy']}% / {baseline['mae']}")
        winners = [
            name
            for name, r in results.items()
            if name != "baseline_hgb (sklearn-Standard, aktuell live)"
            and r["sign_accuracy"] >= baseline["sign_accuracy"] + 1.0
            and r["mae"] <= baseline["mae"]
        ]
        if winners:
            print(f"Erfuellt das Kriterium: {', '.join(winners)}")
        else:
            print("Keine Konfig erfuellt das Kriterium - keine Verbesserung gefunden.")

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

    print("Baue Corpus (einmalig, alle Konfigs teilen sich dieselben Daten)...", file=sys.stderr)
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)
    print(f"{len(history_df)} Trainings-Zeilen im Corpus", file=sys.stderr)

    run_backtest(history_df, CANDIDATE_CONFIGS)
