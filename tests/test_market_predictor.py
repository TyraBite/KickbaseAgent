import datetime
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    _performance_frame,
    _fitness_features_as_of,
    _fetch_player_training_frame,
    _load_fitness_events_by_player,
    _engineer_features,
    FITNESS_NO_HISTORY_DAYS,
    _train_and_evaluate,
    _walk_forward_backtest,
    _train_and_track_horizon,
    predict_market_value_changes,
    TARGET,
    TARGET_3D,
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


class FitnessFeaturesAsOfTests(unittest.TestCase):
    def test_no_prior_event_returns_placeholder(self):
        result = _fitness_features_as_of([], datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], FITNESS_NO_HISTORY_DAYS)
        self.assertEqual(result["status_change_count_90d"], 0)

    def test_ignores_events_after_as_of_date(self):
        events = [{"date": "2026-08-01", "from_status_code": 0, "to_status_code": 1}]
        result = _fitness_features_as_of(events, datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], FITNESS_NO_HISTORY_DAYS)

    def test_one_event_returns_correct_days_since(self):
        events = [{"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1}]
        result = _fitness_features_as_of(events, datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 1)

    def test_multiple_events_only_within_window_counted(self):
        events = [
            {"date": "2026-01-01", "from_status_code": 0, "to_status_code": 1},
            {"date": "2026-07-01", "from_status_code": 1, "to_status_code": 0},
            {"date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
        ]
        result = _fitness_features_as_of(events, datetime.date(2026, 7, 31))
        self.assertEqual(result["days_since_last_status_change"], 11)
        self.assertEqual(result["status_change_count_90d"], 2)

    def test_event_exactly_90_days_before_is_excluded_boundary(self):
        as_of = datetime.date(2026, 7, 31)
        boundary_date = (as_of - datetime.timedelta(days=90)).isoformat()
        events = [{"date": boundary_date, "from_status_code": 0, "to_status_code": 1}]
        result = _fitness_features_as_of(events, as_of)
        self.assertEqual(result["status_change_count_90d"], 0)
        self.assertEqual(result["days_since_last_status_change"], 90)


class LoadFitnessEventsByPlayerTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_fitness_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_entries_by_player_id(self, mock_connect, mock_get):
        mock_get.return_value = [
            {"player_id": "p1", "date": "2026-07-20", "from_status_code": 0, "to_status_code": 1},
            {"player_id": "p1", "date": "2026-07-25", "from_status_code": 1, "to_status_code": 0},
            {"player_id": "p2", "date": "2026-07-22", "from_status_code": 0, "to_status_code": 2},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_fitness_events_by_player()
        self.assertEqual(len(result["p1"]), 2)
        self.assertEqual(len(result["p2"]), 1)

    def test_returns_empty_dict_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_load_fitness_events_by_player(), {})

    @patch("src.market_predictor.firestore_db.get_fitness_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_returns_empty_dict_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            self.assertEqual(_load_fitness_events_by_player(), {})


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

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", fitness_events_by_player)

        self.assertEqual(list(result["days_since_last_status_change"]), [5, 11])
        self.assertEqual(list(result["status_change_count_90d"]), [1, 1])

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_fitness_events_gets_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-07-31"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {})

        self.assertEqual(list(result["days_since_last_status_change"]), [FITNESS_NO_HISTORY_DAYS])


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
        })

    def test_exception_in_3d_call_does_not_discard_1d_result(self):
        result_1d = {"predictions": {"p1": 12_345}, "metrics": {"model_type": "HistGradientBoosting"}}
        history_df = pd.DataFrame({"days_to_next": [1, 2, 3]})
        today_df = self._today_df()

        with patch.dict(
            os.environ, {"KICKBASE_EMAIL": "a@b.c", "KICKBASE_PASSWORD": "x"}, clear=True,
        ), patch("src.market_predictor.login", return_value=("tok", {"id": "u1"}, [{"id": "l1"}])
        ), patch("src.market_predictor.get_me", return_value={"cpi": "1"}
        ), patch("src.market_predictor._load_fitness_events_by_player", return_value={}
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
