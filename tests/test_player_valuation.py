import unittest
from src.player_valuation import fetch_all_players


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
