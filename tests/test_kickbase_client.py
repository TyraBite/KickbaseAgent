import os
import unittest
from unittest.mock import patch

from src.kickbase_client import select_league, status_label


class SelectLeagueTests(unittest.TestCase):
    def _leagues(self):
        return [{"id": "111", "name": "Kickb4se"}, {"id": "222", "name": "MLS Gameweek #16"}]

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_first_league_without_override(self):
        self.assertEqual(select_league(self._leagues())["id"], "111")

    @patch.dict(os.environ, {"KICKBASE_LEAGUE_ID": "222"})
    def test_returns_matching_league_when_override_set(self):
        self.assertEqual(select_league(self._leagues())["id"], "222")

    @patch.dict(os.environ, {"KICKBASE_LEAGUE_ID": "999"})
    def test_raises_when_override_not_found(self):
        with self.assertRaises(RuntimeError):
            select_league(self._leagues())

    @patch.dict(os.environ, {}, clear=True)
    def test_single_league_no_warning_needed(self):
        self.assertEqual(select_league([{"id": "111", "name": "Solo"}])["id"], "111")


class StatusLabelTests(unittest.TestCase):
    def test_zero_is_fit_no_label(self):
        self.assertIsNone(status_label(0))

    def test_one_is_verletzt(self):
        self.assertEqual(status_label(1), "Verletzt")

    def test_two_is_angeschlagen(self):
        self.assertEqual(status_label(2), "Angeschlagen")

    def test_four_is_im_aufbau(self):
        self.assertEqual(status_label(4), "Im Aufbau")

    def test_unconfirmed_code_falls_back_to_placeholder(self):
        self.assertEqual(status_label(8), "Status-Code 8 (Bedeutung in v4-API nicht zweifelsfrei bestaetigt)")
