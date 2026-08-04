import datetime
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.market_predictor import (
    _summarize_from_daily,
    _build_daily_accuracy_updates,
    _realized_by_model_from_daily,
    _trend_from_daily,
    _load_local_prediction_log,
    _load_recent_prediction_log,
    _append_todays_predictions,
    _save_prediction_log,
    _select_live_model,
    _infer_today,
    _parse_minutes,
    _performance_frame,
    _change_recency_features,
    _sentiment_features_as_of,
    _fetch_player_training_frame,
    _build_corpus,
    _load_change_events_by_player,
    _load_news_events_by_player,
    _engineer_features,
    NO_HISTORY_DAYS_PLACEHOLDER,
    SENTIMENT_WINDOW_DAYS,
    _train_and_evaluate,
    _walk_forward_backtest,
    _train_and_track_horizon,
    predict_market_value_changes,
    TARGET,
    TARGET_3D,
    FEATURES,
)
from src.market_predictor import backfill_prediction_log, _build_candidates


class LoadLocalPredictionLogTests(unittest.TestCase):
    def test_never_touches_firestore(self):
        with patch("src.market_predictor.firestore_db.connect") as mock_connect:
            _load_local_prediction_log()
            mock_connect.assert_not_called()


class LoadRecentPredictionLogTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_recent_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_passes_date_filter_to_firestore(self, mock_connect, mock_get):
        mock_get.return_value = []
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            _load_recent_prediction_log("2026-07-28", horizon_days=1)
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[1], "2026-07-25")  # today - EVALUATION_LOOKBACK_DAYS(3)
        self.assertEqual(mock_get.call_args.args[2], "2026-07-28")  # exklusive Obergrenze: heute noch nicht auswertbar

    @patch("src.market_predictor.firestore_db.get_recent_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_falls_back_to_local_file_filtered_by_range_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch("src.market_predictor._load_local_prediction_log") as mock_local:
            mock_local.return_value = [
                {"date": "2026-07-20", "player_id": "p0", "model_type": "RandomForest", "predicted_delta": 1},
                {"date": "2026-07-26", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 2},
                {"date": "2026-07-28", "player_id": "p2", "model_type": "RandomForest", "predicted_delta": 3},
            ]
            with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
                result = _load_recent_prediction_log("2026-07-28", horizon_days=1)
        self.assertEqual([e["player_id"] for e in result], ["p1"])


class SelectLiveModelTests(unittest.TestCase):
    def test_falls_back_to_synthetic_when_not_enough_realized_samples(self):
        realized = {
            "RandomForest": {"realized_30d": {"n": 5, "sign_accuracy": 80.0, "mae": 100}},
            "HistGradientBoosting": {"realized_30d": {"n": 5, "sign_accuracy": 60.0, "mae": 100}},
        }
        name, reason = _select_live_model(realized, "HistGradientBoosting")
        self.assertEqual(name, "HistGradientBoosting")
        self.assertEqual(reason, "synthetic_split_fallback")

    def test_picks_better_realized_model_when_enough_samples(self):
        realized = {
            "RandomForest": {"realized_30d": {"n": 20, "sign_accuracy": 80.0, "mae": 100}},
            "HistGradientBoosting": {"realized_30d": {"n": 20, "sign_accuracy": 60.0, "mae": 100}},
        }
        name, reason = _select_live_model(realized, "HistGradientBoosting")
        self.assertEqual(name, "RandomForest")
        self.assertEqual(reason, "realized_trailing_30d")


class SummarizeFromDailyTests(unittest.TestCase):
    def test_aggregates_over_window(self):
        daily = [
            {"date": "2026-07-20", "n": 450, "sign_correct": 300, "abs_error_sum": 45000.0},
            {"date": "2026-07-21", "n": 450, "sign_correct": 270, "abs_error_sum": 40000.0},
        ]
        result = _summarize_from_daily(daily, "2026-07-28", 30)
        self.assertEqual(result["n"], 900)
        self.assertAlmostEqual(result["sign_accuracy"], 63.3, places=1)

    def test_returns_none_when_window_empty(self):
        result = _summarize_from_daily([{"date": "2026-01-01", "n": 10, "sign_correct": 5, "abs_error_sum": 100.0}], "2026-07-28", 7)
        self.assertIsNone(result)


class BuildDailyAccuracyUpdatesTests(unittest.TestCase):
    def test_aggregates_by_date_and_model(self):
        entries = [
            {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100},
            {"date": "2026-07-27", "player_id": "p2", "model_type": "RandomForest", "predicted_delta": -50},
        ]
        mv_lookup = {
            ("p1", "2026-07-27"): 1000.0, ("p1", "2026-07-28"): 1200.0,
            ("p2", "2026-07-27"): 1000.0, ("p2", "2026-07-28"): 1200.0,
        }
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-29", horizon_days=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["n"], 2)
        self.assertEqual(result[0]["sign_correct"], 1)  # p1 richtig (positiv+positiv), p2 falsch (negativ vorhergesagt, tatsaechlich positiv)

    def test_skips_entries_without_model_type(self):
        entries = [{"date": "2026-07-01", "player_id": "p1", "predicted_delta": 100}]
        result = _build_daily_accuracy_updates(entries, {}, "2026-07-28", horizon_days=1)
        self.assertEqual(result, [])


class HorizonAwareAccuracyUpdatesTests(unittest.TestCase):
    def test_uses_horizon_days_shift_not_hardcoded_one_day(self):
        mv_lookup = {("p1", "2026-07-20"): 10_000_000, ("p1", "2026-07-23"): 10_003_000}
        entries = [{"date": "2026-07-20", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 3000}]
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-31", horizon_days=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["horizon_days"], 3)
        self.assertEqual(result[0]["sign_correct"], 1)

    def test_missing_horizon_shifted_value_skips_entry(self):
        mv_lookup = {("p1", "2026-07-20"): 10_000_000}  # kein Wert fuer +3 Tage bekannt
        entries = [{"date": "2026-07-20", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 3000}]
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-31", horizon_days=3)
        self.assertEqual(result, [])


class LoadRecentPredictionLogHorizonTests(unittest.TestCase):
    def test_returns_empty_dict_without_firestore_enabled_for_any_horizon(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.market_predictor._load_local_prediction_log", return_value=[]):
            self.assertEqual(_load_recent_prediction_log("2026-07-31", horizon_days=3), [])

    def test_filters_local_fallback_by_horizon(self):
        with patch.dict(os.environ, {}, clear=True), patch("src.market_predictor._load_local_prediction_log") as mock_local:
            mock_local.return_value = [
                {"date": "2026-07-29", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 1, "horizon_days": 1},
                {"date": "2026-07-29", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 2, "horizon_days": 3},
            ]
            result = _load_recent_prediction_log("2026-07-31", horizon_days=3)
        self.assertEqual([e["predicted_delta"] for e in result], [2])

    # --- Horizont-abhaengige Fensterbreite (finaler Review 2026-07-31) -------
    # Das Fenster ist [today - (EVALUATION_LOOKBACK_DAYS + horizon_days - 1),
    # today), untere Grenze INKLUSIV (`since <= e["date"] < today`). Fuer
    # Horizont N ist ein an Tag D geloggter Eintrag erst ab D+N auswertbar,
    # also braucht Horizont 3 ein um 2 Tage breiteres Fenster um dieselben 3
    # auswertbaren Tage (= Slack gegen einen verpassten Cron-Lauf) zu haben
    # wie Horizont 1. Mit today=2026-07-31:
    #   Horizont 1: since=07-28 -> auswertbar 07-28/29/30 (je +1 Tag bekannt)
    #   Horizont 3: since=07-26 -> auswertbar 07-26/27/28 (je +3 Tage bekannt)
    # 07-26 und 07-27 sind daher die entscheidenden Datumsangaben: vor dem Fix
    # (festes 3-Tage-Fenster fuer JEDEN Horizont) fielen sie fuer Horizont 3
    # aus dem Fenster, obwohl sie auswertbar sind - ein verpasster Lauf hat
    # ihre Genauigkeits-Daten dauerhaft verloren.
    _WINDOW_FIXTURE = [
        {"date": "2026-07-25", "player_id": "p_t6", "model_type": "RandomForest", "predicted_delta": 6, "horizon_days": 3},
        {"date": "2026-07-26", "player_id": "p_t5", "model_type": "RandomForest", "predicted_delta": 5, "horizon_days": 3},
        {"date": "2026-07-27", "player_id": "p_t4", "model_type": "RandomForest", "predicted_delta": 4, "horizon_days": 3},
        {"date": "2026-07-28", "player_id": "p_t3", "model_type": "RandomForest", "predicted_delta": 3, "horizon_days": 3},
    ]

    def test_horizon_3_window_is_widened_to_keep_same_slack_as_horizon_1(self):
        fixture = [dict(e) for e in self._WINDOW_FIXTURE]
        with patch.dict(os.environ, {}, clear=True), patch("src.market_predictor._load_local_prediction_log", return_value=fixture):
            result = _load_recent_prediction_log("2026-07-31", horizon_days=3)
        # 07-26/07-27 sind neu drin (waren vorher ausgeschlossen), 07-28 wie
        # bisher; 07-25 liegt auch nach der Erweiterung ausserhalb.
        self.assertEqual([e["date"] for e in result], ["2026-07-26", "2026-07-27", "2026-07-28"])

    def test_horizon_1_window_is_unchanged_by_the_widening(self):
        fixture = [dict(e) for e in self._WINDOW_FIXTURE]
        for entry in fixture:
            entry["horizon_days"] = 1
        with patch.dict(os.environ, {}, clear=True), patch("src.market_predictor._load_local_prediction_log", return_value=fixture):
            result = _load_recent_prediction_log("2026-07-31", horizon_days=1)
        # Unveraendert genau das alte Verhalten: nur 07-28 (== since, inklusiv)
        # liegt im Fenster - der Fix darf das produktive 1-Tages-Modell weder
        # verbreitern noch verengen (3 + 1 - 1 == 3).
        self.assertEqual([e["date"] for e in result], ["2026-07-28"])

    @patch("src.market_predictor.firestore_db.get_recent_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_firestore_date_filter_is_horizon_aware(self, mock_connect, mock_get):
        mock_get.return_value = []
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            _load_recent_prediction_log("2026-07-31", horizon_days=3)
        # Auch die serverseitige Query (der Produktionspfad) muss das breitere
        # Fenster anfragen, sonst kommen die neu auswertbaren Tage gar nicht an.
        self.assertEqual(mock_get.call_args.args[1], "2026-07-26")  # today - (3 + 3 - 1)
        self.assertEqual(mock_get.call_args.args[2], "2026-07-31")


class AppendTodaysPredictionsHorizonTests(unittest.TestCase):
    def test_logged_entries_include_horizon_days(self):
        with patch("src.market_predictor._load_local_prediction_log", return_value=[]), patch("src.market_predictor._save_prediction_log") as mock_save:
            today_df = pd.DataFrame({"player_id": ["p1"], "date": [pd.Timestamp("2026-07-31")]})
            _append_todays_predictions(today_df, {"RandomForest": {"p1": 500}}, horizon_days=3)
        logged = mock_save.call_args.args[0]
        self.assertEqual(logged[0]["horizon_days"], 3)


class SavePredictionLogHorizonDedupTests(unittest.TestCase):
    def test_1day_and_3day_entries_for_same_key_both_survive(self):
        """Dedup-Key in _save_prediction_log() ist (date, player_id,
        model_type, horizon_days) - ein 1-Tages- und ein 3-Tages-Eintrag
        fuer denselben (date, player_id, model_type) duerfen sich NICHT
        gegenseitig ueberschreiben (das war der eigentliche Zweck der
        Erweiterung des Dedup-Keys um horizon_days)."""
        entries = [
            {"date": "2026-07-31", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100, "horizon_days": 1},
            {"date": "2026-07-31", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 300, "horizon_days": 3},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "ml_prediction_log.jsonl"
            with patch("src.market_predictor.PREDICTION_LOG_PATH", tmp_path), patch.dict(os.environ, {}, clear=True):
                _save_prediction_log(entries)
                result = _load_local_prediction_log()
        self.assertEqual(len(result), 2)
        self.assertEqual(sorted(e["horizon_days"] for e in result), [1, 3])
        by_horizon = {e["horizon_days"]: e["predicted_delta"] for e in result}
        self.assertEqual(by_horizon, {1: 100, 3: 300})


class RealizedByModelFromDailyTests(unittest.TestCase):
    def test_separates_by_model(self):
        daily = [
            {"date": "2026-07-27", "model_type": "RandomForest", "n": 10, "sign_correct": 8, "abs_error_sum": 100.0},
            {"date": "2026-07-27", "model_type": "HistGradientBoosting", "n": 10, "sign_correct": 4, "abs_error_sum": 100.0},
        ]
        result = _realized_by_model_from_daily(daily, "2026-07-29")
        self.assertGreater(result["RandomForest"]["realized_7d"]["sign_accuracy"], result["HistGradientBoosting"]["realized_7d"]["sign_accuracy"])


class InferTodayTests(unittest.TestCase):
    def test_ignores_future_fixture_rows_without_known_market_value(self):
        # _fetch_player_training_frame() haengt fuer days_to_next zukuenftige
        # Fixture-Zeilen an (mv noch unbekannt, siehe future_p-Concat dort) -
        # corpus["date"].max() wuerde faelschlich diese Zukunfts-Zeile
        # liefern statt des letzten Tages mit echtem Marktwert (Live-Fund
        # 2026-07-30: dadurch blieb realized_by_model trotz 60 Tagen
        # vorhandener Trailing-Daten dauerhaft None).
        corpus = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-07-26", "2026-07-27", "2026-08-15"]),
            "mv": [10_000_000, 10_100_000, 10_200_000, None],
        })
        self.assertEqual(_infer_today(corpus), "2026-07-27")

    def test_uses_max_known_market_value_date_when_no_future_rows(self):
        corpus = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-07-26"]),
            "mv": [10_000_000, 10_100_000],
        })
        self.assertEqual(_infer_today(corpus), "2026-07-26")


