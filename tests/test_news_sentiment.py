"""Tests fuer src/news_sentiment.py: RSS-Fetch/Sentiment-Klassifikation
gegen gemockte requests/germansentiment-Aufrufe (kein echter Netzwerk-
/Modell-Zugriff), siehe
docs/superpowers/specs/2026-08-02-news-sentiment-design.md."""

import datetime
import hashlib
import os
import unittest
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import requests

from src.news_sentiment import (
    _build_query,
    _max_workers,
    classify_sentiment,
    collect_news_sentiment,
    fetch_news_for_player,
)


class BuildQueryTests(unittest.TestCase):
    def test_includes_quoted_name_and_team(self):
        self.assertEqual(_build_query("Marco Friedl", "Werder Bremen"), '"Marco Friedl" Werder Bremen')

    def test_omits_team_when_none(self):
        self.assertEqual(_build_query("Marco Friedl", None), '"Marco Friedl"')

    def test_omits_team_when_empty_string(self):
        self.assertEqual(_build_query("Marco Friedl", ""), '"Marco Friedl"')


RSS_FIXTURE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>"Marco Friedl" Werder Bremen - Google News</title>
    <item>
      <title>Frust bei Werder-Kapitaen Friedl: aktueller Artikel</title>
      <link>https://news.google.com/rss/articles/recent-id?oc=5</link>
      <pubDate>{recent_pub_date}</pubDate>
      <description>&lt;a href="https://news.google.com/rss/articles/recent-id?oc=5" target="_blank"&gt;Frust bei Werder-Kapitaen Friedl: aktueller Artikel&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;buten un binnen&lt;/font&gt;</description>
      <source url="https://www.butenunbinnen.de">buten un binnen</source>
    </item>
    <item>
      <title>Alter Artikel ausserhalb des Lookback-Fensters</title>
      <link>https://news.google.com/rss/articles/old-id?oc=5</link>
      <pubDate>{old_pub_date}</pubDate>
      <description>&lt;a href="https://news.google.com/rss/articles/old-id?oc=5" target="_blank"&gt;Alter Artikel ausserhalb des Lookback-Fensters&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;BILD&lt;/font&gt;</description>
      <source url="https://www.bild.de">BILD</source>
    </item>
    <item>
      <title>Artikel ohne source-Element</title>
      <link>https://news.google.com/rss/articles/no-source-id?oc=5</link>
      <pubDate>{recent_pub_date}</pubDate>
      <description>irrelevant</description>
    </item>
  </channel>
