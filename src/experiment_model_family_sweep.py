"""Einmaliges Experiment-Skript (nach Lauf wieder loeschen, analog den
vorherigen experiment_*.py): Runde 1 einer zweistufigen Modell-Untersuchung.
Testet mehrere MODELLFAMILIEN (nicht nur RandomForest/HistGradientBoosting)
gegen 30 Zeit-Folds (statt der bisherigen 6) - deutlich robusterer Vergleich
als das erste Tuning-Experiment, das mit nur 6 Folds vermutlich eine
Zufalls-guenstige Stichprobe erwischt hat (Live-Kachel zeigt 82.8%/25931 bei
n=10659 echten Tagen, der 6-Fold-Backtest hatte 90.1%/22553 bei n=2244).

Zweck dieser Runde: Modellfamilie(n) UND groben Parameterbereich fuer eine
spaetere, tiefere Nacht-Runde (viele Stunden, echtes Hyperparameter-Tuning
nur innerhalb der hier vielversprechendsten Familie(n)) eingrenzen - deshalb
hier bewusst nur je EIN vernuenftig konfigurierter Kandidat pro Familie,
kein Grid je Familie.

Feature-Set/Zielwert unveraendert (aktuelle 9 Live-Features, absoluter
Zielwert) - isoliert die Modellfamilie als einzige Variable, analog dem
Vorgehen bei den drei vorherigen Experimenten.

xgboost/lightgbm sind NEUE, NUR fuer dieses Skript installierte
Abhaengigkeiten (siehe Workflow-Datei) - kein Eintrag in requirements.txt,
bis eine der beiden tatsaechlich live gewinnt."""

import os
import sys

import numpy as np
from dotenv import load_dotenv
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge

from src.kickbase_client import get_me, login
from src.market_predictor import (
    BACKTEST_MIN_TRAIN_ROWS,
    FEATURES,
    RANDOM_STATE,
    TARGET,
    _build_corpus,
    _engineer_features,
)

FOLDS = 30

MODEL_FACTORIES = {
    "RandomForest (Live-Config)": lambda: RandomForestRegressor(
        n_estimators=500, max_depth=20, min_samples_split=5, min_samples_leaf=2,
        max_features="sqrt", n_jobs=-1, random_state=RANDOM_STATE,
    ),
    "HistGradientBoosting (Live-Config)": lambda: HistGradientBoostingRegressor(random_state=RANDOM_STATE),
    "ExtraTrees": lambda: ExtraTreesRegressor(
        n_estimators=500, max_depth=20, min_samples_split=5, min_samples_leaf=2,
        max_features="sqrt", n_jobs=-1, random_state=RANDOM_STATE,
    ),
    "XGBoost": lambda: _xgboost_regressor(),
    "LightGBM": lambda: _lightgbm_regressor(),
    "Ridge (linear, Referenz)": lambda: Ridge(alpha=1.0),
}


def _xgboost_regressor():
    from xgboost import XGBRegressor

    return XGBRegressor(
        n_estimators=300, learning_rate=0.1, max_depth=6, n_jobs=-1,
        random_state=RANDOM_STATE, objective="reg:squarederror",
    )


def _lightgbm_regressor():
    from lightgbm import LGBMRegressor

    return LGBMRegressor(n_estimators=300, learning_rate=0.1, n_jobs=-1, random_state=RANDOM_STATE, verbosity=-1)


def run_backtest(history_df) -> None:
    dates = sorted(history_df["date"].unique())
    if len(dates) <= FOLDS:
        raise RuntimeError(f"Zu wenig Tage fuer {FOLDS} Folds: {len(dates)}")
    cutoffs = dates[-FOLDS:]

    sign_hits: dict[str, list[bool]] = {name: [] for name in MODEL_FACTORIES}
    abs_errors: dict[str, list[float]] = {name: [] for name in MODEL_FACTORIES}
    per_fold_accuracy: dict[str, list[float]] = {name: [] for name in MODEL_FACTORIES}
    folds_run = 0

    for i, cutoff in enumerate(cutoffs):
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1
        print(f"Fold {i + 1}/{FOLDS} ({cutoff}, {len(train)} Trainings-, {len(test)} Test-Zeilen)...", file=sys.stderr)

        # .astype(float) explizit: die "p"-Spalte kommt als object-Dtype aus
        # dem Corpus, sklearn-Modelle tolerieren das stillschweigend, XGBoost
        # nicht (ValueError: DataFrame.dtypes for data must be int, float,
        # bool or category) - live gefunden im ersten Lauf dieses Skripts.
        x_train, y_train = train[FEATURES].astype(float), train[TARGET]
        x_test = test[FEATURES].astype(float)
        y_test_actual = test["mv_target"]

        for name, factory in MODEL_FACTORIES.items():
            model = factory()
            model.fit(x_train, y_train)
            y_pred = model.predict(x_test)
            hits = (np.sign(y_test_actual) == np.sign(y_pred)).tolist()
            errors = np.abs(y_test_actual - y_pred).tolist()
            sign_hits[name].extend(hits)
            abs_errors[name].extend(errors)
            per_fold_accuracy[name].append(float(np.mean(hits)) * 100 if hits else None)

    if not folds_run:
        raise RuntimeError("Kein Fold hatte genug Trainingsdaten")

    print(f"\n{folds_run} von {FOLDS} Folds ausgewertet\n")
    results = []
    for name in MODEL_FACTORIES:
        hits = sign_hits[name]
        if not hits:
            continue
        fold_accs = [a for a in per_fold_accuracy[name] if a is not None]
        results.append({
            "name": name,
            "sign_accuracy": round(float(np.mean(hits)) * 100, 1),
            "mae": round(float(np.mean(abs_errors[name])), 0),
            "fold_std": round(float(np.std(fold_accs)), 1) if len(fold_accs) > 1 else 0.0,
            "n": len(hits),
        })

    results.sort(key=lambda r: r["sign_accuracy"], reverse=True)
    print(f"{'Modell':<35} {'Accuracy':>10} {'MAE':>10} {'Fold-Std':>10} {'n':>7}")
    for r in results:
        print(f"{r['name']:<35} {r['sign_accuracy']:>9.1f}% {r['mae']:>10.0f} {r['fold_std']:>9.1f}p {r['n']:>7}")

    print("\nZur Einordnung: Live-Kachel (echte 30 Tage) zeigt aktuell RandomForest 82.6%/25413, HistGradientBoosting 82.8%/25931, n=10659.")
    print("Ranking oben zeigt die RELATIVE Reihenfolge unter GLEICHER (Backtest-)Methodik - Grundlage fuer die Wahl der Nacht-Runde-Kandidaten.")


if __name__ == "__main__":
    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)")

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    competition_id = get_me(token, league_id).get("cpi") or "1"

    print("Baue Corpus (einmalig)...", file=sys.stderr)
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)
    print(f"{len(history_df)} Trainings-Zeilen im Corpus", file=sys.stderr)

    run_backtest(history_df)
