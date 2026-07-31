"""ML-Marktwertprognose: taeglich neu trainiertes Modell (RandomForest oder
HistGradientBoosting, siehe _train_and_evaluate fuer die Kandidaten,
_select_live_model fuer die tatsaechliche Live-Auswahl) auf Basis von
Kickbase's eigener 365-Tage-Marktwert- und Performance-Historie.

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
trainiert (kein persistiertes Modell-File). Einzige Ausnahme: taegliche
Prognosen (Datum, Spieler, prognostizierte Aenderung) werden kurzlebig
geloggt (`ml_prediction_log`/lokale data/ml_prediction_log.jsonl als
Fallback), damit die tatsaechliche Tag-fuer-Tag-Genauigkeit rueckwirkend
berechnet werden kann - der Corpus liefert die echte Wertaenderung dafuer
bereits mit, kein zweiter Log fuer "was tatsaechlich passiert ist" noetig.
Seit dem Firestore-Read-Quota-Fix (2026-07-28) ist die eigentliche,
langfristige Historie NICHT mehr diese Rohdaten-Collection, sondern die
aggregierte `ml_accuracy_daily`-Collection (2 Dokumente/Tag statt ~900) -
siehe _build_daily_accuracy_updates/_realized_by_model_from_daily/
_trend_from_daily.
"""

from __future__ import annotations

from collections import defaultdict
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
    select_league,
)

FEATURES = [
    "p", "mv", "days_to_next",
    "mv_change_1d", "mv_trend_1d",
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence",
    "days_since_last_status_change", "status_change_count_90d",
]
TARGET = "mv_target_clipped"
TARGET_3D = "mv_target_3d_clipped"

MARKET_VALUE_TIMEFRAME = 365
LAST_PERFORMANCE_VALUES = 50
MIN_TRAINING_ROWS = 200
RANDOM_STATE = 42
_EPOCH = datetime.date(1970, 1, 1)

PREDICTION_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "ml_prediction_log.jsonl"
LOG_RETENTION_DAYS = 90
ACCURACY_WINDOWS_DAYS = (7, 30)
MIN_REALIZED_SAMPLES_FOR_SELECTION = 14
EVALUATION_LOOKBACK_DAYS = 3

# Anzahl rollierender Trainingsschnitte fuer den Walk-Forward-Backtest (siehe
# _walk_forward_backtest) - bewusst klein gehalten, jeder Fold trainiert beide
# Modell-Kandidaten neu, kostet also spuerbar Laufzeit.
BACKTEST_FOLDS = 6
BACKTEST_MIN_TRAIN_ROWS = MIN_TRAINING_ROWS

FITNESS_NO_HISTORY_DAYS = 9999  # Platzhalter: kein Fitness-Ereignis vor diesem Datum bekannt (Cold-Start oder Spieler nie im fitness_history_log)
FITNESS_COUNT_WINDOW_DAYS = 90

# Aggregierter Sicherheits-Check: schlagen zu viele der ersten Abrufe fehl,
# lieber den ganzen Corpus-Aufbau abbrechen als auf degradierten Daten zu
# trainieren (Rate-Limit? API-Aenderung?).
_ABORT_FAILURE_SAMPLE = 50
_ABORT_FAILURE_RATE = 0.5


def _max_workers() -> int:
    return int(os.environ.get("MARKET_PREDICTOR_MAX_WORKERS", 8))


def _load_fitness_events_by_player() -> dict[str, list[dict]]:
    """Liest fitness_history_log (siehe firestore_db.get_fitness_history)
    einmal pro Lauf und gruppiert nach player_id - Basis fuer
    _fitness_features_as_of() in _fetch_player_training_frame(). Leeres
    Dict bei deaktiviertem Firestore oder Lesefehler (gleiches
    Resilienz-Muster wie _load_recent_prediction_log) - jeder Spieler
    bekommt dann ueberall den Cold-Start-Platzhalter, kein Crash."""
    events_by_player: dict[str, list[dict]] = defaultdict(list)
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            for entry in firestore_db.get_fitness_history(firestore_db.connect()):
                events_by_player[entry["player_id"]].append(entry)
        except Exception as exc:
            print(f"Warnung: fitness_history_log-Lesezugriff fehlgeschlagen: {exc}", file=sys.stderr)
            return {}
    return dict(events_by_player)


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
    df = df.sort_values("date").reset_index(drop=True)
    # Rollierender Schnitt der letzten 3 SPIELE (nicht Kalendertage) -
    # Verletzungs-/Fitness-Proxy: wenig/keine Minuten in den letzten Spielen
    # korreliert mit "nicht im Fokus", ohne dass echte historische
    # Verletzungsdaten vorliegen muessten (siehe Konversation 2026-07-30 -
    # Kickbase liefert status_code nur fuer JETZT, nicht als Zeitreihe).
    # min_periods=1 statt 3, damit die ersten 1-2 Spiele eines Spielers
    # nicht NaN werden, sondern ueber die bis dahin verfuegbaren Spiele
    # mitteln.
    df["mp_avg_3"] = df["mp"].rolling(3, min_periods=1).mean()
    return df