class TrendFromDailyTests(unittest.TestCase):
    def test_builds_sorted_trend_with_both_models(self):
        daily = [
            {"date": "2026-07-27", "model_type": "RandomForest", "n": 10, "sign_correct": 6, "abs_error_sum": 50.0},
            {"date": "2026-07-26", "model_type": "HistGradientBoosting", "n": 10, "sign_correct": 5, "abs_error_sum": 50.0},
        ]
        trend = _trend_from_daily(daily)
        self.assertEqual([d["date"] for d in trend], ["2026-07-26", "2026-07-27"])
        self.assertEqual(trend[1]["RandomForest"], 60.0)
        self.assertIsNone(trend[1].get("HistGradientBoosting"))


class BackfillPredictionLogTests(unittest.TestCase):
    def test_returns_zero_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            result = backfill_prediction_log(90)
        self.assertEqual(result, {"folds_run": 0, "days_written": 0})


class BackfillPredictionLogTargetColTests(unittest.TestCase):
    def _history_df(self, target_col, n=210):
        import numpy as np
        unclipped_col = target_col.removesuffix("_clipped")
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rng = np.random.RandomState(7)
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            "avg_sentiment_7d": 0, "news_volume_7d": 0,
            target_col: rng.randn(n) * 5000,
            unclipped_col: rng.randn(n) * 5000,
        })
        return df

    @patch("src.market_predictor.firestore_db.upsert_accuracy_daily")
    @patch("src.market_predictor.firestore_db.connect", return_value="fake_client")
    @patch("src.market_predictor._load_change_events_by_player", return_value={})
    @patch("src.market_predictor._build_corpus", return_value=None)
    @patch("src.market_predictor.get_me", return_value={"cpi": "1"})
    @patch("src.market_predictor.select_league", return_value={"id": "league1"})
    @patch("src.market_predictor.login", return_value=("token", {}, []))
    @patch("src.market_predictor._engineer_features")
    def test_partial_nan_test_rows_are_dropped_not_averaged_into_nan(
        self, mock_engineer, mock_login, mock_select_league, mock_get_me,
        mock_build_corpus, mock_fitness_events, mock_connect, mock_upsert,
    ):
        # Regression, identisches Muster wie
        # WalkForwardBacktestTargetColTests.test_partial_nan_test_rows_are_dropped_not_averaged_into_nan:
        # eine Zeile mit NaN in der ungeklippten Zielspalte am letzten
        # Cutoff-Tag darf nicht in sign_correct/abs_error_sum einsickern.
        target_col = "alt_target_clipped"
        unclipped_col = "alt_target"
        df = self._history_df(target_col)
        extra_row = df.iloc[[-1]].copy()
        extra_row["player_id"] = "p2"
        extra_row[unclipped_col] = None
        df = pd.concat([df, extra_row], ignore_index=True)
        mock_engineer.return_value = (df, pd.DataFrame())

        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "e", "KICKBASE_PASSWORD": "p", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ):
            result = backfill_prediction_log(3, target_col=target_col, horizon_days=3)

        self.assertGreater(result["folds_run"], 0)
        mock_upsert.assert_called_once()
        entries = mock_upsert.call_args[0][1]
        last_cutoff = pd.Timestamp(df["date"].max()).date().isoformat()
        last_cutoff_entries = [e for e in entries if e["date"] == last_cutoff]
        self.assertTrue(last_cutoff_entries, "letzter Cutoff-Tag fehlt in den geschriebenen Aggregaten.")
        for entry in last_cutoff_entries:
            self.assertTrue(
                math.isfinite(entry["abs_error_sum"]),
                f"{entry}: abs_error_sum ist nicht finit - NaN-Zeile eingesickert.",
            )
            self.assertEqual(entry["n"], 1, "p2s NaN-Zeile darf nicht mitgezaehlt werden.")
            self.assertEqual(entry["horizon_days"], 3)

    @patch("src.market_predictor.firestore_db.upsert_accuracy_daily")
    @patch("src.market_predictor.firestore_db.connect", return_value="fake_client")
    @patch("src.market_predictor._load_change_events_by_player", return_value={})
    @patch("src.market_predictor._build_corpus", return_value=None)
    @patch("src.market_predictor.get_me", return_value={"cpi": "1"})
    @patch("src.market_predictor.select_league", return_value={"id": "league1"})
    @patch("src.market_predictor.login", return_value=("token", {}, []))
    @patch("src.market_predictor._engineer_features")
    def test_default_horizon_is_1_and_target_is_1d(
        self, mock_engineer, mock_login, mock_select_league, mock_get_me,
        mock_build_corpus, mock_fitness_events, mock_connect, mock_upsert,
    ):
        df = self._history_df(TARGET)
        mock_engineer.return_value = (df, pd.DataFrame())

        with patch.dict(
            os.environ,
            {"KICKBASE_EMAIL": "e", "KICKBASE_PASSWORD": "p", "FIRESTORE_ENABLED": "1"},
            clear=True,
        ):
            backfill_prediction_log(3)

        entries = mock_upsert.call_args[0][1]
        self.assertTrue(all(e["horizon_days"] == 1 for e in entries))


