import unittest
from unittest.mock import MagicMock
from src.migrate_wunschkader_player_ids import _resolve_player_id


class ResolvePlayerIdTests(unittest.TestCase):
    def test_returns_id_for_unique_name_match(self):
        players = {"p1": {"name": "Krauß"}, "p2": {"name": "Stage"}}
        self.assertEqual(_resolve_player_id("Krauß", players), "p1")

    def test_returns_none_for_no_match(self):
        players = {"p1": {"name": "Krauß"}}
        self.assertIsNone(_resolve_player_id("Unbekannt", players))

    def test_returns_none_for_ambiguous_match(self):
        players = {"p1": {"name": "Müller"}, "p2": {"name": "Müller"}}
        self.assertIsNone(_resolve_player_id("Müller", players))
