"""Tests fuer src/news_sentiment.py: RSS-Fetch/Sentiment-Klassifikation
gegen gemockte requests/germansentiment-Aufrufe (kein echter Netzwerk-
/Modell-Zugriff), siehe
docs/superpowers/specs/2026-08-02-news-sentiment-design.md."""

import datetime
import unittest
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import requests

from src.news_sentiment import _build_query, fetch_news_for_player


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