class BuildCandidatesTests(unittest.TestCase):
    def test_random_forest_matches_live_hyperparameters(self):
        candidates = _build_candidates()
        self.assertEqual(candidates["RandomForest"].n_estimators, 500)
        self.assertIn("HistGradientBoosting", candidates)

    def test_hist_gradient_boosting_matches_tuned_hyperparameters(self):
        # Aus der randomisierten 277-Konfigurationen-Suche (2026-07-31,
        # siehe _build_candidates()-Docstring) - 83.4% Richtungsgenauigkeit
        # / MAE 25147 statt 82.4% / 25370 mit sklearn-Standardwerten.
        hgb = _build_candidates()["HistGradientBoosting"]
        self.assertEqual(hgb.learning_rate, 0.05)
        self.assertEqual(hgb.max_iter, 200)
        self.assertEqual(hgb.max_leaf_nodes, 127)
        self.assertEqual(hgb.min_samples_leaf, 20)
        self.assertEqual(hgb.l2_regularization, 0.0)


def _performance_payload(minutes_by_matchday):
    return {
        "it": [
            {
                "ph": [
                    {"md": f"2026-0{i+1}-01T00:00:00Z", "p": 5, "mp": f"{mp}'", "t1": "1", "t2": "2", "t1g": 1, "t2g": 0}
                    for i, mp in enumerate(minutes_by_matchday)
                ]
            }
        ]
    }


