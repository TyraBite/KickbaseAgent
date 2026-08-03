import unittest
from src.player_valuation import fairwert, fetch_all_players, k_per_point, signal


class FetchAllPlayersFieldNameTests(unittest.TestCase):
    def test_output_uses_average_points_not_points_avg(self):
        # Reiner Vertrags-Test ohne echten API-Call: prueft nur, dass die
        # Konstante/Doku-Referenz auf 'average_points' zeigt, indem wir das
        # Modul nach dem alten Feldnamen durchsuchen.
        import inspect
        import src.player_valuation as pv
        source = inspect.getsource(pv)
        self.assertNotIn('"points_avg"', source)
        self.assertIn('"average_points"', source)


class KPerPointTests(unittest.TestCase):
    def test_computes_market_value_over_average_points(self):
        row = {"market_value": 1_000_000, "average_points": 200}
        self.assertEqual(k_per_point(row), 5000.0)

    def test_average_points_zero_returns_none(self):
        row = {"market_value": 1_000_000, "average_points": 0}
        self.assertIsNone(k_per_point(row))

    def test_average_points_missing_returns_none(self):
        row = {"market_value": 1_000_000}
        self.assertIsNone(k_per_point(row))

    def test_market_value_none_returns_none(self):
        row = {"market_value": None, "average_points": 200}
        self.assertIsNone(k_per_point(row))


class SignalTests(unittest.TestCase):
    def test_signal_above_one_means_under_reference_price(self):
        # Kandidat kostet weniger pro Punkt (k/Punkt=4000) als das
        # Referenz-K (5000) -> Signal > 1, "guenstig".
        row = {"market_value": 800_000, "average_points": 200}
        self.assertEqual(signal(row, k=5000), 1.25)

    def test_kp_none_because_average_points_zero_returns_none(self):
        row = {"market_value": 1_000_000, "average_points": 0}
        self.assertIsNone(signal(row, k=5000))

    def test_kp_zero_because_market_value_zero_returns_none(self):
        # market_value=0 ist nicht None (der explizite Guard in k_per_point
        # greift nicht), macht k_per_point aber zu 0.0 - "not kp" faengt das.
        row = {"market_value": 0, "average_points": 200}
        self.assertIsNone(signal(row, k=5000))


class FairwertTests(unittest.TestCase):
    def test_computes_average_points_times_k(self):
        row = {"average_points": 200}
        self.assertEqual(fairwert(row, k=5000), 1_000_000)

    def test_average_points_none_returns_none(self):
        row = {"average_points": None}
        self.assertIsNone(fairwert(row, k=5000))

    def test_average_points_zero_returns_none(self):
        row = {"average_points": 0}
        self.assertIsNone(fairwert(row, k=5000))