</rss>"""


def _mock_response(xml_bytes: bytes) -> MagicMock:
    response = MagicMock()
    response.content = xml_bytes
    response.raise_for_status = MagicMock()
    return response


class FetchNewsForPlayerTests(unittest.TestCase):
    def _fixture_xml(self, now: datetime.datetime) -> bytes:
        recent = format_datetime(now - datetime.timedelta(days=2))
        old = format_datetime(now - datetime.timedelta(days=10))
        return RSS_FIXTURE_TEMPLATE.format(recent_pub_date=recent, old_pub_date=old).encode("utf-8")

    @patch("src.news_sentiment.requests.get")
    def test_filters_out_articles_outside_lookback_window(self, mock_get):
        now = datetime.datetime.now(datetime.timezone.utc)
        mock_get.return_value = _mock_response(self._fixture_xml(now))

        result = fetch_news_for_player("Marco Friedl", "Werder Bremen")

        titles = [a["title"] for a in result]
        self.assertIn("Frust bei Werder-Kapitaen Friedl: aktueller Artikel", titles)
        self.assertNotIn("Alter Artikel ausserhalb des Lookback-Fensters", titles)

    @patch("src.news_sentiment.requests.get")
    def test_snippet_field_is_publisher_name_from_source_element(self, mock_get):
        now = datetime.datetime.now(datetime.timezone.utc)
        mock_get.return_value = _mock_response(self._fixture_xml(now))

        result = fetch_news_for_player("Marco Friedl", "Werder Bremen")

        recent = next(a for a in result if a["title"] == "Frust bei Werder-Kapitaen Friedl: aktueller Artikel")
        self.assertEqual(recent["snippet"], "buten un binnen")
        self.assertEqual(recent["link"], "https://news.google.com/rss/articles/recent-id?oc=5")
        self.assertEqual(recent["pub_date"], (now - datetime.timedelta(days=2)).date().isoformat())

    @patch("src.news_sentiment.requests.get")
    def test_missing_source_element_gives_empty_snippet(self, mock_get):
        now = datetime.datetime.now(datetime.timezone.utc)
        mock_get.return_value = _mock_response(self._fixture_xml(now))

        result = fetch_news_for_player("Marco Friedl", "Werder Bremen")

        no_source = next(a for a in result if a["title"] == "Artikel ohne source-Element")
        self.assertEqual(no_source["snippet"], "")

    @patch("src.news_sentiment.requests.get")
    def test_query_passed_as_request_param(self, mock_get):
        mock_get.return_value = _mock_response(b"<rss><channel></channel></rss>")

        fetch_news_for_player("Robert Mueller", "Werder Bremen")

        called_params = mock_get.call_args.kwargs["params"]
        self.assertEqual(called_params["q"], _build_query("Robert Mueller", "Werder Bremen"))
        self.assertEqual(called_params["hl"], "de")
        self.assertEqual(called_params["gl"], "DE")

    @patch("src.news_sentiment.requests.get")
    def test_network_error_returns_empty_list_not_raises(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("network down")

        result = fetch_news_for_player("Marco Friedl", "Werder Bremen")

        self.assertEqual(result, [])

    @patch("src.news_sentiment.requests.get")
    def test_malformed_xml_returns_empty_list_not_raises(self, mock_get):
        mock_get.return_value = _mock_response(b"not valid xml <<<")

        result = fetch_news_for_player("Marco Friedl", "Werder Bremen")

        self.assertEqual(result, [])

    @patch("src.news_sentiment.requests.get")
    def test_empty_channel_returns_empty_list(self, mock_get):
        mock_get.return_value = _mock_response(b"<rss><channel></channel></rss>")

        result = fetch_news_for_player("Marco Friedl", "Werder Bremen")

        self.assertEqual(result, [])

    @patch("src.news_sentiment.requests.get")
    def test_naive_pub_date_from_rfc822_dash_zero_offset_does_not_raise(self, mock_get):
        # RFC-822 erlaubt "-0000" als Zonen-Marker ("Zeit unbekannt/UTC"), im
        # Unterschied zu "+0000"/"GMT" gibt parsedate_to_datetime() dafuer ein
        # naives datetime ohne tzinfo zurueck. Ohne Normalisierung wuerde der
        # Vergleich mit dem tz-aware cutoff ein TypeError werfen und den
        # gesamten Abruf fuer diesen Spieler crashen statt nur den Artikel zu
        # ueberspringen.
        now = datetime.datetime.now(datetime.timezone.utc)
        recent = now - datetime.timedelta(days=2)
        naive_style_pub_date = format_datetime(recent).replace("+0000", "-0000")
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Artikel mit -0000 Zonen-Marker</title>
      <link>https://news.google.com/rss/articles/dash-zero-id?oc=5</link>
      <pubDate>{naive_style_pub_date}</pubDate>
      <source url="https://www.butenunbinnen.de">buten un binnen</source>
    </item>
  </channel>
</rss>""".encode("utf-8")
        mock_get.return_value = _mock_response(xml)

        result = fetch_news_for_player("Marco Friedl", "Werder Bremen")

        titles = [a["title"] for a in result]
        self.assertIn("Artikel mit -0000 Zonen-Marker", titles)
        article = next(a for a in result if a["title"] == "Artikel mit -0000 Zonen-Marker")
        self.assertEqual(article["pub_date"], recent.date().isoformat())


class MaxWorkersTests(unittest.TestCase):
    def test_defaults_to_eight(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_max_workers(), 8)

    def test_reads_env_override(self):
        with patch.dict(os.environ, {"NEWS_SENTIMENT_MAX_WORKERS": "3"}):
            self.assertEqual(_max_workers(), 3)


class ClassifySentimentTests(unittest.TestCase):
    def test_empty_texts_returns_empty_list_without_calling_model(self):
        model = MagicMock()
        self.assertEqual(classify_sentiment(model, []), [])
        model.predict_sentiment.assert_not_called()

    def test_batch_call_maps_label_and_matching_probability(self):
        model = MagicMock()
        model.predict_sentiment.return_value = (
            ["positive", "negative"],
            [
                [["positive", 0.9761], ["negative", 0.0235], ["neutral", 0.0003]],
                [["positive", 0.01], ["negative", 0.95], ["neutral", 0.04]],
            ],
        )

        result = classify_sentiment(model, ["Text A", "Text B"])

        self.assertEqual(result, [
            {"label": "positive", "score": 0.9761},
            {"label": "negative", "score": 0.95},
        ])
        model.predict_sentiment.assert_called_once_with(["Text A", "Text B"], output_probabilities=True)


