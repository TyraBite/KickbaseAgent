"""Einmaliges Experiment-Skript (nach Lauf wieder loeschen, analog
experiment_hgb_tuning.py/experiment_injury_proxy.py): testet ob ein
relativer statt absoluter Zielwert (prozentuale statt Euro-Marktwert-
Aenderung) die Prognose verbessert - Motivation: ein fixer Euro-Fehler
(aktuell MAE ~22.5k) wiegt bei einem 1-Mio.-Spieler relativ viel schwerer
als bei einem 15-Mio.-Spieler. EINE Variable geaendert (Ziel-Repraesentation),
Modell/Features/Hyperparameter unveraendert (HistGradientBoosting,
sklearn-Standardwerte - Tuning-Experiment fand keine bessere Konfiguration).

Modell B (relativ) wird auf mv_target_pct_clipped ((mv_next_day - mv) / mv,
IQR-geclippt) trainiert, seine Vorhersage fuer den fairen Vergleich zurueck
auf Euro-Einheiten multipliziert (pred_pct * mv) - beide Modelle landen so
in derselben MAE-Einheit.

Zusaetzlich: Aufschluesselung nach Marktwert-Terzil (guenstig/mittel/teuer),
um zu pruefen, ob der relative Zielwert tatsaechlich gezielt guenstigen
Spielern hilft, ohne teure zu verschlechtern - genau die Hypothese hinter
diesem Experiment."""

import os
import sys

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import HistGradientBoostingRegressor

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


def _add_relative_target(history_df: pd.DataFrame) -> pd.DataFrame:
    df = history_df.copy()
    pct = df["mv_target"] / df["mv"]
    q1, q3 = pct.quantile(0.25), pct.quantile(0.75)
    iqr = q3 - q1
    df["mv_target_pct_clipped"] = pct.clip(q1 - 2.5 * iqr, q3 + 2.5 * iqr)
    return df


def run_backtest(history_df: pd.DataFrame) -> None:
    history_df = _add_relative_target(history_df)
    dates = sorted(history_df["date"].unique())
    if len(dates) <= BACKTEST_FOLDS:
        raise RuntimeError(f"Zu wenig Tage fuer {BACKTEST_FOLDS} Folds: {len(dates)}")
    cutoffs = dates[-BACKTEST_FOLDS:]

    rows = []  # {mv, actual, pred_abs, pred_rel}
    folds_run = 0

    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        model_abs = HistGradientBoostingRegressor(random_state=RANDOM_STATE)
        model_abs.fit(train[FEATURES], train[TARGET])
        pred_abs = model_abs.predict(test[FEATURES])

        model_rel = HistGradientBoostingRegressor(random_state=RANDOM_STATE)
        model_rel.fit(train[FEATURES], train["mv_target_pct_clipped"])
        pred_rel_pct = model_rel.predict(test[FEATURES])
        pred_rel_abs = pred_rel_pct * test["mv"].to_numpy()

        for mv, actual, pa, pr in zip(test["mv"], test["mv_target"], pred_abs, pred_rel_abs):
            rows.append({"mv": mv, "actual": actual, "pred_abs": pa, "pred_rel": pr})

    if not folds_run:
        raise RuntimeError("Kein Fold hatte genug Trainingsdaten")

    print(f"\n{folds_run} von {BACKTEST_FOLDS} Folds ausgewertet, {len(rows)} Test-Zeilen gesamt\n")
    df = pd.DataFrame(rows)
    df["bucket"] = pd.qcut(df["mv"], 3, labels=["guenstig", "mittel", "teuer"])

    def _metrics(sub: pd.DataFrame, pred_col: str) -> dict:
        hits = np.sign(sub["actual"]) == np.sign(sub[pred_col])
        return {
            "sign_accuracy": round(float(hits.mean()) * 100, 1),
            "mae": round(float(np.abs(sub["actual"] - sub[pred_col]).mean()), 0),
            "n": len(sub),
        }

    print(f"{'Bucket':<12} {'Modell':<10} {'Accuracy':>10} {'MAE':>10} {'n':>6}")
    for bucket in ["guenstig", "mittel", "teuer", None]:
        sub = df if bucket is None else df[df["bucket"] == bucket]
        label = bucket or "GESAMT"
        for pred_col, name in [("pred_abs", "absolut"), ("pred_rel", "relativ")]:
            m = _metrics(sub, pred_col)
            print(f"{label:<12} {name:<10} {m['sign_accuracy']:>9.1f}% {m['mae']:>10.0f} {m['n']:>6}")

    overall_abs = _metrics(df, "pred_abs")
    overall_rel = _metrics(df, "pred_rel")
    print(f"\nErfolgs-Kriterium: Accuracy >= Baseline+1pt UND MAE <= Baseline (Baseline = absolut)")
    print(f"Absolut (Baseline): {overall_abs['sign_accuracy']}% / {overall_abs['mae']}")
    print(f"Relativ: {overall_rel['sign_accuracy']}% / {overall_rel['mae']}")
    if overall_rel["sign_accuracy"] >= overall_abs["sign_accuracy"] + 1.0 and overall_rel["mae"] <= overall_abs["mae"]:
        print("Kriterium erfuellt - relativer Zielwert verbessert die Prognose.")
    else:
        print("Kriterium NICHT erfuellt - keine Gesamt-Verbesserung durch relativen Zielwert gefunden.")


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