class ParseMinutesTests(unittest.TestCase):
    def test_normal_value_strips_apostrophe_and_converts_to_int(self):
        self.assertEqual(_parse_minutes("45'"), 45)

    def test_malformed_string_falls_back_to_zero(self):
        # Der except-ValueError-Fallback - deckt kaputte "mp"-Strings von
        # der echten API ab (bisher ungetestet).
        self.assertEqual(_parse_minutes("garbage"), 0)

    def test_none_falls_back_to_zero(self):
        self.assertEqual(_parse_minutes(None), 0)


class PerformanceFrameMinutesAvgTests(unittest.TestCase):
    @patch("src.market_predictor.get_player_performance")
    def test_early_rows_average_over_available_matches_only(self, mock_perf):
        mock_perf.return_value = _performance_payload([90, 0, 45])
        df = _performance_frame("tok", "comp1", "p1")

        # min_periods=1: erste Zeile hat nur sich selbst, zweite nur die
        # ersten zwei - kein NaN trotz <3 verfuegbarer Vorgaenger-Spiele.
        self.assertEqual(df["mp_avg_3"].iloc[0], 90.0)
        self.assertEqual(df["mp_avg_3"].iloc[1], 45.0)

    @patch("src.market_predictor.get_player_performance")
    def test_fourth_row_averages_last_three_not_all_four(self, mock_perf):
        mock_perf.return_value = _performance_payload([90, 0, 45, 90])
        df = _performance_frame("tok", "comp1", "p1")

        # Fenster 3, nicht alle bisherigen Spiele - Zeile 4 mittelt ueber
        # Zeilen 2-4 (0, 45, 90), nicht ueber alle vier.
        self.assertAlmostEqual(df["mp_avg_3"].iloc[3], (0 + 45 + 90) / 3)

    @patch("src.market_predictor.get_player_performance")
    def test_empty_performance_history_has_no_rows(self, mock_perf):
        mock_perf.return_value = {"it": [{"ph": []}]}
        df = _performance_frame("tok", "comp1", "p1")
        self.assertTrue(df.empty)


class ChangeRecencyFeaturesTests(unittest.TestCase):
    def test_no_prior_event_returns_placeholder(self):
        result = _change_recency_features(
            [], datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], NO_HISTORY_DAYS_PLACEHOLDER)
        self.assertEqual(result["status_change_count_90d"], 0)

    def test_ignores_events_after_as_of_date(self):
        events = [{"date": "2026-08-01", "from_status_code": 0, "to_status_code": 1}]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], NO_HISTORY_DAYS_PLACEHOLDER)

    def test_one_event_returns_correct_days_since(self):
        events = [{"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1}]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 1)

    def test_multiple_events_only_within_window_counted(self):
        events = [
            {"date": "2026-01-01", "from_status_code": 0, "to_status_code": 1},
            {"date": "2026-07-01", "from_status_code": 1, "to_status_code": 0},
            {"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
        ]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31), "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 2)

    def test_event_exactly_90_days_before_is_excluded_boundary(self):
        as_of = datetime.date(2026, 7, 31)
        boundary_date = (as_of - datetime.timedelta(days=90)).isoformat()
        events = [{"date": boundary_date, "from_status_code": 0, "to_status_code": 1}]
        result = _change_recency_features(
            events, as_of, "days_since_last_status_change", "status_change_count_90d",
        )
        self.assertEqual(result["status_change_count_90d"], 0)
        self.assertEqual(result["days_since_last_status_change"], 90)

    def test_starting_rank_feature_names_produce_same_formula(self):
        """Regressionsschutz fuer die Generalisierung selbst (siehe
        docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md,
        Abschnitt Testing): identische Events/Datum wie
        test_one_event_returns_correct_days_since, aber mit den
        Startelf-Rang-Feature-Namen durchgereicht - beweist, dass die Formel
        unveraendert bleibt, unabhaengig vom Feld."""
        events = [{"date": "2026-07-20", "from_starting_rank": 3, "to_starting_rank": 1}]
        result = _change_recency_features(
            events, datetime.date(2026, 7, 31),
            "days_since_last_starting_rank_change", "starting_rank_change_count_90d",
        )
        self.assertEqual(result["days_since_last_starting_rank_change"], 11)
        self.assertEqual(result["starting_rank_change_count_90d"], 1)

    def test_starting_rank_feature_names_cold_start_placeholder(self):
        result = _change_recency_features(
            [], datetime.date(2026, 7, 31),
            "days_since_last_starting_rank_change", "starting_rank_change_count_90d",
        )
        self.assertEqual(result["days_since_last_starting_rank_change"], NO_HISTORY_DAYS_PLACEHOLDER)
        self.assertEqual(result["starting_rank_change_count_90d"], 0)


class SentimentFeaturesAsOfTests(unittest.TestCase):
    def test_no_articles_returns_neutral_placeholder(self):
        result = _sentiment_features_as_of([], datetime.date(2026, 8, 2))
        self.assertEqual(result["avg_sentiment_7d"], 0)
        self.assertEqual(result["news_volume_7d"], 0)

    def test_only_positive_articles_averages_to_one(self):
        articles = [
            {"pub_date": "2026-08-01", "sentiment_label": "positive"},
            {"pub_date": "2026-07-30", "sentiment_label": "positive"},
        ]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertEqual(result["avg_sentiment_7d"], 1)
        self.assertEqual(result["news_volume_7d"], 2)

    def test_mixed_sentiment_averages_correctly(self):
        articles = [
            {"pub_date": "2026-08-01", "sentiment_label": "positive"},
            {"pub_date": "2026-08-01", "sentiment_label": "negative"},
            {"pub_date": "2026-07-31", "sentiment_label": "neutral"},
        ]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertEqual(result["avg_sentiment_7d"], 0)
        self.assertEqual(result["news_volume_7d"], 3)

    def test_fractional_average_two_positive_one_negative(self):
        articles = [
            {"pub_date": "2026-08-01", "sentiment_label": "positive"},
            {"pub_date": "2026-08-01", "sentiment_label": "positive"},
            {"pub_date": "2026-08-01", "sentiment_label": "negative"},
        ]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertAlmostEqual(result["avg_sentiment_7d"], 1 / 3)
        self.assertEqual(result["news_volume_7d"], 3)

    def test_article_older_than_window_is_excluded(self):
        as_of = datetime.date(2026, 8, 2)
        too_old = (as_of - datetime.timedelta(days=8)).isoformat()
        articles = [{"pub_date": too_old, "sentiment_label": "positive"}]
        result = _sentiment_features_as_of(articles, as_of)
        self.assertEqual(result["news_volume_7d"], 0)
        self.assertEqual(result["avg_sentiment_7d"], 0)

    def test_article_exactly_on_window_boundary_is_excluded(self):
        as_of = datetime.date(2026, 8, 2)
        boundary_date = (as_of - datetime.timedelta(days=SENTIMENT_WINDOW_DAYS)).isoformat()
        articles = [{"pub_date": boundary_date, "sentiment_label": "positive"}]
        result = _sentiment_features_as_of(articles, as_of)
        self.assertEqual(result["news_volume_7d"], 0)

    def test_article_published_exactly_on_as_of_date_is_included(self):
        """Oberes Fensterende ist inklusiv ((as_of_date - 7, as_of_date]) -
        ein heute (am as_of_date selbst) veroeffentlichter Artikel zaehlt
        noch mit, wird NICHT wie Cold-Start behandelt. Regressionsschutz
        dagegen, dass die obere Grenze versehentlich exklusiv (< statt <=)
        wird."""
        as_of = datetime.date(2026, 8, 2)
        articles = [{"pub_date": as_of.isoformat(), "sentiment_label": "positive"}]
        result = _sentiment_features_as_of(articles, as_of)
        self.assertEqual(result["news_volume_7d"], 1)
        self.assertEqual(result["avg_sentiment_7d"], 1)

    def test_article_published_after_as_of_date_is_excluded_lookahead_guard(self):
        as_of = datetime.date(2026, 8, 2)
        future_date = (as_of + datetime.timedelta(days=1)).isoformat()
        articles = [{"pub_date": future_date, "sentiment_label": "negative"}]
        result = _sentiment_features_as_of(articles, as_of)
        self.assertEqual(result["news_volume_7d"], 0)
        self.assertEqual(result["avg_sentiment_7d"], 0)

    def test_unknown_sentiment_label_raises_key_error(self):
        articles = [{"pub_date": "2026-08-01", "sentiment_label": "surprised"}]
        with self.assertRaises(KeyError):
            _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))


class LoadChangeEventsByPlayerTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_entries_by_player_id(self, mock_connect, mock_get):
        mock_get.return_value = [
            {"player_id": "p1", "date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
            {"player_id": "p1", "date": "2026-07-25", "from_status_code": 1, "to_status_code": 0},
            {"player_id": "p2", "date": "2026-07-22", "from_status_code": 0, "to_status_code": 2},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_change_events_by_player("fitness_history_log")
        mock_get.assert_called_once_with(mock_connect.return_value, "fitness_history_log")
        self.assertEqual(len(result["p1"]), 2)
        self.assertEqual(len(result["p2"]), 1)

    def test_returns_empty_dict_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_load_change_events_by_player("fitness_history_log"), {})

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_returns_empty_dict_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            self.assertEqual(_load_change_events_by_player("fitness_history_log"), {})

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_starting_rank_entries_by_player_id(self, mock_connect, mock_get):
        """Regressionsschutz fuer die Generalisierung selbst: gleiche Logik
        wie test_groups_entries_by_player_id, aber mit collection=
        'starting_rank_history_log' - beweist collection ist ein echter
        Parameter, nicht hardcoded."""
        mock_get.return_value = [
            {"player_id": "p1", "date": "2026-07-20", "from_starting_rank": 3, "to_starting_rank": 1},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_change_events_by_player("starting_rank_history_log")
        mock_get.assert_called_once_with(mock_connect.return_value, "starting_rank_history_log")
        self.assertEqual(len(result["p1"]), 1)

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_news_entries_by_player_id(self, mock_connect, mock_get):
        """Regressionsschutz analog test_groups_starting_rank_entries_by_player_id,
        hier fuer 'player_news_log' (Phase B/C) - beweist collection bleibt
        ein echter Parameter auch fuer die dritte Nutzung dieser
        Generalisierung."""
        mock_get.return_value = [
            {"player_id": "p1", "pub_date": "2026-07-20", "sentiment_label": "positive"},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_change_events_by_player("player_news_log")
        mock_get.assert_called_once_with(mock_connect.return_value, "player_news_log")
        self.assertEqual(len(result["p1"]), 1)


class LoadNewsEventsByPlayerTests(unittest.TestCase):
    """_load_news_events_by_player() ist eine duenne, benannte Verdrahtung um
    _load_change_events_by_player('player_news_log') (siehe dortige
    LoadChangeEventsByPlayerTests fuer die eigentliche Gruppier-/Resilienz-Logik) -
    die Design-Spec (docs/superpowers/specs/2026-08-02-sentiment-ml-integration-design.md)
    sieht explizit einen eigenen, benannten Funktionsnamen vor, damit
    backfill_prediction_log()/predict_market_value_changes() lesbar bleiben
    (drei parallele Event-Quellen-Loads nebeneinander)."""

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_entries_by_player_id(self, mock_connect, mock_get):
        mock_get.return_value = [
            {"player_id": "p1", "pub_date": "2026-07-20", "sentiment_label": "positive"},
            {"player_id": "p1", "pub_date": "2026-07-25", "sentiment_label": "negative"},
            {"player_id": "p2", "pub_date": "2026-07-22", "sentiment_label": "neutral"},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_news_events_by_player()
        self.assertEqual(len(result["p1"]), 2)
        self.assertEqual(len(result["p2"]), 1)
        mock_get.assert_called_once_with(mock_connect.return_value, "player_news_log")

    def test_returns_empty_dict_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_load_news_events_by_player(), {})

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_returns_empty_dict_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            self.assertEqual(_load_news_events_by_player(), {})


class FetchPlayerTrainingFrameFitnessColumnsTests(unittest.TestCase):
    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_adds_fitness_columns_computed_as_of_each_row_date(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-07-31"]),
            "mv": [10_000_000, 10_200_000],
        })
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])
        fitness_events_by_player = {
            "p1": [{"player_id": "p1", "date": "2026-07-20", "from_status_code": 0, "to_status_code": 1}],
        }

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", fitness_events_by_player, {}, {})

        self.assertEqual(list(result["days_since_last_status_change"]), [5, 11])
        self.assertEqual(list(result["status_change_count_90d"]), [1, 1])

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_fitness_events_gets_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-07-31"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {}, {}, {})

        self.assertEqual(list(result["days_since_last_status_change"]), [NO_HISTORY_DAYS_PLACEHOLDER])


class FetchPlayerTrainingFrameStartingRankColumnsTests(unittest.TestCase):
    """Spiegelt FetchPlayerTrainingFrameFitnessColumnsTests 1:1 fuer
    starting_rank - beweist, dass die zweite Event-Quelle unabhaengig von
    der ersten funktioniert (leeres fitness_events_by_player daneben, kein
    Cross-Contamination zwischen den beiden Feature-Paaren)."""

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_adds_starting_rank_columns_computed_as_of_each_row_date(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-07-31"]),
            "mv": [10_000_000, 10_200_000],
        })
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])
        starting_rank_events_by_player = {
            "p1": [{"player_id": "p1", "date": "2026-07-20", "from_starting_rank": 3, "to_starting_rank": 1}],
        }

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", {}, starting_rank_events_by_player, {})

        self.assertEqual(list(result["days_since_last_starting_rank_change"]), [5, 11])
        self.assertEqual(list(result["starting_rank_change_count_90d"]), [1, 1])
        self.assertEqual(
            list(result["days_since_last_status_change"]), [NO_HISTORY_DAYS_PLACEHOLDER, NO_HISTORY_DAYS_PLACEHOLDER]
        )

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_starting_rank_events_gets_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-07-31"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {}, {}, {})

        self.assertEqual(list(result["days_since_last_starting_rank_change"]), [NO_HISTORY_DAYS_PLACEHOLDER])


