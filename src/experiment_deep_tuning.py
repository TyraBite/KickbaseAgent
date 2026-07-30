"""Einmaliges Experiment-Skript (nach Lauf wieder loeschen, analog den
vorherigen experiment_*.py): Runde 2 der Modell-Untersuchung - echte
randomisierte Hyperparameter-Suche innerhalb der 4 in Runde 1
gleichwertigen Familien (RandomForest, HistGradientBoosting, LightGBM,
XGBoost - ExtraTrees/Ridge waren dort klar schlechter, hier nicht mehr
dabei). 30 Folds (wie Runde 1, robust bestaetigt gegen die echte
Live-Kachel).

Zeitbudget-gesteuert statt Konfigurations-Anzahl-gesteuert (TUNING_BUDGET_
SECONDS-Env-Var) - GitHub Actions hat ein hartes 6h-Job-Limit auf gehosteten
Runnern, das Skript hoert deshalb rechtzeitig VOR dem Budget auf (Sicherheits-
marge = letzte Konfigurationsdauer * 1.3), damit ein Lauf nie zwangsabgebrochen
wird, ohne dass die bis dahin gefundenen Ergebnisse ausgegeben wurden.

Konfigurationen werden per sklearn ParameterSampler zufaellig aus einem
Bereich pro Familie gezogen, RUNDE-ROBIN ueber die 4 Familien verteilt
(damit bei vorzeitigem Zeit-Ende keine Familie systematisch benachteiligt
wird). Nach JEDER fertigen Konfiguration wird die aktuelle Bestenliste
neu ausgegeben - bei einem Absturz/Abbruch bleibt trotzdem ein
verwertbares Zwischenergebnis im Log."""

import os
import sys
import time

import numpy as np
from dotenv import load_dotenv
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import ParameterSampler

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
N_SAMPLES_PER_FAMILY = 100  # obere Schranke, Zeitbudget bricht i.d.R. frueher ab

PARAM_SPACES = {
    "RandomForest": {
        "n_estimators": [200, 500, 800],
        "max_depth": [10, 20, 30, None],
        "min_samples_split": [2, 5, 10],
        "min_samples_leaf": [1, 2, 4],
        "max_features": ["sqrt", "log2", 0.5],
    },
    "HistGradientBoosting": {
        "learning_rate": [0.02, 0.05, 0.1, 0.2],
        "max_iter": [100, 200, 300, 500],
        "max_leaf_nodes": [15, 31, 63, 127],
        "l2_regularization": [0.0, 0.1, 1.0],
        "min_samples_leaf": [10, 20, 50],
    },
    "LightGBM": {
        "n_estimators": [100, 300, 500],
        "learning_rate": [0.02, 0.05, 0.1, 0.2],
        "num_leaves": [15, 31, 63, 127],
        "min_child_samples": [10, 20, 50],
        "subsample": [0.7, 0.85, 1.0],
    },
    "XGBoost": {
        "n_estimators": [100, 300, 500],
        "learning_rate": [0.02, 0.05, 0.1, 0.2],
        "max_depth": [3, 6, 9],
        "subsample": [0.7, 0.85, 1.0],
        "colsample_bytree": [0.7, 0.85, 1.0],
    },
}


def _build_model(family: str, params: dict):
    if family == "RandomForest":
        return RandomForestRegressor(n_jobs=-1, random_state=RANDOM_STATE, **params)
    if family == "HistGradientBoosting":
        return HistGradientBoostingRegressor(random_state=RANDOM_STATE, **params)
    if family == "LightGBM":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(n_jobs=-1, random_state=RANDOM_STATE, verbosity=-1, **params)
    if family == "XGBoost":
        from xgboost import XGBRegressor

        return XGBRegressor(n_jobs=-1, random_state=RANDOM_STATE, objective="reg:squarederror", **params)
    raise ValueError(family)


def _build_candidate_queue():
    """Round-Robin ueber die 4 Familien, damit bei vorzeitigem Zeit-Ende
    keine Familie systematisch benachteiligt wird."""
    samplers = {
        family: iter(ParameterSampler(space, n_iter=N_SAMPLES_PER_FAMILY, random_state=RANDOM_STATE))
        for family, space in PARAM_SPACES.items()
    }
    queue = []
    families = list(PARAM_SPACES)
    exhausted = set()
    while len(exhausted) < len(families):
        for family in families:
            if family in exhausted:
                continue
            try:
                queue.append((family, next(samplers[family])))
            except StopIteration:
                exhausted.add(family)
    return queue


