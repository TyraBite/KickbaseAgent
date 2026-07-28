"""ML-Marktwertprognose: taeglich neu trainiertes Modell (RandomForest oder
HistGradientBoosting, siehe _train_and_evaluate) auf Basis von Kickbase's
eigener 365-Tage-Marktwert- und Performance-Historie.

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
trainiert (kein persistiertes Modell-File). Einzige Ausnahme:
data/ml_prediction_log.jsonl protokolliert taegliche Prognosen (Datum,
Spieler, prognostizierte Aenderung), damit die tatsaechliche Tag-fuer-Tag-
Genauigkeit rueckwirkend berechnet werden kann - der Corpus liefert die
echte Wertaenderung dafuer bereits mit, kein zweiter Log fuer "was
tatsaechlich passiert ist" noetig.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src import firestore_db
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

PREDICTION_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "ml_prediction_log.jsonl"
LOG_RETENTION_DAYS = 90
ACCURACY_WINDOWS_DAYS = (7, 30)
MIN_REALIZED_SAMPLES_FOR_SELECTION = 14

# Anzahl rollierender Trainingsschnitte fuer den Walk-Forward-Backtest (siehe
# _walk_forward_backtest) - bewusst klein gehalten, jeder Fold trainiert beide
# Modell-Kandidaten neu, kostet also spuerbar Laufzeit.
BACKTEST_FOLDS = 6
BACKTEST_MIN_TRAIN_ROWS = MIN_TRAINING_ROWS

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

    team_match = (
        (df["team_id"] == df["t1"]) | (df["team_id"] == df["t2"]) | (df["t1"].isna() & df["t2"].isna())
    )
    # merge_asof(direction="backward") in _fetch_player_training_frame haengt
    # jedem Marktwert-Tag die letzte bekannte Performance-Zeile an - bei
    # Spielern, die seit Jahren nicht mehr gespielt haben (z.B. Funk, letzter
    # Einsatz 2021), gehoert diese letzte Zeile zu einem laengst vergangenen
    # Verein/Gegner und matcht NIE den aktuellen team_id. Ohne Sonderbehandlung
    # verliert der Filter oben dann ALLE Zeilen dieses Spielers (nicht nur die
    # Performance-Feature-Zeilen) - er faellt komplett aus history_df/today_df
    # und bekommt nie eine ML-Prognose (live bestaetigt 27.07.2026). Fuer
    # Spieler, bei denen wirklich KEINE Zeile matcht, werden die
    # Performance-Spalten stattdessen genullt (wie beim p_df.empty-Fall) -
    # der Spieler bleibt so mit "keine verwertbare Performance-Historie" statt
    # unsichtbar zu verschwinden.
    # Nur ueber die Marktwert-bekannten (taeglichen) Zeilen pruefen - die
    # zusaetzlichen Zukunfts-Fixture-Zeilen (mv noch unbekannt) matchen bei
    # JEDEM Spieler oft zufaellig, sagen aber nichts darueber, ob die
    # eigentlich relevanten mv-Zeilen brauchbare Performance-Daten haben.
    mv_known_mask = df["mv"].notna()
    never_matches = [
        pid
        for pid in df.loc[mv_known_mask & ~team_match, "player_id"].unique()
        if not team_match[mv_known_mask & (df["player_id"] == pid)].any()
    ]
    if never_matches:
        stale_mask = df["player_id"].isin(never_matches)
        for col in ("md", "p", "mp", "t1", "t2", "t1g", "t2g"):
            df.loc[stale_mask, col] = None
        team_match = team_match | stale_mask

    df = df[team_match]

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
    """Trainiert zwei Modell-Kandidaten per Zeit-Split (75/25, kein Shuffle,
    verhindert Data Leakage) - RandomForestRegressor (bisherige feste
    Parameter) gegen HistGradientBoostingRegressor (eingebautes
    Early-Stopping, oft besser bei Feature-Interaktionen). Gibt (models,
    metrics) oder None zurueck, wenn zu wenig Daten fuer einen sinnvollen
    Split/Training vorhanden sind. `models` enthaelt ALLE trainierten
    Kandidaten (Phase 4: werden beide fuer die taegliche Prognose
    gebraucht, um beide zu loggen), nicht mehr nur den Gewinner.
    metrics["model_type"] zeigt, welcher Kandidat nach Test-R2 gewonnen
    hat."""
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

    candidates = {
        "RandomForest": RandomForestRegressor(
            n_estimators=500,
            max_depth=20,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features="sqrt",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
        "HistGradientBoosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE),
    }

    models: dict[str, object] = {}
    per_model_metrics: dict[str, dict] = {}
    for name, candidate in candidates.items():
        candidate.fit(x_train, y_train)
        y_pred = candidate.predict(x_test)
        r2 = r2_score(y_test, y_pred)
        rmse = mean_squared_error(y_test, y_pred) ** 0.5
        mae = mean_absolute_error(y_test, y_pred)
        sign_accuracy = float(np.mean(np.sign(y_test) == np.sign(y_pred)) * 100)
        models[name] = candidate
        per_model_metrics[name] = {
            "rmse": round(rmse, 2),
            "mae": round(mae, 2),
            "r2": round(r2, 3),
            "sign_accuracy": round(sign_accuracy, 1),
        }

    best_name = max(per_model_metrics, key=lambda name: per_model_metrics[name]["r2"])
    metrics = {
        "model_type": best_name,
        **per_model_metrics[best_name],
        "train_rows": len(train),
        "test_rows": len(test),
        "per_model": per_model_metrics,
    }
    return models, metrics


def _walk_forward_backtest(history_df: pd.DataFrame) -> dict | None:
    """Beantwortet direkt "wie waere die Prognose damals gewesen" - ohne wie
    beim Live-Log (_evaluate_realized_accuracy) tage-/wochenlang auf echte
    Folgetage warten zu muessen. history_df enthaelt fuer JEDEN historischen
    Tag bereits das bekannte Ergebnis (mv_target); es reicht also, mehrere
    Cutoff-Tage rueckwirkend durchzugehen: Training nur auf Zeilen VOR dem
    Cutoff, Test auf den Zeilen GENAU am Cutoff-Tag, verglichen gegen den
    tatsaechlichen (ungeklippten) Marktwert-Sprung. Bewertet beide
    Modell-Kandidaten pro Fold, damit sichtbar wird, welches Modell nicht
    nur im aktuellen 75/25-Split (_train_and_evaluate), sondern ueber
    mehrere echte historische Tage hinweg konsistent gewinnt."""
    dates = sorted(history_df["date"].unique())
    if len(dates) <= BACKTEST_FOLDS:
        return None
    cutoffs = dates[-BACKTEST_FOLDS:]

    sign_hits: dict[str, list[bool]] = {"RandomForest": [], "HistGradientBoosting": []}
    abs_errors: dict[str, list[float]] = {"RandomForest": [], "HistGradientBoosting": []}
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

        candidates = {
            "RandomForest": RandomForestRegressor(
                n_estimators=200,
                max_depth=20,
                min_samples_split=5,
                min_samples_leaf=2,
                max_features="sqrt",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
            "HistGradientBoosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE),
        }
        for name, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            sign_hits[name].extend((np.sign(y_test_actual) == np.sign(y_pred)).tolist())
            abs_errors[name].extend(np.abs(y_test_actual - y_pred).tolist())

    if not folds_run:
        return None

    per_model = {}
    for name, hits in sign_hits.items():
        if not hits:
            continue
        per_model[name] = {
            "sign_accuracy": round(float(np.mean(hits)) * 100, 1),
            "mae": round(float(np.mean(abs_errors[name])), 2),
            "n": len(hits),
        }
    if not per_model:
        return None
    return {"n_folds": folds_run, "per_model": per_model}


def backfill_prediction_log(days: int = 90) -> dict:
    """Einmalige Utility (dauerhaft im Code, nicht Teil des taeglichen Laufs):
    baut denselben Corpus wie ein normaler Lauf, aber statt nur der letzten
    BACKTEST_FOLDS Cutoffs werden bis zu `days` rollierende historische
    Cutoffs durchlaufen (begrenzt durch verfuegbare Kickbase-Historie UND
    genug Trainingszeilen je Cutoff - fruehe Tage im ~365-Tage-Fenster
    fallen typischerweise raus). Pro Fold werden ECHTE Pro-Spieler-
    predicted_delta-Werte fuer BEIDE Modelle gesammelt (nicht nur
    aggregiertes Hit/Miss wie _walk_forward_backtest) und als
    ml_prediction_log-Eintraege nach Firestore geschrieben - schliesst die
    Kaltstart-Luecke fuer die Trailing-30d-Live-Auswahl, ohne 90 echte
    Kalendertage abwarten zu muessen. Wiederverwendbar, falls die
    Firestore-Historie je zurueckgesetzt werden muss."""
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        print("Warnung: KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen, Backfill uebersprungen.", file=sys.stderr)
        return {"folds_run": 0, "entries_written": 0}

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    me = get_me(token, league_id)
    competition_id = me.get("cpi") or "1"
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)

    dates = sorted(history_df["date"].unique())
    cutoffs = dates[-days:] if len(dates) > days else dates

    entries = []
    folds_run = 0
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[TARGET]
        x_test = test[FEATURES]
        cutoff_date = pd.Timestamp(cutoff).date().isoformat()

        candidates = {
            "RandomForest": RandomForestRegressor(
                n_estimators=200,
                max_depth=20,
                min_samples_split=5,
                min_samples_leaf=2,
                max_features="sqrt",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
            "HistGradientBoosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE),
        }
        for model_type, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            entries.extend(
                {
                    "date": cutoff_date,
                    "player_id": player_id,
                    "model_type": model_type,
                    "predicted_delta": round(float(pred)),
                }
                for player_id, pred in zip(test["player_id"], y_pred)
            )

    if entries and os.environ.get("FIRESTORE_ENABLED"):
        fs_client = firestore_db.connect()
        firestore_db.upsert_prediction_log_entries(fs_client, entries)

    return {"folds_run": folds_run, "entries_written": len(entries)}


def _load_prediction_log() -> list[dict]:
    """Liest bei FIRESTORE_ENABLED aus Firestore (persistiert ueber CI-Laeufe
    hinweg, anders als die lokale Datei) - Firestore-Lesefehler faellt
    zurueck auf die lokale Datei statt die Pipeline zu crashen. Ohne
    FIRESTORE_ENABLED (lokaler Testlauf) bleibt alles wie bisher."""
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            return firestore_db.get_prediction_log_entries(firestore_db.connect())
        except Exception as exc:
            print(
                f"Warnung: ml_prediction_log-Lesezugriff fehlgeschlagen, nutze lokale Datei: {exc}",
                file=sys.stderr,
            )
    if not PREDICTION_LOG_PATH.exists():
        return []
    entries = []
    for line in PREDICTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def _save_prediction_log(entries: list[dict]) -> None:
    """Schreibt das Log neu: dedupliziert nach (date, player_id) - haelt den
    LETZTEN Eintrag pro Schluessel (main.py und dashboard_export.py rufen
    beide taeglich predict_market_value_changes() auf, ein zweiter Lauf am
    selben Tag darf keine doppelte Zeile erzeugen) - und begrenzt auf
    LOG_RETENTION_DAYS relativ zum juengsten Eintrag, waechst sonst
    unbegrenzt."""
    if not entries:
        return
    # .get() statt e["model_type"]: alte Log-Eintraege aus der Zeit vor
    # Phase 4 (ohne model_type-Feld) bleiben laut Plan bewusst unmigriert
    # liegen und duerfen den Speichervorgang nicht mit einem KeyError
    # crashen - sie landen einfach unter demselben (date, player_id, None)
    # -Schluessel wie bisher.
    deduped = {(e["date"], e["player_id"], e.get("model_type")): e for e in entries}
    kept_entries = list(deduped.values())
    latest = max(datetime.date.fromisoformat(e["date"]) for e in kept_entries)
    cutoff = latest - datetime.timedelta(days=LOG_RETENTION_DAYS)
    kept_entries = [e for e in kept_entries if datetime.date.fromisoformat(e["date"]) >= cutoff]
    PREDICTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREDICTION_LOG_PATH.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in kept_entries) + "\n", encoding="utf-8"
    )

    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            # Nur den juengsten Tag an Firestore senden, nicht die komplette
            # LOG_RETENTION_DAYS-Historie: die ist hier schon lokal dedupliziert
            # und aeltere Tage wurden an frueheren Laeufen bereits geschrieben
            # (Doc-Id ist date_player_id-basiert) - ein voller Re-Sync bei jedem
            # Lauf waere unnoetiges Schreibvolumen (Firestore Spark-Free-Tier
            # hat ein taegliches Schreib-Kontingent).
            todays_entries = [e for e in kept_entries if e["date"] == latest.isoformat()]
            fs_client = firestore_db.connect()
            firestore_db.upsert_prediction_log_entries(fs_client, todays_entries)
        except Exception as exc:  # ein Firestore-Ausfall darf die Pipeline nie brechen
            print(
                f"Warnung: Firestore-Schreibzugriff fuer ml_prediction_log fehlgeschlagen: {exc}",
                file=sys.stderr,
            )


def _build_mv_lookup(corpus: pd.DataFrame) -> dict[tuple[str, str], float]:
    """(player_id, ISO-Datum) -> Marktwert, aus dem schon geladenen Corpus -
    kein zweiter Log fuer 'was tatsaechlich passiert ist' noetig, Kickbase
    liefert die echte Historie ohnehin bei jedem Lauf frisch."""
    lookup: dict[tuple[str, str], float] = {}
    for player_id, date, mv in zip(corpus["player_id"], corpus["date"], corpus["mv"]):
        if pd.notna(mv) and pd.notna(date):
            lookup[(player_id, pd.Timestamp(date).date().isoformat())] = float(mv)
    return lookup


def _summarize_window(evaluated: list[dict], today: str, days: int) -> dict | None:
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    window = [e for e in evaluated if e["date"] >= cutoff]
    if not window:
        return None
    sign_accuracy = sum(1 for e in window if e["sign_correct"]) / len(window) * 100
    mae = sum(e["abs_error"] for e in window) / len(window)
    return {"n": len(window), "sign_accuracy": round(sign_accuracy, 1), "mae": round(mae, 2)}


def _evaluate_realized_accuracy_by_model(log_entries: list[dict], mv_lookup: dict, today: str) -> dict[str, dict]:
    """Wie zuvor, aber getrennt pro model_type - ermoeglicht echten
    Kopf-an-Kopf-Vergleich ueber die Zeit statt nur 'der jeweilige
    Tagessieger, egal welches Modell das war'. Log-Eintraege ohne
    model_type (altes Schema, vor Phase 4) werden uebersprungen statt
    einen KeyError zu werfen - bewusst keine Migration noetig."""
    evaluated_by_model: dict[str, list[dict]] = {"RandomForest": [], "HistGradientBoosting": []}
    for entry in log_entries:
        model_type = entry.get("model_type")
        if model_type not in evaluated_by_model:
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        evaluated_by_model[model_type].append(
            {
                "date": date,
                "sign_correct": np.sign(entry["predicted_delta"]) == np.sign(actual_delta),
                "abs_error": abs(entry["predicted_delta"] - actual_delta),
            }
        )
    return {
        name: {f"realized_{days}d": _summarize_window(evaluated, today, days) for days in ACCURACY_WINDOWS_DAYS}
        for name, evaluated in evaluated_by_model.items()
    }


def _build_accuracy_trend(log_entries: list[dict], mv_lookup: dict, today: str) -> list[dict]:
    """Taegliche realisierte sign_accuracy pro Modell UEBER DIE KOMPLETTE
    Historie (nicht nur 'heute' wie _evaluate_realized_accuracy_by_model) -
    Rohdaten fuer den Trend-Chart im 'ML-Genauigkeit'-Tab. Gruppiert nach
    Log-Datum, ein Eintrag pro Tag mit beiden Modellen nebeneinander."""
    by_date: dict[str, dict[str, list[bool]]] = {}
    for entry in log_entries:
        model_type = entry.get("model_type")
        if model_type not in ("RandomForest", "HistGradientBoosting"):
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        sign_correct = bool(np.sign(entry["predicted_delta"]) == np.sign(actual_delta))
        by_date.setdefault(date, {"RandomForest": [], "HistGradientBoosting": []})[model_type].append(sign_correct)

    trend = []
    for date in sorted(by_date):
        day = {"date": date}
        for model_type, hits in by_date[date].items():
            day[model_type] = round(float(np.mean(hits)) * 100, 1) if hits else None
        trend.append(day)
    return trend


def _select_live_model(realized_by_model: dict[str, dict], synthetic_winner: str) -> tuple[str, str]:
    """Waehlt das Modell fuer die tatsaechliche Live-Prognose. Bevorzugt echte
    Trailing-30d-sign_accuracy sobald BEIDE Modelle genug Realdaten haben
    (MIN_REALIZED_SAMPLES_FOR_SELECTION), sonst Fallback auf den heutigen
    synthetischen Split (bisheriges Verhalten) - vermeidet eine Entscheidung
    auf Basis von 1-2 verrauschten Datenpunkten in der Kaltstart-Phase."""
    rf_window = realized_by_model.get("RandomForest", {}).get("realized_30d")
    hgb_window = realized_by_model.get("HistGradientBoosting", {}).get("realized_30d")
    if (
        rf_window and hgb_window
        and rf_window["n"] >= MIN_REALIZED_SAMPLES_FOR_SELECTION
        and hgb_window["n"] >= MIN_REALIZED_SAMPLES_FOR_SELECTION
    ):
        winner = "RandomForest" if rf_window["sign_accuracy"] >= hgb_window["sign_accuracy"] else "HistGradientBoosting"
        return winner, "realized_trailing_30d"
    return synthetic_winner, "synthetic_split_fallback"


def _append_todays_predictions(today_df: pd.DataFrame, predictions_by_model: dict[str, dict[str, float]]) -> None:
    new_entries = [
        {
            "date": pd.Timestamp(date).date().isoformat(),
            "player_id": player_id,
            "model_type": model_type,
            "predicted_delta": predictions[player_id],
        }
        for model_type, predictions in predictions_by_model.items()
        for player_id, date in zip(today_df["player_id"], today_df["date"])
        if player_id in predictions
    ]
    log = _load_prediction_log() + new_entries
    _save_prediction_log(log)


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
        models, metrics = trained
        synthetic_winner = metrics["model_type"]

        backtest = _walk_forward_backtest(history_df)
        if backtest is not None:
            metrics["backtest"] = backtest

        # Spieler ohne verwertbaren "naechster Spieltag" (kein Spiel seit
        # Jahren wie Funk, oder Performance-Historie komplett leer wie
        # Suleiman - beides live bestaetigt 27.07.2026) haben NaN bei
        # days_to_next und wuerden sonst komplett aus der Prognose
        # herausfallen. Fuer die Vorhersage (NICHT fuers Training, siehe
        # history_df.dropna oben in _engineer_features) reicht der
        # Median aus der Trainingshistorie als neutrale Annahme - lieber
        # eine etwas unsicherere Prognose als gar keine.
        median_days_to_next = history_df["days_to_next"].median()
        today_df = today_df.copy()
        today_df["days_to_next"] = today_df["days_to_next"].fillna(median_days_to_next)

        today_df = today_df.dropna(subset=["mv"] + FEATURES)
        if today_df.empty:
            print("Warnung: keine heutigen Zeilen mit vollstaendigen Features - ML-Prognose uebersprungen.", file=sys.stderr)
            return None

        today_iso = pd.Timestamp(corpus["date"].max()).date().isoformat()
        mv_lookup = _build_mv_lookup(corpus)
        log_entries = _load_prediction_log()
        realized_by_model = _evaluate_realized_accuracy_by_model(log_entries, mv_lookup, today_iso)
        metrics["realized_by_model"] = realized_by_model
        metrics["accuracy_trend"] = _build_accuracy_trend(log_entries, mv_lookup, today_iso)

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
        _append_todays_predictions(today_df, predictions_by_model)

        return {"predictions": predictions, "metrics": metrics}
    except (KickbaseError, RuntimeError) as exc:
        print(f"Warnung: ML-Marktwertprognose fehlgeschlagen, wird uebersprungen: {exc}", file=sys.stderr)
        return None


if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=int, default=None, metavar="DAYS")
    args = parser.parse_args()

    if args.backfill is not None:
        result = backfill_prediction_log(args.backfill)
        print(f"Backfill: {result['folds_run']} Folds, {result['entries_written']} Eintraege geschrieben.")
    else:
        result = predict_market_value_changes()
        if result is None:
            print("Keine Prognose verfuegbar (siehe Warnungen oben).")
        else:
            print("Metriken:", result["metrics"])
            print(f"Anzahl Spieler mit Prognose: {len(result['predictions'])}")
            sample = list(result["predictions"].items())[:10]
            print("Beispiele:", sample)