class FetchPlayerTrainingFrameSentimentColumnsTests(unittest.TestCase):
    """Spiegelt FetchPlayerTrainingFrameStartingRankColumnsTests fuer die
    dritte Event-Quelle (player_news_log/Sentiment, Phase C) - beweist, dass
    sie unabhaengig von Fitness- UND Startelf-Rang-Events funktioniert (beide
    leer daneben, kein Cross-Contamination zwischen den drei Feature-Paaren)."""

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_adds_sentiment_columns_computed_as_of_each_row_date(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-08-01"]),
            "mv": [10_000_000, 10_200_000],
        })
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])
        news_events_by_player = {
            "p1": [{"player_id": "p1", "pub_date": "2026-07-24", "sentiment_label": "positive"}],
        }

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", {}, {}, news_events_by_player)

        self.assertEqual(list(result["avg_sentiment_7d"]), [1, 0])
        self.assertEqual(list(result["news_volume_7d"]), [1, 0])
        self.assertEqual(
            list(result["days_since_last_status_change"]), [NO_HISTORY_DAYS_PLACEHOLDER, NO_HISTORY_DAYS_PLACEHOLDER]
        )

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_news_events_gets_neutral_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-08-01"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {}, {}, {})

        self.assertEqual(list(result["avg_sentiment_7d"]), [0])
        self.assertEqual(list(result["news_volume_7d"]), [0])


class BuildCorpusStartingRankThreadingTests(unittest.TestCase):
    @patch("src.market_predictor._fetch_player_training_frame")
    @patch("src.market_predictor._fetch_competition_player_ids", return_value={"p1": "t1"})
    def test_starting_rank_events_by_player_passed_through_to_training_frame(
        self, mock_fetch_ids, mock_fetch_frame
    ):
        mock_fetch_frame.return_value = pd.DataFrame({"player_id": ["p1"], "mv": [1_000_000]})
        fitness_events = {"p1": [{"date": "2026-07-20"}]}
        starting_rank_events = {"p1": [{"date": "2026-07-25"}]}

        _build_corpus("tok", "l1", "c1", fitness_events, starting_rank_events, {})

        mock_fetch_frame.assert_called_once_with(
            "tok", "l1", "c1", "p1", "t1", fitness_events, starting_rank_events, {}
        )


class BuildCorpusNewsEventsThreadingTests(unittest.TestCase):
    """Spiegelt BuildCorpusStartingRankThreadingTests fuer news_events_by_player
    (dritter, letzter Event-Quellen-Parameter, Phase C)."""

    @patch("src.market_predictor._fetch_player_training_frame")
    @patch("src.market_predictor._fetch_competition_player_ids", return_value={"p1": "t1"})
    def test_news_events_by_player_passed_through_to_training_frame(
        self, mock_fetch_ids, mock_fetch_frame
    ):
        mock_fetch_frame.return_value = pd.DataFrame({"player_id": ["p1"], "mv": [1_000_000]})
        fitness_events = {"p1": [{"date": "2026-07-20"}]}
        starting_rank_events = {"p1": [{"date": "2026-07-25"}]}
        news_events = {"p1": [{"pub_date": "2026-07-24", "sentiment_label": "positive"}]}

        _build_corpus("tok", "l1", "c1", fitness_events, starting_rank_events, news_events)

        mock_fetch_frame.assert_called_once_with(
            "tok", "l1", "c1", "p1", "t1", fitness_events, starting_rank_events, news_events
        )


class EngineerFeatures3dTargetTests(unittest.TestCase):
    def test_mv_target_3d_uses_shift_of_three_not_one(self):
        # 5 Tage, taeglich +1000 Marktwert-Aenderung fuer denselben Spieler.
        rows = [
            {"player_id": "p1", "team_id": "t1", "date": pd.Timestamp(f"2026-07-{20+i:02d}"),
             "mv": 10_000_000 + i * 1000, "md": pd.Timestamp(f"2026-07-{20+i:02d}"), "p": 5, "mp": 90, "mp_avg_3": 90,
             "t1": "t1", "t2": "t2", "t1g": 1, "t2g": 0,
             "days_since_last_status_change": 9999, "status_change_count_90d": 0}
            for i in range(5)
        ]
        df = pd.DataFrame(rows)
        history_df, _ = _engineer_features(df)
        # Zeile fuer 2026-07-21 (i=1): mv_target (1 Tag) = 1000, mv_target_3d (3 Tage) = 3000.
        row0 = history_df[history_df["date"] == pd.Timestamp("2026-07-21")].iloc[0]
        self.assertEqual(row0["mv_target"], 1000)
        self.assertEqual(row0["mv_target_3d"], 3000)

    def test_rows_with_nan_3d_target_are_not_dropped_from_history_df(self):
        # Gleiche 5-Tage-Fixture wie oben. history_df enthaelt die Zeilen
        # i=1,2,3 (i=0 faellt durch mv_change_1d==NaN raus, i=4 wird zu
        # today_df) - i=2 und i=3 haben aber KEINEN gueltigen 3-Tage-Wert
        # mehr (braeuchten Zeilen i=5/i=6, die es in dieser 5-Tage-Fixture
        # nicht gibt). Wenn ein kuenftiger Edit mv_target_3d_clipped
        # versehentlich zum gemeinsamen dropna()-Filter hinzufuegt, wuerden
        # genau diese Zeilen aus history_df verschwinden UND die
        # 1-Tages-Trainingsbasis unnoetig verkleinern - dieser Test faengt
        # das.
        rows = [
            {"player_id": "p1", "team_id": "t1", "date": pd.Timestamp(f"2026-07-{20+i:02d}"),
             "mv": 10_000_000 + i * 1000, "md": pd.Timestamp(f"2026-07-{20+i:02d}"), "p": 5, "mp": 90, "mp_avg_3": 90,
             "t1": "t1", "t2": "t2", "t1g": 1, "t2g": 0,
             "days_since_last_status_change": 9999, "status_change_count_90d": 0}
            for i in range(5)
        ]
        df = pd.DataFrame(rows)
        history_df, _ = _engineer_features(df)
        self.assertEqual(len(history_df), 3)
        self.assertTrue(history_df["mv_target_3d"].isna().any())


class TrainAndEvaluateTargetColTests(unittest.TestCase):
    def _history_df(self, target_col):
        import numpy as np
        n = 250
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rng = np.random.RandomState(42)
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            "avg_sentiment_7d": 0, "news_volume_7d": 0,
            "mv_target_clipped": rng.randn(n) * 5000,
            "alt_target_clipped": rng.randn(n) * 9000,
        })
        return df

    def test_default_target_col_is_backward_compatible(self):
        df = self._history_df("mv_target_clipped")
        result = _train_and_evaluate(df)
        self.assertIsNotNone(result)

    def test_custom_target_col_is_used_for_training(self):
        df = self._history_df("alt_target_clipped")
        result = _train_and_evaluate(df, target_col="alt_target_clipped")
        self.assertIsNotNone(result)
        models, metrics = result
        self.assertIn("model_type", metrics)

    def test_rows_with_nan_target_col_are_dropped_not_fatal(self):
        df = self._history_df("mv_target_clipped")
        df.loc[df.index[:5], "alt_target_clipped"] = None
        result = _train_and_evaluate(df, target_col="alt_target_clipped")
        self.assertIsNotNone(result)


