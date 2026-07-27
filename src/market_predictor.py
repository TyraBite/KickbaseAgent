"""ML-Marktwertprognose: taeglich neu trainiertes RandomForest-Modell auf
Basis von Kickbase's eigener 365-Tage-Marktwert- und Performance-Historie.

Kein eigenes Langzeit-Tracking noetig - Kickbase liefert die Historie selbst
(bestaetigt am 27.07.2026, auch fuer Spieler ausserhalb des eigenen Kaders/
Markts, siehe kickbase_client.get_team_players/get_player_performance).

Portiert die Grundidee aus github.com/LennardFe/Kickbase-Trading-Advisor,
aber bewusst abgewandelt:
- kein zweites SQLite-File als Cache (unnoetig, Kickbase liefert die
  Historie bei jedem Call frisch)
- kein Berlin-22:15-Cutoff (unser Cron laeuft 07:00 UTC, lange nach dem
  naechtlichen Marktwert-Update) - "heute" ist einfach die juengste Zeile
  pro Spieler mit bekanntem Marktwert
- eigener login()/get_me()/get_teams()-Call, unabhaengig von fetcher.py
  (bleibt dadurch unveraendert; dieses Modul ist eigenstaendig testbar:
  `python -m src.market_predictor`)
- echte RMSE statt der Referenz' mit "rmse" gelabelten MSE (fehlender
  sqrt())

Vollstaendig transient - kein DB-Schreiben, Modell wird jeden Lauf neu
trainiert (kein persistiertes Modell-File).
"""

from __future__ import annotations

import concurrent.futures
import datetime
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.kickbase_client import (
    KickbaseError,
    get_market_value_history,
    get_me,
    get_player_performance,
    get_team_players,
    get_teams,
    login,
)

FEATURES = [
    "p", "mv", "days_to_next",
    "mv_change_1d", "mv_trend_1d",
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence",
]
TARGET = "mv_target_clipped"

MARKET_VALUE_TIMEFRAME = 365
LAST_PERFORMANCE_VALUES = 50
MIN_TRAINING_ROWS = 200
RANDOM_STATE = 42
_EPOCH = datetime.date(1970, 1, 1)

# Aggregierter Sicherheits-Check: schlagen zu viele der ersten Abrufe fehl,
# lieber den ganzen Corpus-Aufbau abbrechen als auf degradierten Daten zu
# trainieren (Rate-Limit? API-Aenderung?).
_ABORT_FAILURE_SAMPLE = 50
_ABORT_FAILURE_RATE = 0.5


def _max_workers() -> int:
    return int(os.environ.get("MARKET_PREDICTOR_MAX_WORKERS", 8))


def _fetch_competition_player_ids(token: str, competition_id: str) -> dict[str, str]:
    """player_id -> team_id, ueber alle Vereine der Competition."""
    team_ids = get_teams(token, competition_id)
    player_to_team: dict[str, str] = {}
    for team_id in team_ids:
        try:
            player_ids = get_team_players(token, competition_id, team_id)
        except KickbaseError as exc:
            print(f"Warnung: Spieler von Team {team_id} nicht ladbar: {exc}", file=sys.stderr)
            continue
        for player_id in player_ids:
            player_to_team[player_id] = team_id
    return player_to_team


def _parse_minutes(raw) -> int:
    if not raw:
        return 0
    try:
        return int(str(raw).replace("'", ""))
    except ValueError:
        return 0


def _market_value_frame(token: str, league_id: str, player_id: str) -> pd.DataFrame:
    history = get_market_value_history(token, league_id, player_id, timeframe=MARKET_VALUE_TIMEFRAME)
    entries = history.get("it") or []
    if not entries:
        return pd.DataFrame(columns=["date", "mv"])
    df = pd.DataFrame(entries)
    df["date"] = pd.to_datetime([_EPOCH + datetime.timedelta(days=int(d)) for d in df["dt"]])
    return df[["date", "mv"]].sort_values("date").reset_index(drop=True)


def _performance_frame(token: str, competition_id: str, player_id: str) -> pd.DataFrame:
    data = get_player_performance(token, competition_id, player_id)
    all_ph = [m for season in data.get("it", []) for m in season.get("ph", [])]
    all_ph = all_ph[-LAST_PERFORMANCE_VALUES:]
    if not all_ph:
        return pd.DataFrame(columns=["date", "md", "p", "mp", "t1", "t2", "t1g", "t2g"])
    rows = [
        {
            "md": m.get("md"),
            "p": m.get("p"),
            "mp": _parse_minutes(m.get("mp")),
            "t1": m.get("t1"),
            "t2": m.get("t2"),
            "t1g": m.get("t1g"),
            "t2g": m.get("t2g"),
        }
        for m in all_ph
    ]
    df = pd.DataFrame(rows)
    df["md"] = pd.to_datetime(df["md"], utc=True).dt.tz_localize(None)
    df["date"] = df["md"]
    return df.sort_values("date").reset_index(drop=True)


