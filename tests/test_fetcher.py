import unittest
from unittest.mock import patch

from src.fetcher import _apply_or_reuse_market_value_history


class ApplyOrReuseMarketValueHistoryTests(unittest.TestCase):
    @patch("src.fetcher._apply_market_value_history")
    def test_reuses_cached_fields_without_api_call(self, mock_apply):
        row = {"player_id": "p1", "market_value_change_7d": None}
        cache = {"p1": {
            "market_value_change_7d": 50_000, "market_value_low_92d": 900_000,
            "market_value_high_92d": 1_100_000, "market_value_in_drop_phase": 0,
        }}

        _apply_or_reuse_market_value_history("tok", "l1", row, cache)

        mock_apply.assert_not_called()
        self.assertEqual(row["market_value_change_7d"], 50_000)
        self.assertEqual(row["market_value_low_92d"], 900_000)

    @patch("src.fetcher._apply_market_value_history")
    def test_calls_api_when_not_cached(self, mock_apply):
        row = {"player_id": "p2", "market_value_change_7d": None}

        _apply_or_reuse_market_value_history("tok", "l1", row, {})

        mock_apply.assert_called_once_with("tok", "l1", row)
