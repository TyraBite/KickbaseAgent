import os
import unittest
from unittest.mock import MagicMock, patch

from src.market_predictor import _load_prediction_log
from src.market_predictor import _select_live_model, _evaluate_realized_accuracy_by_model


class LoadPredictionLogTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_reads_from_firestore_when_enabled(self, mock_connect, mock_get):
        mock_get.return_value = [{"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_prediction_log()
        self.assertEqual(result, mock_get.return_value)

    @patch("src.market_predictor.firestore_db.get_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_falls_back_to_local_file_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_prediction_log()
        self.assertIsInstance(result, list)


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


class EvaluateRealizedAccuracyByModelTests(unittest.TestCase):
    def test_skips_entries_without_model_type(self):
        log_entries = [{"date": "2026-07-01", "player_id": "p1", "predicted_delta": 100}]  # altes Schema
        result = _evaluate_realized_accuracy_by_model(log_entries, {}, "2026-07-28")
        self.assertIsNone(result["RandomForest"]["realized_7d"])
        self.assertIsNone(result["HistGradientBoosting"]["realized_7d"])

    def test_separates_by_model_type(self):
        log_entries = [
            {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100},
            {"date": "2026-07-27", "player_id": "p1", "model_type": "HistGradientBoosting", "predicted_delta": -100},
        ]
        mv_lookup = {("p1", "2026-07-27"): 1000.0, ("p1", "2026-07-28"): 1200.0}
        result = _evaluate_realized_accuracy_by_model(log_entries, mv_lookup, "2026-07-29")
        self.assertGreater(
            result["RandomForest"]["realized_7d"]["sign_accuracy"],
            result["HistGradientBoosting"]["realized_7d"]["sign_accuracy"],
        )
