import os
import unittest
from unittest.mock import patch

from src.dashboard_export import _build_alle_spieler, _load_wunschkader


class BuildAlleSpielerTests(unittest.TestCase):
    def test_marks_own_squad_players(self):
        players = [{"player_id": "p1", "name": "Krauß", "position": "Mittelfeld",
                    "team_name": "Bremen", "market_value": 10_000_000,
                    "points_avg": 150, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={}, own_squad_names={"Krauß"}, calibration=None)

        self.assertEqual(rows[0]["owner"], "Eigener Kader")
        self.assertIsNone(rows[0]["status_label"])

    def test_marks_other_manager_ownership(self):
        players = [{"player_id": "p2", "name": "Zentner", "position": "Torwart",
                    "team_name": "Mainz", "market_value": 9_000_000,
                    "points_avg": 100, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={"p2": "Fleischmanns"}, own_squad_names=set(), calibration=None)

        self.assertEqual(rows[0]["owner"], "Fleischmanns")

    def test_marks_free_agent(self):
        players = [{"player_id": "p3", "name": "Heuer Fernandes", "position": "Torwart",
                    "team_name": "Hamburg", "market_value": 11_000_000,
                    "points_avg": 90, "starting_rank": 1, "status_code": 0}]

        rows = _build_alle_spieler(players, owned_by={}, own_squad_names=set(), calibration=None)

        self.assertEqual(rows[0]["owner"], "Frei")


class LoadWunschkaderTests(unittest.TestCase):
    def test_returns_none_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(_load_wunschkader())

    @patch("src.dashboard_export.firestore_db.get_wunschkader")
    @patch("src.dashboard_export.firestore_db.connect")
    def test_returns_data_from_firestore_when_enabled(self, mock_connect, mock_get):
        mock_get.return_value = {"targets": [{"name": "Krauß"}], "formation": "3-4-3"}
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_wunschkader()
        self.assertEqual(result["formation"], "3-4-3")

    @patch("src.dashboard_export.firestore_db.get_wunschkader")
    @patch("src.dashboard_export.firestore_db.connect")
    def test_propagates_exception_instead_of_swallowing(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            with self.assertRaises(RuntimeError):
                _load_wunschkader()