class WalkForwardBacktestTargetColTests(unittest.TestCase):
    def _history_df(self, target_col, n=210):
        import numpy as np
        unclipped_col = target_col.removesuffix("_clipped")
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        rng = np.random.RandomState(7)
        df = pd.DataFrame({
            "date": dates, "player_id": ["p1"] * n,
            "p": rng.rand(n), "mv": rng.rand(n) * 1_000_000,
            "days_to_next": rng.randint(1, 8, n),
            "mv_change_1d": rng.randn(n) * 1000, "mv_trend_1d": rng.randn(n) * 0.01,
            "mv_change_3d": rng.randn(n) * 2000, "mv_vol_3d": rng.rand(n) * 500,
            "mv_trend_7d": rng.randn(n) * 0.02, "market_divergence": rng.rand(n) + 0.5,
            "days_since_last_status_change": 9999, "status_change_count_90d": 0,
            "days_since_last_starting_rank_change": 9999, "starting_rank_change_count_90d": 0,
            "avg_sentiment_7d": 0, "news_volume_7d": 0,
            target_col: rng.randn(n) * 5000,
            unclipped_col: rng.randn(n) * 5000,
        })
        return df

    def test_partial_nan_test_rows_are_dropped_not_averaged_into_nan(self):
        # Regression fuer Finding 1: eine einzelne Zeile mit NaN in der
        # ungeklippten Zielspalte lag frueher NEBEN echten Werten im
        # selben Fold (test.isna().all() war False, also kein Skip) und
        # sickerte unverworfen in sign_hits/abs_errors - da abs_errors
        # ueber ALLE Folds aufsummiert wird, kippte eine einzige solche
        # Zeile den finalen mae fuer BEIDE Modelle auf NaN.
        target_col = "alt_target_clipped"
        unclipped_col = "alt_target"
        df = self._history_df(target_col)
        # Zweite Zeile am selben (letzten) Cutoff-Tag wie p1, aber ohne
        # bekannten tatsaechlichen Ausgang (z.B. ein 3-Tage-Ziel, dessen
        # Fenster ueber das Ende der Historie hinauslaeuft).
        extra_row = df.iloc[[-1]].copy()
        extra_row["player_id"] = "p2"
        extra_row[unclipped_col] = None
        df = pd.concat([df, extra_row], ignore_index=True)

        result = _walk_forward_backtest(df, target_col=target_col)

        self.assertIsNotNone(result)
        self.assertEqual(result["n_folds"], 6)
        for name, model_metrics in result["per_model"].items():
            self.assertTrue(
                math.isfinite(model_metrics["mae"]),
                f"{name}: mae ist nicht finit ({model_metrics['mae']!r}) - die NaN-Zeile ist eingesickert.",
            )
            # p2s NaN-Zeile darf im letzten Fold nicht mitgezaehlt werden -
            # sonst waeren es 7 (6 Folds x 1 Testzeile + 1 zusaetzliche).
            self.assertEqual(model_metrics["n"], 6)

    def test_custom_target_col_is_honored(self):
        target_col = "alt_target_clipped"
        df = self._history_df(target_col)

        result = _walk_forward_backtest(df, target_col=target_col)

        self.assertIsNotNone(result)
        self.assertIn("n_folds", result)
        self.assertIn("per_model", result)
        self.assertTrue(result["per_model"])
        for model_metrics in result["per_model"].values():
            self.assertIn("mae", model_metrics)
            self.assertIn("sign_accuracy", model_metrics)
            self.assertIn("n", model_metrics)


class TrainAndTrackHorizonTests(unittest.TestCase):
    def test_returns_none_when_too_few_training_rows(self):
        df = pd.DataFrame({"date": pd.to_datetime(["2026-07-01"]), "player_id": ["p1"], "mv_target_clipped": [100]})
        result = _train_and_track_horizon(df, df, TARGET, 1, "2026-07-31", {})
        self.assertIsNone(result)