def _evaluate_config(history_df, cutoffs, family: str, params: dict) -> dict:
    sign_hits: list[bool] = []
    abs_errors: list[float] = []
    per_fold_accuracy: list[float] = []
    folds_run = 0

    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES].astype(float), train[TARGET]
        x_test = test[FEATURES].astype(float)
        y_test_actual = test["mv_target"]

        model = _build_model(family, params)
        model.fit(x_train, y_train)
        y_pred = model.predict(x_test)
        hits = (np.sign(y_test_actual) == np.sign(y_pred)).tolist()
        errors = np.abs(y_test_actual - y_pred).tolist()
        sign_hits.extend(hits)
        abs_errors.extend(errors)
        per_fold_accuracy.append(float(np.mean(hits)) * 100 if hits else None)

    if not sign_hits:
        raise RuntimeError("Kein Fold hatte genug Trainingsdaten")

    fold_accs = [a for a in per_fold_accuracy if a is not None]
    return {
        "family": family,
        "params": params,
        "sign_accuracy": round(float(np.mean(sign_hits)) * 100, 1),
        "mae": round(float(np.mean(abs_errors)), 0),
        "fold_std": round(float(np.std(fold_accs)), 1) if len(fold_accs) > 1 else 0.0,
        "n": len(sign_hits),
        "folds_run": folds_run,
    }


def _print_leaderboard(results: list[dict]) -> None:
    # Nach MAE sortiert, NICHT nach Accuracy - ein Fund im 2h-Testlauf:
    # Configs mit sehr niedriger learning_rate + wenig Estimators (=
    # Unterfitting) trafen oefter zufaellig die Richtung (hohe Accuracy),
    # lagen dabei aber im Betrag katastrophal daneben (MAE 30k+ statt ~25k).
    # Reine Accuracy-Sortierung haette solche Configs faelschlich nach oben
    # gespuelt.
    ranked = sorted(results, key=lambda r: r["mae"])
    print(f"\n--- Zwischenstand ({len(results)} Konfigurationen fertig, nach MAE sortiert) ---")
    print(f"{'Familie':<20} {'Accuracy':>10} {'MAE':>10} {'Fold-Std':>10} {'Params'}")
    for r in ranked[:10]:
        print(f"{r['family']:<20} {r['sign_accuracy']:>9.1f}% {r['mae']:>10.0f} {r['fold_std']:>9.1f}p {r['params']}")
    print("---\n", file=sys.stderr)


def run(history_df, budget_seconds: float) -> None:
    dates = sorted(history_df["date"].unique())
    if len(dates) <= FOLDS:
        raise RuntimeError(f"Zu wenig Tage fuer {FOLDS} Folds: {len(dates)}")
    cutoffs = dates[-FOLDS:]

    queue = _build_candidate_queue()
    print(f"{len(queue)} Konfigurationen in der Warteschlange, Zeitbudget {budget_seconds/3600:.1f}h", file=sys.stderr)

    results = []
    start = time.monotonic()
    last_config_duration = 0.0

    for i, (family, params) in enumerate(queue):
        elapsed = time.monotonic() - start
        remaining = budget_seconds - elapsed
        if last_config_duration and remaining < last_config_duration * 1.3:
            print(
                f"Zeitbudget bald erreicht ({elapsed/60:.1f}min verstrichen, {remaining/60:.1f}min uebrig, "
                f"letzte Konfig brauchte {last_config_duration/60:.1f}min) - Suche wird jetzt beendet.",
                file=sys.stderr,
            )
            break

        config_start = time.monotonic()
        print(f"[{i + 1}/{len(queue)}] {family} {params} ...", file=sys.stderr)
        try:
            result = _evaluate_config(history_df, cutoffs, family, params)
            results.append(result)
        except Exception as exc:
            print(f"Warnung: Konfiguration fehlgeschlagen, uebersprungen: {exc}", file=sys.stderr)
            continue
        last_config_duration = time.monotonic() - config_start

        # JEDES Ergebnis einzeln loggen, nicht nur alle 3 in der
        # Top-10-Bestenliste - sonst verschwinden schwaechere Configs
        # spurlos aus dem Log, sobald sie aus der Top 10 rutschen (im
        # 2h-Testlauf gefunden: von 29 Configs waren nur 19 ueberhaupt
        # rekonstruierbar).
        print(
            f"ERGEBNIS {result['family']:<20} {result['sign_accuracy']:>5.1f}% "
            f"MAE={result['mae']:.0f} std={result['fold_std']:.1f}p {result['params']}"
        )

        if len(results) % 3 == 0 or i == len(queue) - 1:
            _print_leaderboard(results)

    print(f"\n=== ENDERGEBNIS: {len(results)} Konfigurationen getestet in {(time.monotonic() - start)/3600:.2f}h ===\n")
    _print_leaderboard(results)


if __name__ == "__main__":
    load_dotenv()
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError("KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)")
    budget_hours = float(os.environ.get("TUNING_BUDGET_HOURS", "2"))

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    competition_id = get_me(token, league_id).get("cpi") or "1"

    print("Baue Corpus (einmalig)...", file=sys.stderr)
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)
    print(f"{len(history_df)} Trainings-Zeilen im Corpus", file=sys.stderr)

    run(history_df, budget_seconds=budget_hours * 3600)