class CollectNewsSentimentTests(unittest.TestCase):
    def _today(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    @patch("src.news_sentiment.SentimentModel")
    @patch("src.news_sentiment.fetch_news_for_player")
    def test_builds_entry_with_article_hash_and_sentiment(self, mock_fetch, mock_model_cls):
        mock_fetch.side_effect = lambda name, team: (
            [{"title": "Tor fuer Krauss", "snippet": "Bremen", "link": "https://example.com/a1", "pub_date": "2026-08-01"}]
            if name == "Krauss" else []
        )
        mock_model_cls.return_value.predict_sentiment.return_value = (
            ["positive"],
            [[["positive", 0.9], ["negative", 0.05], ["neutral", 0.05]]],
        )
        players = [
            {"player_id": "p1", "name": "Krauss", "team_name": "Bremen"},
            {"player_id": "p2", "name": "Niemand", "team_name": "Bremen"},
        ]

        result = collect_news_sentiment(players)

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["player_id"], "p1")
        self.assertEqual(entry["headline"], "Tor fuer Krauss")
        self.assertEqual(entry["snippet"], "Bremen")
        self.assertEqual(entry["link"], "https://example.com/a1")
        self.assertEqual(entry["pub_date"], "2026-08-01")
        self.assertEqual(entry["sentiment_label"], "positive")
        self.assertEqual(entry["sentiment_score"], 0.9)
        self.assertEqual(entry["date"], self._today())
        self.assertEqual(entry["article_hash"], hashlib.sha1(b"https://example.com/a1").hexdigest()[:12])
        mock_model_cls.return_value.predict_sentiment.assert_called_once_with(["Tor fuer Krauss"], output_probabilities=True)

    @patch("src.news_sentiment.SentimentModel")
    @patch("src.news_sentiment.fetch_news_for_player")
    def test_player_with_no_articles_contributes_nothing(self, mock_fetch, mock_model_cls):
        mock_fetch.return_value = []
        mock_model_cls.return_value.predict_sentiment.return_value = ([], [])

        result = collect_news_sentiment([{"player_id": "p1", "name": "Niemand", "team_name": None}])

        self.assertEqual(result, [])

    @patch("src.news_sentiment.SentimentModel")
    @patch("src.news_sentiment.fetch_news_for_player")
    def test_one_players_fetch_failure_does_not_abort_others(self, mock_fetch, mock_model_cls):
        def side_effect(name, team):
            if name == "Broken":
                raise RuntimeError("boom")
            return [{"title": "Meldung", "snippet": "Quelle", "link": "https://example.com/b1", "pub_date": "2026-08-01"}]
        mock_fetch.side_effect = side_effect
        mock_model_cls.return_value.predict_sentiment.return_value = (
            ["neutral"], [[["positive", 0.1], ["negative", 0.1], ["neutral", 0.8]]]
        )
        players = [
            {"player_id": "p1", "name": "Broken", "team_name": None},
            {"player_id": "p2", "name": "OK", "team_name": None},
        ]

        result = collect_news_sentiment(players)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["player_id"], "p2")

    @patch("src.news_sentiment.SentimentModel")
    @patch("src.news_sentiment.fetch_news_for_player")
    def test_players_missing_player_id_or_name_are_skipped_without_fetching(self, mock_fetch, mock_model_cls):
        mock_model_cls.return_value.predict_sentiment.return_value = ([], [])
        players = [
            {"player_id": None, "name": "X", "team_name": None},
            {"player_id": "p1", "name": None, "team_name": None},
        ]

        result = collect_news_sentiment(players)

        self.assertEqual(result, [])
        mock_fetch.assert_not_called()

    @patch("src.news_sentiment.SentimentModel")
    @patch("src.news_sentiment.fetch_news_for_player")
    def test_two_articles_same_player_get_distinct_article_hashes(self, mock_fetch, mock_model_cls):
        mock_fetch.return_value = [
            {"title": "Artikel 1", "snippet": "Q1", "link": "https://example.com/x1", "pub_date": "2026-08-01"},
            {"title": "Artikel 2", "snippet": "Q2", "link": "https://example.com/x2", "pub_date": "2026-08-01"},
        ]
        mock_model_cls.return_value.predict_sentiment.return_value = (
            ["neutral", "neutral"],
            [[["positive", 0.1], ["negative", 0.1], ["neutral", 0.8]], [["positive", 0.2], ["negative", 0.1], ["neutral", 0.7]]],
        )

        result = collect_news_sentiment([{"player_id": "p1", "name": "X", "team_name": None}])

        self.assertEqual(len(result), 2)
        article_hashes = {e["article_hash"] for e in result}
        self.assertEqual(len(article_hashes), 2)
