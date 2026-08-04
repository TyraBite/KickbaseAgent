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
        try:
            result = _walk_forward_backtest(
                history_df, target_col=TARGET_COL, horizon_days=HORIZON_DAYS,
                candidates={family: trial_model}, n_folds=N_FOLDS,
            )
        except ValueError as e:
            last_config_seconds = time.monotonic() - start
            if "DataFrame.dtypes for data must be int, float, bool or category" in str(e):
                print(f"[{trial_num}] {family}: XGBoost-Inkompatibilität (object-Spalten) - überspringen.")
                continue
            raise
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
