import datetime
import unittest
from unittest.mock import patch

from src.fetcher import (
    _apply_market_value_history,
    _apply_or_reuse_market_value_history,
    _compute_expiry,
    _market_item_to_row,
    _squad_item_to_row,
)


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


class MarketItemToRowOwnerTests(unittest.TestCase):
    """Regressionsschutz fuer den dokumentierten echten Live-Crash
    ("unhashable type: dict"): ein fruehes Ad-hoc-Skript nahm an, 'u' sei
    immer eine flache Id/String, tatsaechlich steckt der Anbieter bei
    Mitspieler-Angeboten als VERSCHACHTELTES Objekt {"i": ..., "n": ...}
    drin."""

    def test_owner_as_dict_resolves_id_and_name_from_nested_object(self):
        item = {"i": "p1", "n": "Foo", "pos": 3, "mv": 1_000_000, "tid": "t1", "u": {"i": "u1", "n": "Rivale"}}
        row = _market_item_to_row(item, {}, {"t1": "Bremen"})
        self.assertEqual(row["offering_user_id"], "u1")
        self.assertEqual(row["offering_username"], "Rivale")
        self.assertEqual(row["is_system_offer"], 0)

    def test_owner_as_string_falls_back_to_names_by_user_id_lookup(self):
        item = {"i": "p2", "n": "Bar", "pos": 1, "mv": 500_000, "u": "u2"}
        row = _market_item_to_row(item, {"u2": "Zweiter"}, {})
        self.assertEqual(row["offering_user_id"], "u2")
        self.assertEqual(row["offering_username"], "Zweiter")
        self.assertEqual(row["is_system_offer"], 0)

    def test_no_owner_field_is_a_system_offer(self):
        item = {"i": "p3", "n": "Baz", "pos": 2, "mv": 300_000}
        row = _market_item_to_row(item, {}, {})
        self.assertIsNone(row["offering_user_id"])
        self.assertIsNone(row["offering_username"])
        self.assertEqual(row["is_system_offer"], 1)


class MarketItemToRowPriceDeltaPctTests(unittest.TestCase):
    def test_computes_pct_change_between_price_and_market_value(self):
        item = {"i": "p4", "n": "Qux", "pos": 4, "mv": 1_000_000, "prc": 1_050_000}
        row = _market_item_to_row(item, {}, {})
        self.assertEqual(row["price_delta_pct"], 5.0)


class MarketItemToRowLeadingBidTests(unittest.TestCase):
    def test_matches_leading_bid_username_from_offers_list(self):
        item = {
            "i": "p5", "n": "Quux", "pos": 3, "mv": 1_000_000,
            "uoid": "u9", "uop": 1_200_000,
            "ofs": [{"u": "u9", "unm": "Fuehrender"}, {"u": "u8", "unm": "Andere"}],
        }
        row = _market_item_to_row(item, {}, {})
        self.assertEqual(row["leading_bid_username"], "Fuehrender")
        self.assertEqual(row["leading_bid_price"], 1_200_000)


class ApplyMarketValueHistoryTests(unittest.TestCase):
    """Direkt gegen die echte Funktion getestet (nicht durch den
    _apply_or_reuse_market_value_history-Wrapper, der sie in den anderen
    Tests bereits wegmockt) - deckt den len(entries)>=8-Grenzfall ab."""

    @patch("src.fetcher.get_market_value_history")
    def test_seven_entries_stays_below_threshold_change_7d_remains_none(self, mock_history):
        mock_history.return_value = {
            "it": [{"mv": 1_000_000 + i * 10_000} for i in range(7)],
            "lmv": 900_000, "hmv": 1_100_000, "idp": False,
        }
        row = {"player_id": "p1", "name": "Foo", "market_value_change_7d": None}

        _apply_market_value_history("tok", "l1", row)

        self.assertIsNone(row["market_value_change_7d"])
        self.assertEqual(row["market_value_low_92d"], 900_000)
        self.assertEqual(row["market_value_high_92d"], 1_100_000)
        self.assertEqual(row["market_value_in_drop_phase"], 0)

    @patch("src.fetcher.get_market_value_history")
    def test_eight_entries_computes_change_7d_from_first_and_last(self, mock_history):
        mock_history.return_value = {
            "it": [
                {"mv": v}
                for v in [1_000_000, 1_010_000, 1_020_000, 1_030_000, 1_040_000, 1_050_000, 1_060_000, 1_070_000]
            ],
            "lmv": 950_000, "hmv": 1_100_000, "idp": True,
        }
        row = {"player_id": "p2", "name": "Bar", "market_value_change_7d": None}

        _apply_market_value_history("tok", "l1", row)

        self.assertEqual(row["market_value_change_7d"], 70_000)
        self.assertEqual(row["market_value_in_drop_phase"], 1)
