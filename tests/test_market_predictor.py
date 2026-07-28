import os
import unittest
from unittest.mock import MagicMock, patch

from src.market_predictor import _load_prediction_log


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