def _fitness_features_as_of(events: list[dict], as_of_date: datetime.date) -> dict:
    """events: EIN Spielers Eintraege aus fitness_history_log (jeweils
    {'date': 'YYYY-MM-DD', 'from_status_code': int, 'to_status_code': int}),
    Reihenfolge egal. as_of_date: das Datum der Trainings-/Prognose-Zeile.
    Nur Ereignisse mit event_date <= as_of_date fliessen ein - kein
    Lookahead in die Zukunft dieser Zeile. Siehe
    docs/superpowers/specs/2026-07-31-fitness-history-design.md,
    Abschnitt 'ML-Integration'."""
    relevant = [e for e in events if datetime.date.fromisoformat(e["date"]) <= as_of_date]
    if not relevant:
        return {"days_since_last_status_change": FITNESS_NO_HISTORY_DAYS, "status_change_count_90d": 0}
    last_date = max(datetime.date.fromisoformat(e["date"]) for e in relevant)
    days_since = (as_of_date - last_date).days
    cutoff = as_of_date - datetime.timedelta(days=FITNESS_COUNT_WINDOW_DAYS)
    count_90d = sum(1 for e in relevant if datetime.date.fromisoformat(e["date"]) > cutoff)
    return {"days_since_last_status_change": days_since, "status_change_count_90d": count_90d}


