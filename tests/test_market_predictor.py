import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.market_predictor import (
    _summarize_from_daily,
    _build_daily_accuracy_updates,
    _realized_by_model_from_daily,
    _trend_from_daily,
    _load_local_prediction_log,
    _load_recent_prediction_log,
    _select_live_model,
    _infer_today,
    _performance_frame,
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
            _load_recent_prediction_log("2026-07-28")
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
                result = _load_recent_prediction_log("2026-07-28")
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
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-29")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["n"], 2)
        self.assertEqual(result[0]["sign_correct"], 1)  # p1 richtig (positiv+positiv), p2 falsch (negativ vorhergesagt, tatsaechlich positiv)

    def test_skips_entries_without_model_type(self):
        entries = [{"date": "2026-07-01", "player_id": "p1", "predicted_delta": 100}]
        result = _build_daily_accuracy_updates(entries, {}, "2026-07-28")
        self.assertEqual(result, [])


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
