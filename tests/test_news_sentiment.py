"""Tests fuer src/news_sentiment.py: RSS-Fetch/Sentiment-Klassifikation
gegen gemockte requests/germansentiment-Aufrufe (kein echter Netzwerk-
/Modell-Zugriff), siehe
docs/superpowers/specs/2026-08-02-news-sentiment-design.md."""

import unittest

from src.news_sentiment import _build_query


class BuildQueryTests(unittest.TestCase):
    def test_includes_quoted_name_and_team(self):
        self.assertEqual(_build_query("Marco Friedl", "Werder Bremen"), '"Marco Friedl" Werder Bremen')

    def test_omits_team_when_none(self):
        self.assertEqual(_build_query("Marco Friedl", None), '"Marco Friedl"')

    def test_omits_team_when_empty_string(self):
        self.assertEqual(_build_query("Marco Friedl", ""), '"Marco Friedl"')