def _fetch_player_training_frame(
    token: str, league_id: str, competition_id: str, player_id: str, team_id: str,
    fitness_events_by_player: dict[str, list[dict]],
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
        for col in ("md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"):
            merged[col] = None
    else:
        p_df["date"] = p_df["date"].astype("datetime64[us]")
        merged = pd.merge_asof(mv_df, p_df, on="date", direction="backward")
        future_p = p_df[p_df["date"] > mv_df["date"].max()]
        if not future_p.empty:
            merged = pd.concat([merged, future_p], ignore_index=True)

    merged["player_id"] = player_id
    merged["team_id"] = team_id

    events = fitness_events_by_player.get(player_id, [])
    fitness_features = merged["date"].apply(lambda ts: _fitness_features_as_of(events, ts.date()))
    merged["days_since_last_status_change"] = fitness_features.apply(lambda f: f["days_since_last_status_change"])
    merged["status_change_count_90d"] = fitness_features.apply(lambda f: f["status_change_count_90d"])

    return merged


def _build_corpus(
    token: str, league_id: str, competition_id: str, fitness_events_by_player: dict[str, list[dict]]
) -> pd.DataFrame:
    player_to_team = _fetch_competition_player_ids(token, competition_id)
    if not player_to_team:
        raise RuntimeError("Keine Spieler-Ids ueber get_team_players() gefunden")

    frames: list[pd.DataFrame] = []
    checked = 0
    failures = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers()) as executor:
        futures = {
            executor.submit(_fetch_player_training_frame, token, league_id, competition_id, pid, tid, fitness_events_by_player): pid
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
        for col in ("md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"):
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
    df["mv_next_3d"] = df.groupby("player_id")["mv"].shift(-3)
    df["mv_target_3d"] = df["mv_next_3d"] - df["mv"]
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

    q1_3d = df["mv_target_3d"].quantile(0.25)
    q3_3d = df["mv_target_3d"].quantile(0.75)
    iqr_3d = q3_3d - q1_3d
    df["mv_target_3d_clipped"] = df["mv_target_3d"].clip(q1_3d - 2.5 * iqr_3d, q3_3d + 2.5 * iqr_3d)

    df = df.fillna({"market_divergence": 1, "mv_change_3d": 0, "mv_vol_3d": 0, "p": 0, "mp_avg_3": 0})

    mv_known = df[df["mv"].notna()]
    today_df = mv_known.sort_values("date").groupby("player_id").tail(1)
    history_df = mv_known.drop(today_df.index)
    history_df = history_df.dropna(
        subset=["mv_change_1d", "next_md", "days_to_next", "mv_next_day", "mv_target", "mv_target_clipped"]
    )

    return history_df, today_df


def _infer_today(corpus: pd.DataFrame) -> str:
    """Neuestes Datum mit TATSAECHLICH bekanntem Marktwert - NICHT einfach
    corpus["date"].max(), das durch zukuenftige Fixture-Zeilen verzerrt
    werden kann: _fetch_player_training_frame() haengt fuer days_to_next
    kommende Spieltag-Zeilen an (future_p-Concat dort), deren mv noch
    unbekannt ist. Ohne diesen Filter landet man bei einem "heutigen" Datum
    Wochen in der Zukunft, sobald irgendein Spieler ein bekanntes kommendes
    Spiel hat - live gefunden 2026-07-30: realized_by_model blieb dadurch
    trotz 60 Tagen vorhandener Trailing-Daten dauerhaft None, weil der
    30/7-Tage-Cutoff dann jenseits aller echten Tage lag."""
    known = corpus[corpus["mv"].notna()]
    return pd.Timestamp(known["date"].max()).date().isoformat()


def _build_candidates() -> dict[str, object]:
    """Baut die zwei Modell-Kandidaten mit denselben Hyperparametern, die
    auch fuer die echte Live-Prognose (_train_and_evaluate) UND den
    Walk-Forward-Backtest (_walk_forward_backtest) verwendet werden - eine
    einzige Quelle statt zwei duplizierter Definitionen, damit historisch
    geloggte/gebacktestete Genauigkeit mit der echten Live-Prognose
    vergleichbar bleibt (vorher: sowohl backfill_prediction_log als auch
    _walk_forward_backtest nutzten unabhaengig eigene, abweichende
    Parameter - siehe Git-History).

    HistGradientBoosting-Parameter stammen aus einer randomisierten
    Hyperparameter-Suche (277 Konfigurationen, 30-Fold-Walk-Forward,
    2026-07-31): {learning_rate: 0.05, max_iter: 200, max_leaf_nodes: 127,
    min_samples_leaf: 20, l2_regularization: 0.0} lag bei 83.4%
    Richtungsgenauigkeit / MAE 25147 (Baseline mit sklearn-Standardwerten:
    82.4% / 25370) - mehrere unabhaengig gezogene Konfigurationen aus 3
    verschiedenen Bibliotheken (LightGBM/XGBoost/HistGradientBoosting)
    landeten konvergent im selben Bereich (viele Iterationen, niedrige
    Lernrate, hohe Blatt-Kapazitaet) - kein Einzeltreffer. LightGBM/XGBoost
    lagen minimal davor, aber HistGradientBoosting braucht keine neue
    Abhaengigkeit (bleibt bei reinem sklearn)."""
    return {
        "RandomForest": RandomForestRegressor(
            n_estimators=500,
            max_depth=20,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features="sqrt",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
        "HistGradientBoosting": HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_iter=200,
            max_leaf_nodes=127,
            min_samples_leaf=20,
            l2_regularization=0.0,
            random_state=RANDOM_STATE,
        ),
    }


def _train_and_evaluate(history_df: pd.DataFrame, target_col: str = TARGET):
    """Trainiert zwei Modell-Kandidaten per Zeit-Split (75/25, kein Shuffle,
    verhindert Data Leakage) - RandomForestRegressor (bisherige feste
    Parameter) gegen HistGradientBoostingRegressor (eingebautes
    Early-Stopping, oft besser bei Feature-Interaktionen). Gibt (models,
    metrics) oder None zurueck, wenn zu wenig Daten fuer einen sinnvollen
    Split/Training vorhanden sind. `models` enthaelt ALLE trainierten
    Kandidaten (Phase 4: werden beide fuer die taegliche Prognose
    gebraucht, um beide zu loggen), nicht mehr nur den Gewinner.
    metrics["model_type"] zeigt, welcher Kandidat nach Test-R2 gewonnen
    hat. Erweitert um target_col: die Zeilen ohne bekannten Zielwert
    (z.B. die letzten paar Tage pro Spieler beim 3-Tage-Ziel, siehe
    TARGET_3D) werden hier - und nur hier, nicht global auf history_df -
    verworfen, damit ein zweites Trainingsziel die Datenbasis des ersten
    nicht verkleinert."""
    df = history_df.dropna(subset=[target_col])
    if len(df) < MIN_TRAINING_ROWS:
        return None

    df = df.sort_values("date").reset_index(drop=True)
    split_idx = int(len(df) * 0.75)
    split_date = df["date"].iloc[split_idx]
    train = df[df["date"] < split_date]
    test = df[df["date"] >= split_date]

    if train.empty or test.empty:
        return None

    x_train, y_train = train[FEATURES], train[target_col]
    x_test, y_test = test[FEATURES], test[target_col]

    candidates = _build_candidates()

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


def _walk_forward_backtest(history_df: pd.DataFrame, target_col: str = TARGET) -> dict | None:
    """Beantwortet direkt "wie waere die Prognose damals gewesen" - ohne wie
    beim Live-Log (_realized_by_model_from_daily) tage-/wochenlang auf echte
    Folgetage warten zu muessen. history_df enthaelt fuer JEDEN historischen
    Tag bereits das bekannte Ergebnis (mv_target); es reicht also, mehrere
    Cutoff-Tage rueckwirkend durchzugehen: Training nur auf Zeilen VOR dem
    Cutoff, Test auf den Zeilen GENAU am Cutoff-Tag, verglichen gegen den
    tatsaechlichen (ungeklippten) Marktwert-Sprung. Bewertet beide
    Modell-Kandidaten pro Fold, damit sichtbar wird, welches Modell nicht
    nur im aktuellen 75/25-Split (_train_and_evaluate), sondern ueber
    mehrere echte historische Tage hinweg konsistent gewinnt.

    target_col (Default TARGET) waehlt das Trainingsziel; unclipped_col
    (target_col ohne "_clipped"-Suffix) ist die Spalte, gegen die der
    TATSAECHLICHE Ausgang verglichen wird. Sowohl train als auch test
    werden auf ihre jeweils relevante Zielspalte hin von NaN befreit -
    bei TARGET (1 Tag) heute ein No-Op, aber Voraussetzung dafuer, dass
    ein 3-Tage-Ziel (TARGET_3D) hier wiederverwendbar ist: dessen letzte
    Tage pro Spieler (shift(-3)) kennen ihren Ausgang noch nicht, weder
    beim Training noch - unabhaengig davon, pro Cutoff - beim Test. Ohne
    den Test-seitigen Drop wuerde eine einzelne NaN-Zeile in y_test_actual
    via np.sign/np.abs in sign_hits/abs_errors einsickern und, weil
    abs_errors ueber ALLE Folds aufsummiert wird, den finalen mae fuer
    BEIDE Modelle komplett auf NaN kippen."""
    dates = sorted(history_df["date"].unique())
    if len(dates) <= BACKTEST_FOLDS:
        return None
    cutoffs = dates[-BACKTEST_FOLDS:]

    sign_hits: dict[str, list[bool]] = {"RandomForest": [], "HistGradientBoosting": []}
    abs_errors: dict[str, list[float]] = {"RandomForest": [], "HistGradientBoosting": []}
    folds_run = 0

    unclipped_col = target_col.removesuffix("_clipped")
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff].dropna(subset=[target_col])
        test = history_df[history_df["date"] == cutoff].dropna(subset=[unclipped_col])
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[target_col]
        x_test = test[FEATURES]
        y_test_actual = test[unclipped_col]

        # _build_candidates() statt eigener Kopie - vorher hatte dieser
        # Backtest eigene, von der echten Live-Prognose abweichende
        # Parameter (RandomForest n_estimators=200 statt 500), genau die
        # Inkonsistenz-Klasse, die _build_candidates()s Docstring schon
        # fuer den Backfill-Pfad beschreibt.
        candidates = _build_candidates()
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
    fallen typischerweise raus). Anders als der Live-Pfad kennt jeder
    Walk-Forward-Fold Prognose UND tatsaechlichen Wert (mv_target) im
    selben Schritt - schreibt deshalb DIREKT Tages-Aggregate nach
    ml_accuracy_daily, keine Rohdaten-Zwischenstation noetig (auch das
    spart Schreibvolumen: 2 Dokumente/Tag statt 2 x ~450). Wiederverwendbar,
    falls die Firestore-Historie je zurueckgesetzt werden muss."""
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        print("Warnung: KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen, Backfill uebersprungen.", file=sys.stderr)
        return {"folds_run": 0, "days_written": 0}

    token, _user, leagues = login(email, password)
    league_id = select_league(leagues)["id"]
    me = get_me(token, league_id)
    competition_id = me.get("cpi") or "1"
    fitness_events_by_player = _load_fitness_events_by_player()
    corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player)
    history_df, _today_df = _engineer_features(corpus)

    dates = sorted(history_df["date"].unique())
    cutoffs = dates[-days:] if len(dates) > days else dates

    daily_updates = []
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
        cutoff_date = pd.Timestamp(cutoff).date().isoformat()

        candidates = _build_candidates()
        for model_type, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            sign_correct = np.sign(y_test_actual) == np.sign(y_pred)
            abs_error = np.abs(y_test_actual - y_pred)
            daily_updates.append(
                {
                    "date": cutoff_date,
                    "model_type": model_type,
                    "n": int(len(sign_correct)),
                    "sign_correct": int(sign_correct.sum()),
                    "abs_error_sum": float(abs_error.sum()),
                }
            )

    if daily_updates and os.environ.get("FIRESTORE_ENABLED"):
        try:
            fs_client = firestore_db.connect()
            firestore_db.upsert_accuracy_daily(fs_client, daily_updates)
        except Exception as exc:  # z.B. Firestore-Schreib-Quota (Spark-Free-Tier)
            print(
                f"Warnung: Firestore-Schreibzugriff fuer Backfill fehlgeschlagen (evtl. Quota-Limit) - "
                f"ein Teil der {len(daily_updates)} Tages-Aggregate ist evtl. schon angekommen: {exc}",
                file=sys.stderr,
            )

    return {"folds_run": folds_run, "days_written": len(daily_updates)}


def _load_local_prediction_log() -> list[dict]:
    """Liest AUSSCHLIESSLICH die lokale data/ml_prediction_log.jsonl (kein
    Firestore-Zugriff) - fuer die lokale Datei-Fallback-Pflege
    (_append_todays_predictions/_save_prediction_log), die ein
    Read-Modify-Write auf der KOMPLETTEN lokalen Datei braucht. Firestore
    braucht dafuer KEINEN vorherigen Read (Upsert ist idempotent per
    Doc-Id) - ein Firestore-Read hier waere reine Verschwendung."""
    if not PREDICTION_LOG_PATH.exists():
        return []
    entries = []
    for line in PREDICTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def _load_recent_prediction_log(today: str) -> list[dict]:
    """Liest NUR die letzten EVALUATION_LOOKBACK_DAYS Tage roher Pro-Spieler-
    Prognosen (Firestore serverseitig datumsgefiltert bei FIRESTORE_ENABLED,
    sonst die lokale Datei client-seitig gefiltert) - genug um neu
    auswertbare Eintraege zu finden, OHNE die komplette (taeglich
    wachsende) Historie zu scannen. Firestore-Lesefehler faellt auf die
    lokale Datei zurueck statt zu crashen."""
    since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=EVALUATION_LOOKBACK_DAYS)).isoformat()
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            return firestore_db.get_recent_prediction_log_entries(firestore_db.connect(), since, today)
        except Exception as exc:
            print(
                f"Warnung: ml_prediction_log-Lesezugriff fehlgeschlagen, nutze lokale Datei: {exc}",
                file=sys.stderr,
            )
    return [e for e in _load_local_prediction_log() if since <= e["date"] < today]


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


def _summarize_from_daily(daily_docs: list[dict], today: str, days: int) -> dict | None:
    """Wie zuvor `_summarize_window`, aber auf bereits AGGREGIERTEN
    Tages-/Modell-Dokumenten (ein Dokument pro Kalendertag, nicht pro
    Spieler) - Summiert n/sign_correct/abs_error_sum ueber das Fenster,
    statt jede Rohdaten-Zeile einzeln zu iterieren."""
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    window = [d for d in daily_docs if d["date"] >= cutoff]
    n = sum(d["n"] for d in window)
    if n == 0:
        return None
    sign_accuracy = sum(d["sign_correct"] for d in window) / n * 100
    mae = sum(d["abs_error_sum"] for d in window) / n
    return {"n": n, "sign_accuracy": round(sign_accuracy, 1), "mae": round(mae, 2)}


def _build_daily_accuracy_updates(recent_entries: list[dict], mv_lookup: dict, today: str) -> list[dict]:
    """Wertet alle in recent_entries bereits auswertbaren Eintraege aus
    (Datum < today, Folgetag-Marktwert im aktuellen Corpus bekannt) und
    aggregiert sie zu EINEM Dokument pro (date, model_type) - fuer
    ml_accuracy_daily. Log-Eintraege ohne model_type (altes Schema, vor
    Phase 4) werden uebersprungen statt einen KeyError zu werfen."""
    agg: dict[tuple[str, str], dict] = {}
    for entry in recent_entries:
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
        abs_error = abs(entry["predicted_delta"] - actual_delta)
        key = (date, model_type)
        bucket = agg.setdefault(key, {"date": date, "model_type": model_type, "n": 0, "sign_correct": 0, "abs_error_sum": 0.0})
        bucket["n"] += 1
        bucket["sign_correct"] += int(sign_correct)
        bucket["abs_error_sum"] += abs_error
    return list(agg.values())


def _realized_by_model_from_daily(daily_docs: list[dict], today: str) -> dict[str, dict]:
    """Trailing-Fenster-Zusammenfassung pro Modell aus bereits gespeicherten
    Tages-Aggregaten (ml_accuracy_daily) - ersetzt die alte, Rohdaten-
    basierte _evaluate_realized_accuracy_by_model. Externe Rueckgabeform
    ist IDENTISCH zur alten Funktion (dict[model_type, dict[fenster_label,
    summary]])."""
    by_model: dict[str, list[dict]] = {"RandomForest": [], "HistGradientBoosting": []}
    for doc in daily_docs:
        if doc.get("model_type") in by_model:
            by_model[doc["model_type"]].append(doc)
    return {
        name: {f"realized_{days}d": _summarize_from_daily(docs, today, days) for days in ACCURACY_WINDOWS_DAYS}
        for name, docs in by_model.items()
    }


def _trend_from_daily(daily_docs: list[dict]) -> list[dict]:
    """Taegliche realisierte sign_accuracy pro Modell fuer den Trend-Chart -
    liest direkt aus bereits gespeicherten ml_accuracy_daily-Aggregaten
    (keine Rohdaten/mv_lookup mehr noetig, die Auswertung ist schon
    passiert als das jeweilige Aggregat geschrieben wurde). Externe
    Rueckgabeform ist IDENTISCH zur alten Funktion (Liste von
    {date, RandomForest, HistGradientBoosting})."""
    by_date: dict[str, dict] = {}
    for doc in daily_docs:
        model_type = doc.get("model_type")
        if model_type not in ("RandomForest", "HistGradientBoosting"):
            continue
        day = by_date.setdefault(doc["date"], {"date": doc["date"]})
        day[model_type] = round(doc["sign_correct"] / doc["n"] * 100, 1) if doc["n"] else None
    return [by_date[date] for date in sorted(by_date)]


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
    log = _load_local_prediction_log() + new_entries
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
        league_id = select_league(leagues)["id"]
        me = get_me(token, league_id)
        competition_id = me.get("cpi") or "1"

        fitness_events_by_player = _load_fitness_events_by_player()
        corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player)
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

        today_iso = _infer_today(corpus)
        mv_lookup = _build_mv_lookup(corpus)

        recent_entries = _load_recent_prediction_log(today_iso)
        daily_updates = _build_daily_accuracy_updates(recent_entries, mv_lookup, today_iso)
        if daily_updates and os.environ.get("FIRESTORE_ENABLED"):
            try:
                firestore_db.upsert_accuracy_daily(firestore_db.connect(), daily_updates)
            except Exception as exc:
                print(f"Warnung: Firestore-Schreibzugriff fuer ml_accuracy_daily fehlgeschlagen: {exc}", file=sys.stderr)

        daily_docs: list[dict] = []
        if os.environ.get("FIRESTORE_ENABLED"):
            try:
                daily_docs = firestore_db.get_accuracy_daily(firestore_db.connect())
            except Exception as exc:
                print(f"Warnung: ml_accuracy_daily-Lesezugriff fehlgeschlagen: {exc}", file=sys.stderr)

        realized_by_model = _realized_by_model_from_daily(daily_docs, today_iso)
        metrics["realized_by_model"] = realized_by_model
        metrics["accuracy_trend"] = _trend_from_daily(daily_docs)
        metrics["synthetic_winner"] = synthetic_winner

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
        print(f"Backfill: {result['folds_run']} Folds, {result['days_written']} Tages-Aggregate geschrieben.")
    else:
        result = predict_market_value_changes()
        if result is None:
            print("Keine Prognose verfuegbar (siehe Warnungen oben).")
        else:
            print("Metriken:", result["metrics"])
            print(f"Anzahl Spieler mit Prognose: {len(result['predictions'])}")
            sample = list(result["predictions"].items())[:10]
            print("Beispiele:", sample)
