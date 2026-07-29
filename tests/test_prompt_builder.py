import unittest

from src.prompt_builder import _cost_per_point, _market_line, _player_line


class CostPerPointTests(unittest.TestCase):
    def test_divides_value_by_second_argument(self):
        self.assertEqual(_cost_per_point(10_000_000, 100), "100000")

    def test_none_value_is_unbekannt(self):
        self.assertEqual(_cost_per_point(None, 100), "unbekannt")

    def test_zero_second_argument_is_unbekannt(self):
        self.assertEqual(_cost_per_point(10_000_000, 0), "unbekannt")

    def test_none_second_argument_is_unbekannt(self):
        self.assertEqual(_cost_per_point(10_000_000, None), "unbekannt")


def _base_row(**overrides):
    row = {
        "name": "Krauß", "position": "Mittelfeld", "team_name": "Bremen",
        "status_label": None, "player_id": "p1",
        "market_value": 10_000_000, "average_points": 100, "total_points": 1_000,
        "market_value_change_7d": None, "market_value_low_92d": None, "market_value_high_92d": None,
        "price": 11_000_000, "price_delta_pct": None,
        "is_system_offer": True, "offering_username": None, "offering_user_id": None,
        "pending_offers_count": 0, "is_own_leading_bid": False, "leading_bid_username": None,
        "leading_bid_price": None,
    }
    row.update(overrides)
    return row


class PlayerLineCostPerPointTests(unittest.TestCase):
    def test_uses_average_points_not_total_points(self):
        # average_points=100 -> 10_000_000/100 = 100_000. Mit dem Bug
        # (Division durch total_points=1000) kaeme 10_000 heraus - ein
        # komplett anderer, falscher Wert.
        row = _base_row(average_points=100, total_points=1_000)

        line = _player_line(row, current_matchday=10)

        self.assertIn("Kosten/Punkt: 100000 |", line)


class MarketLineCostPerPointTests(unittest.TestCase):
    def test_uses_average_points_not_total_points(self):
        row = _base_row(price=12_000_000, average_points=120, total_points=2_400)

        line = _market_line(row, current_matchday=10)

        self.assertIn("Kosten/Punkt: 100000", line)
        self.assertNotIn("Kosten/Punkt: 5000", line)


if __name__ == "__main__":
    unittest.main()
