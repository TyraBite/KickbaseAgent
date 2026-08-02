"""News/Sentiment-Ingestion (Phase B: ML-Marktwert-Turning-Points, siehe
docs/superpowers/specs/2026-08-02-news-sentiment-design.md). Sammelt fuer
jeden Spieler im Kandidatenpool (dashboard_snapshot/latest's players-Map,
~450 Spieler, dasselbe Universum wie market_predictor.py) die juengsten
Google-News-RSS-Treffer (Kicker.de/Transfermarkt.de scheiden aus - Opt-Out
per robots.txt bzw. technisch nicht erreichbar, siehe Design-Spec) und
klassifiziert deren Sentiment per germansentiment (fertig trainiertes
deutsches BERT-Modell, CPU-Inferenz, kein API-Call/keine laufenden Kosten).

Laeuft als eigener, vom Dashboard-Cron unabhaengiger GitHub-Actions-Workflow
(.github/workflows/player-news-sentiment.yml, 1x/Tag) - liest
dashboard_snapshot/latest NUR lesend (kein neuer Kickbase-API-Call) und
schreibt die Rohdaten nach player_news_log (ueber
firestore_db.upsert_history_entries, siehe Phase A/
docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md fuer
den generalisierten Batch-Writer). Liefert nur Rohdaten - Aggregation/
Feature-Berechnung fuer die ML-Prognose ist Phase C (eigene, noch nicht
geschriebene Spec).

Wichtiger, live verifizierter Fund (2026-08-02): Google News RSS liefert
KEINEN echten Anriss-/Snippet-Text im <description>-Feld - das ist nur eine
HTML-verpackte Dopplung des Titels plus Verlagsname. Das <source>-Element
(reiner Klartext-Verlagsname) wird stattdessen fuer das 'snippet'-Feld
genutzt, siehe fetch_news_for_player(). Sentiment-Klassifikation nutzt
deshalb ausschliesslich den Titel als Input."""

import datetime
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

NEWS_LOOKBACK_DAYS = 7
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
RSS_REQUEST_TIMEOUT_SECONDS = 15


def _build_query(player_name: str, team_name: str | None) -> str:
    """Spielername + Vereinsname zur Eindeutigkeit - ein reiner Nachname
    (z.B. 'Mueller') waere sonst viel zu unspezifisch fuer sinnvolle
    Treffer. Anfuehrungszeichen um den Namen erzwingen bei Google News eine
    Phrasensuche statt einer Treffermenge fuer die Einzelwoerter."""
    parts = [f'"{player_name}"']
    if team_name:
        parts.append(team_name)
    return " ".join(parts)


def fetch_news_for_player(player_name: str, team_name: str | None) -> list[dict]:
    """Ruft Google News RSS fuer einen Spieler ab, filtert auf die letzten
    NEWS_LOOKBACK_DAYS Tage per pubDate. Gibt eine Liste von
    {title, snippet, link, pub_date} zurueck, leere Liste bei Fehler oder
    keinen Treffern - ein einzelner fehlgeschlagener Spieler darf den
    Gesamtlauf nicht abbrechen (gleiches Resilienz-Muster wie
    market_predictor._fetch_player_training_frame). snippet ist der
    Verlagsname aus dem <source>-Element, KEIN echter Anriss-Text - Google
    News RSS liefert das nicht (siehe Modul-Docstring, live verifiziert
    2026-08-02). link ist eine Google-News-Redirect-URL, kein Direktlink
    zum Original-Artikel - ausreichend fuer den Doc-Id-Hash (article_hash),
    Volltext-Abruf ist ohnehin bewusst out of scope (siehe Design-Spec)."""
    query = _build_query(player_name, team_name)
    try:
        response = requests.get(
            GOOGLE_NEWS_RSS_URL,
            params={"q": query, "hl": "de", "gl": "DE"},
            timeout=RSS_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as exc:
        print(f"Warnung: Google-News-RSS fuer '{player_name}' fehlgeschlagen: {exc}", file=sys.stderr)
        return []

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=NEWS_LOOKBACK_DAYS)
    articles = []
    for item in root.findall("./channel/item"):
        pub_date_raw = item.findtext("pubDate") or ""
        try:
            pub_date = parsedate_to_datetime(pub_date_raw)
        except (TypeError, ValueError):
            continue
        if pub_date is None:
            continue
        if pub_date.tzinfo is None:
            # RFC-822 erlaubt den Zonen-Marker "-0000" ("Zeit unbekannt/UTC"),
            # den parsedate_to_datetime() im Gegensatz zu "+0000"/"GMT" als
            # naives datetime ohne tzinfo zurueckgibt. Ohne Normalisierung
            # wuerde der Vergleich unten mit dem tz-aware cutoff ein
            # TypeError werfen und den gesamten Abruf fuer diesen Spieler
            # abbrechen statt nur diesen einen Artikel zu uebergehen.
            pub_date = pub_date.replace(tzinfo=datetime.timezone.utc)
        if pub_date < cutoff:
            continue
        articles.append({
            "title": item.findtext("title") or "",
            "snippet": item.findtext("source") or "",
            "link": item.findtext("link") or "",
            "pub_date": pub_date.date().isoformat(),
        })
    return articles