class PredictMarketValueChangesThreeDayIsolationTests(unittest.TestCase):
    """Reviewer-Finding (Task 5, kritisch): eine unerwartete Exception im
    3-Tage-Aufruf von _train_and_track_horizon() darf NICHT bis zum
    aeusseren try/except von predict_market_value_changes() durchschlagen -
    das wuerde das bereits berechnete result_1d verwerfen und die GESAMTE
    Funktion mit None statt Ergebnis abschliessen lassen (kein Snapshot,
    kein 1-Tages-Signal), obwohl nur der neue 3-Tage-Pfad kaputt ist. Vorher
    war nur der DESIGNTE None-Rueckgabefall (zu wenig Trainingsdaten)
    getestet (siehe TrainAndTrackHorizonTests) - eine echte Exception
    (z.B. ein sklearn/pandas-Edge-Case) war ungetestet."""

    def _today_df(self):
        return pd.DataFrame({
            "player_id": ["p1"],
            "date": [pd.Timestamp("2026-07-31")],
            "mv": [1_000_000],
            "p": [5],
            "days_to_next": [3],
            "mv_change_1d": [100],
            "mv_trend_1d": [0.01],
            "mv_change_3d": [200],
            "mv_vol_3d": [50],
            "mv_trend_7d": [0.02],
            "market_divergence": [1.0],
            "days_since_last_status_change": [10],
            "status_change_count_90d": [0],
            "days_since_last_starting_rank_change": [10],
            "starting_rank_change_count_90d": [0],
            "avg_sentiment_7d": [0],
            "news_volume_7d": [0],
        })

    def test_exception_in_3d_call_does_not_discard_1d_result(self):
        result_1d = {"predictions": {"p1": 12_345}, "metrics": {"model_type": "HistGradientBoosting"}}
        history_df = pd.DataFrame({"days_to_next": [1, 2, 3]})
        today_df = self._today_df()

        with patch.dict(
            os.environ, {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x"}, clear=True,
        ), patch("src.market_predictor.login", return_value=("tok", {"id": "u1"}, [{"id": "l1"}])
        ), patch("src.market_predictor.get_me", return_value={"cpi": "1"}
        ), patch("src.market_predictor._load_change_events_by_player", return_value={}
        ), patch("src.market_predictor._build_corpus", return_value=pd.DataFrame()
        ), patch("src.market_predictor._engineer_features", return_value=(history_df, today_df)
        ), patch("src.market_predictor._infer_today", return_value="2026-07-31"
        ), patch("src.market_predictor._build_mv_lookup", return_value={}
        ), patch(
            "src.market_predictor._train_and_track_horizon",
            side_effect=[result_1d, RuntimeError("boom")],
        ) as mock_horizon:
            result = predict_market_value_changes()

        self.assertEqual(mock_horizon.call_count, 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["predictions"], {"p1": 12_345})
        self.assertEqual(result["metrics"], {"model_type": "HistGradientBoosting"})
        self.assertIsNone(result["predictions_3d"])
        self.assertIsNone(result["metrics_3d"])


class FeaturesListStartingRankTests(unittest.TestCase):
    def test_features_includes_starting_rank_recency_columns(self):
        self.assertIn("days_since_last_starting_rank_change", FEATURES)
        self.assertIn("starting_rank_change_count_90d", FEATURES)


class FeaturesListSentimentTests(unittest.TestCase):
    def test_features_includes_sentiment_columns(self):
        self.assertIn("avg_sentiment_7d", FEATURES)


class ClipTargetTests(unittest.TestCase):
    def test_clips_using_only_given_series_quantiles(self):
        # Werte 0..99 plus ein Ausreisser 100000 - IQR-Clip muss den
        # Ausreisser kappen, den Rest unveraendert lassen.
        from src.market_predictor import _clip_target
        values = pd.Series(list(range(100)) + [100000])
        clipped = _clip_target(values)
        self.assertLess(clipped.iloc[-1], 100000)
        self.assertEqual(clipped.iloc[0], 0)
        self.assertEqual(clipped.iloc[50], 50)


class ApplyEmbargoTests(unittest.TestCase):
    def _train(self):
        return pd.DataFrame({
            "date": pd.to_datetime([
                "2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05",
            ]),
        })

    def test_horizon_1_is_noop(self):
        from src.market_predictor import _apply_embargo
        train = self._train()
        result = _apply_embargo(train, pd.Timestamp("2026-08-06"), horizon_days=1)
        self.assertEqual(len(result), 5)

    def test_horizon_3_excludes_last_two_days_before_cutoff(self):
        from src.market_predictor import _apply_embargo
        # cutoff=08-06, horizon=3: Zeilen mit Label ueber den Cutoff hinaus
        # sind 08-04 (Label -> 08-07) und 08-05 (Label -> 08-08) - genau
        # horizon_days-1=2 Tage, NICHT horizon_days=3 Tage (08-03 hat ein
        # Label das genau am Cutoff endet, 08-03+3=08-06 - das ist noch
        # KEIN Blick in die Zukunft DES Cutoffs, bleibt also drin).
        train = self._train()
        result = _apply_embargo(train, pd.Timestamp("2026-08-06"), horizon_days=3)
        self.assertEqual(
            list(result["date"].dt.date.astype(str)),
            ["2026-08-01", "2026-08-02", "2026-08-03"],
        )


class ScoreCountsFromArraysTests(unittest.TestCase):
    def test_counts_match_hand_computation(self):
        from src.market_predictor import _score_counts_from_arrays
        y_actual = [100, -50, 30, -10]
        y_pred = [80, -60, -5, -20]  # Zeile 3 (30 vs -5) hat falsches Vorzeichen
        baseline_pred = [90, 40, 30, -5]  # Zeile 2 (-50 vs 40) hat falsches Vorzeichen
        counts = _score_counts_from_arrays(y_actual, y_pred, baseline_pred)
        self.assertEqual(counts["n"], 4)
        self.assertEqual(counts["sign_correct"], 3)  # alle bis auf Zeile 3
        self.assertEqual(counts["n_baseline"], 4)
        self.assertEqual(counts["baseline_sign_correct"], 3)  # alle bis auf Zeile 2
        self.assertEqual(counts["n_baseline_wrong"], 1)
        # Zeile 2: Modell richtig (-50 vs -60, beide negativ), Baseline falsch
        self.assertEqual(counts["model_sign_correct_when_baseline_wrong"], 1)
        self.assertAlmostEqual(counts["abs_error_sum"], 20 + 10 + 35 + 10, places=5)
        # abs_error_sum_given_correct_sign: Zeilen 1,2,4 (Zeile 3 hat falsches Vorzeichen)
        self.assertAlmostEqual(counts["abs_error_sum_given_correct_sign"], 20 + 10 + 10, places=5)


class FinalizeScoreCountsTests(unittest.TestCase):
    def test_derives_rounded_percentages(self):
        from src.market_predictor import _finalize_score_counts
        counts = {
            "n": 4, "sign_correct": 3, "abs_error_sum": 75.0,
            "abs_error_sum_given_correct_sign": 40.0,
            "n_baseline": 4, "baseline_sign_correct": 3, "baseline_abs_error_sum": 90.0,
            "n_baseline_wrong": 1, "model_sign_correct_when_baseline_wrong": 1,
        }
        result = _finalize_score_counts(counts)
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["sign_accuracy"], 75.0)
        self.assertAlmostEqual(result["mae"], 18.75, places=2)
        self.assertAlmostEqual(result["mae_given_correct_sign"], 40.0 / 3, places=2)
        self.assertEqual(result["baseline_sign_accuracy"], 75.0)
        self.assertAlmostEqual(result["baseline_mae"], 22.5, places=2)
        self.assertEqual(result["reversal_sign_accuracy"], 100.0)
        self.assertEqual(result["reversal_n"], 1)

    def test_returns_none_when_n_zero(self):
        from src.market_predictor import _finalize_score_counts, _empty_counts
        self.assertIsNone(_finalize_score_counts(_empty_counts()))

    def test_reversal_and_correct_sign_fields_are_none_when_denominator_zero(self):
        from src.market_predictor import _finalize_score_counts, _empty_counts
        counts = _empty_counts()
        counts["n"] = 2
        counts["sign_correct"] = 0
        counts["abs_error_sum"] = 10.0
        counts["n_baseline"] = 0
        result = _finalize_score_counts(counts)
        self.assertIsNone(result["mae_given_correct_sign"])
        self.assertIsNone(result["baseline_sign_accuracy"])
        self.assertIsNone(result["baseline_mae"])
        self.assertIsNone(result["reversal_sign_accuracy"])
        self.assertEqual(result["reversal_n"], 0)


class EngineerFeaturesUnclippedTargetTests(unittest.TestCase):
    def test_mv_target_columns_are_not_clipped(self):
        # Ein Ausreisser-Sprung darf NICHT mehr geklippt werden - Clipping
        # passiert jetzt erst beim Training, pro Split/Fold.
        rows = []
        pid, tid = "p1", "t1"
        for i, mv in enumerate([1_000_000, 1_000_000, 1_000_000, 50_000_000]):
            rows.append({
                "player_id": pid, "team_id": tid, "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "mv": mv, "md": pd.NaT, "p": None, "mp": None, "mp_avg_3": None,
                "t1": tid, "t2": None, "t1g": None, "t2g": None,
            })
        df = pd.DataFrame(rows)
        history_df, _today_df = _engineer_features(df)
        self.assertIn("mv_target", history_df.columns)
        self.assertNotIn("mv_target_clipped", history_df.columns)
        self.assertNotIn("mv_target_3d_clipped", history_df.columns)
        self.assertIn("news_volume_7d", FEATURES)
