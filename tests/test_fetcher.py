import datetime
import unittest
from unittest.mock import patch

from src.fetcher import _apply_or_reuse_market_value_history, _compute_expiry, _squad_item_to_row


class ComputeExpiryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 7, 30, 10, 0, 0, tzinfo=datetime.timezone.utc)

    def test_exact_exs_seconds_used_when_present(self):
        expires_at, is_estimate = _compute_expiry(175, self.now)
        self.assertEqual(expires_at, "2026-07-30T10:02:55Z")
        self.assertFalse(is_estimate)

    def test_no_exs_seconds_returns_unknown_not_a_guess(self):
        # Live-Fund 2026-07-30: die alte mpst-Tage-Schaetzung markierte echte,
        # weiterhin aktive Mitspieler-Angebote faelschlich als "abgelaufen"
        # (ein Angebot, gelistet vor 5 Tagen, war live ueber die Kickbase-API
        # noch abrufbar, obwohl die Schaetzung "gelistet + 3 Tage" es laengst
        # als abgelaufen auswies). Mitspieler-Angebote liefern nie ein 'exs' -
        # ohne dieses Feld ist keine verlaessliche Restzeit ableitbar.
        expires_at, is_estimate = _compute_expiry(None, self.now)
        self.assertIsNone(expires_at)
        self.assertFalse(is_estimate)


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


class SquadItemToRowPurchasePriceTests(unittest.TestCase):
    def test_computes_purchase_price_from_market_value_minus_gain_loss(self):
        row = _squad_item_to_row({"i": "p1", "n": "Test", "pos": 3, "mv": 26_263_884, "mvgl": 322_616}, {})
        self.assertEqual(row["purchase_price"], 25_941_268)

    def test_purchase_price_none_when_mvgl_missing(self):
        row = _squad_item_to_row({"i": "p1", "n": "Test", "pos": 3, "mv": 1_000_000}, {})
        self.assertIsNone(row["purchase_price"])