def _fetch_player_training_frame(
    token: str, league_id: str, competition_id: str, player_id: str, team_id: str
) -> pd.DataFrame | None:
    """Holt Marktwert- und Performance-Historie eines Spielers und merged sie
    zu einer Zeitreihe. Faengt Fehler selbst ab (Resilienz-Pattern analog
    fetcher._apply_market_value_history) - ein einzelner fehlgeschlagener
    Spieler darf den Corpus-Aufbau nicht abbrechen."""
    try:
        mv_df = _market_value_frame(token, league_id, player_id)
        p_df = _performance_frame(token, competition_id, player_id)
    except KickbaseError as exc:
        print(f"Warnung: Spieler {player_id} nicht ladbar: {exc}", file=sys.stderr)
        return None

    if mv_df.empty:
        return None

    mv_df["date"] = mv_df["date"].astype("datetime64[us]")

    if p_df.empty:
        merged = mv_df.copy()
        for col in ("md", "p", "mp", "t1", "t2", "t1g", "t2g"):
            merged[col] = None
    else:
        p_df["date"] = p_df["date"].astype("datetime64[us]")
        merged = pd.merge_asof(mv_df, p_df, on="date", direction="backward")
        future_p = p_df[p_df["date"] > mv_df["date"].max()]
        if not future_p.empty:
            merged = pd.concat([merged, future_p], ignore_index=True)

    merged["player_id"] = player_id
    merged["team_id"] = team_id
    return merged


def _build_corpus(token: str, league_id: str, competition_id: str) -> pd.DataFrame:
    player_to_team = _fetch_competition_player_ids(token, competition_id)
    if not player_to_team:
        raise RuntimeError("Keine Spieler-Ids ueber get_team_players() gefunden")

    frames: list[pd.DataFrame] = []
    checked = 0
    failures = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers()) as executor:
        futures = {
            executor.submit(_fetch_player_training_frame, token, league_id, competition_id, pid, tid): pid
            for pid, tid in player_to_team.items()
        }
        for future in concurrent.futures.as_completed(futures):
            checked += 1
            result = future.result()
            if result is None or result.empty:
                failures += 1
            else:
                frames.append(result)

            if checked == _ABORT_FAILURE_SAMPLE and failures / checked > _ABORT_FAILURE_RATE:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(
                    f"Abbruch: {failures}/{checked} Spieler-Abrufe fehlgeschlagen - "
                    "Corpus-Aufbau wirkt degradiert (Rate-Limit? API-Aenderung?)"
                )

    if not frames:
        raise RuntimeError("Kein einziger Spieler-Datensatz erfolgreich geladen")
    return pd.concat(frames, ignore_index=True)


def _engineer_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Feature-Engineering fuer die Marktwertprognose, portiert aus der
    Referenz-Implementierung (siehe Modul-Docstring). Gibt (history_df,
    today_df) zurueck - history_df fuer Training/Test, today_df ist die
    juengste Zeile pro Spieler mit bekanntem Marktwert (das was prognostiziert
    werden soll)."""
    df = df.sort_values(["player_id", "date"]).reset_index(drop=True)

    df = df[
        (df["team_id"] == df["t1"])
        | (df["team_id"] == df["t2"])
        | (df["t1"].isna() & df["t2"].isna())
    ]

    df["date"] = pd.to_datetime(df["date"])
    df["md"] = pd.to_datetime(df["md"])

    df["next_md"] = df.groupby("player_id")["md"].transform(
        lambda x: x.shift(-1).where(x.shift(-1) != x).bfill()
    )
    df["days_to_next"] = (df["next_md"] - df["date"]).dt.days

    df["mv_next_day"] = df.groupby("player_id")["mv"].shift(-1)
    df["mv_target"] = df["mv_next_day"] - df["mv"]
    df = df[df["mv"] != 0.0]

    df["mv_change_1d"] = df["mv"] - df.groupby("player_id")["mv"].shift(1)
    df["mv_trend_1d"] = df.groupby("player_id")["mv"].pct_change(fill_method=None)
    df["mv_trend_1d"] = df["mv_trend_1d"].replace([np.inf, -np.inf], 0).fillna(0)

    df["mv_change_3d"] = df["mv"] - df.groupby("player_id")["mv"].shift(3)
    df["mv_vol_3d"] = df.groupby("player_id")["mv"].rolling(3).std().reset_index(0, drop=True)

    df["mv_trend_7d"] = df.groupby("player_id")["mv"].pct_change(periods=7, fill_method=None)
    df["mv_trend_7d"] = df["mv_trend_7d"].replace([np.inf, -np.inf], 0).fillna(0)

    df["market_divergence"] = (
        df["mv"] / df.groupby("md")["mv"].transform("mean")
    ).rolling(3).mean()

    q1 = df["mv_target"].quantile(0.25)
    q3 = df["mv_target"].quantile(0.75)
    iqr = q3 - q1
    df["mv_target_clipped"] = df["mv_target"].clip(q1 - 2.5 * iqr, q3 + 2.5 * iqr)

    df = df.fillna({"market_divergence": 1, "mv_change_3d": 0, "mv_vol_3d": 0, "p": 0})

    mv_known = df[df["mv"].notna()]
    today_df = mv_known.sort_values("date").groupby("player_id").tail(1)
    history_df = mv_known.drop(today_df.index)
    history_df = history_df.dropna(
        subset=["mv_change_1d", "next_md", "days_to_next", "mv_next_day", "mv_target", "mv_target_clipped"]
    )

    return history_df, today_df


def _train_and_evaluate(history_df: pd.DataFrame):
    """Trainiert RandomForestRegressor per Zeit-Split (75/25, kein Shuffle,
    verhindert Data Leakage). Gibt (model, metrics) oder None zurueck, wenn
    zu wenig Daten fuer einen sinnvollen Split/Training vorhanden sind."""
    if len(history_df) < MIN_TRAINING_ROWS:
        return None

    df = history_df.sort_values("date").reset_index(drop=True)
    split_idx = int(len(df) * 0.75)
    split_date = df["date"].iloc[split_idx]
    train = df[df["date"] < split_date]
    test = df[df["date"] >= split_date]

    if train.empty or test.empty:
        return None

    x_train, y_train = train[FEATURES], train[TARGET]
    x_test, y_test = test[FEATURES], test[TARGET]

    model = RandomForestRegressor(
        n_estimators=500,
        max_depth=20,
        min_samples_split=5,
        min_samples_leaf=2,
        max_features="sqrt",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    model.fit(x_train, y_train)

    y_pred = model.predict(x_test)
    rmse = mean_squared_error(y_test, y_pred) ** 0.5
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    sign_accuracy = float(np.mean(np.sign(y_test) == np.sign(y_pred)) * 100)

    metrics = {
        "rmse": round(rmse, 2),
        "mae": round(mae, 2),
        "r2": round(r2, 3),
        "sign_accuracy": round(sign_accuracy, 1),
        "train_rows": len(train),
        "test_rows": len(test),
    }
    return model, metrics


def predict_market_value_changes() -> dict | None:
    """Oeffentlicher Entry-Point: loggt sich unabhaengig von fetcher.py ein,
    baut den Corpus, trainiert und prognostiziert. Gibt bei Erfolg
    {"predictions": {player_id: predicted_delta}, "metrics": {...}} zurueck,
    sonst None (Warnung auf stderr) - main.py degradiert dann auf den
    Rest der Pipeline ohne ML-Sektion."""
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        print("Warnung: KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen, ML-Prognose uebersprungen.", file=sys.stderr)
        return None

    try:
        token, _user, leagues = login(email, password)
        if not leagues:
            print("Warnung: Account in keiner Liga, ML-Prognose uebersprungen.", file=sys.stderr)
            return None
        league_id = leagues[0]["id"]
        me = get_me(token, league_id)
        competition_id = me.get("cpi") or "1"

        corpus = _build_corpus(token, league_id, competition_id)
        history_df, today_df = _engineer_features(corpus)

        trained = _train_and_evaluate(history_df)
        if trained is None:
            print(
                f"Warnung: zu wenig Trainingsdaten ({len(history_df)} Zeilen, Minimum {MIN_TRAINING_ROWS}) - "
                "ML-Prognose uebersprungen.",
                file=sys.stderr,
            )
            return None
        model, metrics = trained

        today_df = today_df.dropna(subset=["mv"] + FEATURES)
        if today_df.empty:
            print("Warnung: keine heutigen Zeilen mit vollstaendigen Features - ML-Prognose uebersprungen.", file=sys.stderr)
            return None

        predicted = model.predict(today_df[FEATURES])
        predictions = {
            player_id: round(float(value))
            for player_id, value in zip(today_df["player_id"], predicted)
        }
        return {"predictions": predictions, "metrics": metrics}
    except (KickbaseError, RuntimeError) as exc:
        print(f"Warnung: ML-Marktwertprognose fehlgeschlagen, wird uebersprungen: {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    result = predict_market_value_changes()
    if result is None:
        print("Keine Prognose verfuegbar (siehe Warnungen oben).")
    else:
        print("Metriken:", result["metrics"])
        print(f"Anzahl Spieler mit Prognose: {len(result['predictions'])}")
        sample = list(result["predictions"].items())[:10]
        print("Beispiele:", sample)
