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

import concurrent.futures
import datetime
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from germansentiment import SentimentModel

NEWS_LOOKBACK_DAYS = 7
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
RSS_REQUEST_TIMEOUT_SECONDS = 15


def _max_workers() -> int:
    """Analog market_predictor._max_workers() - begrenzte Parallelitaet
    fuer die RSS-Fetches statt unbegrenzter Parallelitaet, um ein Blocken
    durch Google bei ~450 taeglichen Requests zu vermeiden (siehe Design-
    Spec, Abschnitt 'Google-News-Rate-Limiting')."""
    return int(os.environ.get("NEWS_SENTIMENT_MAX_WORKERS", 8))


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


def classify_sentiment(model: "SentimentModel", texts: list[str]) -> list[dict]:
    """Batch-Klassifikation ueber germansentiment - gibt pro Text
    {label: 'positive'|'negative'|'neutral', score: float} zurueck. Batch
    statt Einzelaufruf pro Artikel, da germansentiment.predict_sentiment()
    nativ Listen akzeptiert - spart Modell-Overhead pro Aufruf. score ist
    die Wahrscheinlichkeit DES vorhergesagten Labels (nicht z.B. immer die
    von 'positive'), aus der von output_probabilities=True zurueckgegebenen
    Liste aller drei Klassen-Wahrscheinlichkeiten herausgesucht."""
    if not texts:
        return []
    labels, probabilities = model.predict_sentiment(texts, output_probabilities=True)
    results = []
    for label, probs in zip(labels, probabilities):
        score = next((float(p[1]) for p in probs if p[0] == label), None)
        results.append({"label": label, "score": score})
    return results


def collect_news_sentiment(players: list[dict]) -> list[dict]:
    """Orchestriert: pro Spieler fetch_news_for_player(), dann alle
    gesammelten Artikel-TITEL (nicht title+snippet - snippet ist nur der
    Verlagsname, kein Sentiment-Signal, siehe Modul-Docstring) in EINEM
    Batch durch classify_sentiment() (nicht pro Spieler einzeln - Modell-
    Ladezeit faellt nur einmal an). Gibt eine flache Liste von Rohdaten-
    Dicts zurueck (inkl. article_hash, aber OHNE fertiges doc_id-Feld -
    der Firestore-Doc-Key wird erst in run_news_sentiment_ingestion() per
    upsert_history_entries()s doc_id_fn-Parameter gebildet, siehe dort),
    bereit fuer
    firestore_db.upsert_history_entries(client, 'player_news_log', ..., doc_id_fn=...).
    Parallelisiert die RSS-Fetches ueber ThreadPoolExecutor (gleiches
    Muster wie market_predictor._max_workers(), Netzwerk-IO-gebunden - das
    Sentiment-Modell selbst laeuft NICHT parallel, ein BERT-Modell mehrfach
    gleichzeitig zu laden waere reiner Speicher-Overhead ohne Nutzen bei
    dieser Batch-Groesse). Spieler ohne player_id/name werden ohne Fetch
    uebersprungen - kein sinnvoller RSS-Query ohne Namen moeglich."""
    valid_players = [p for p in players if p.get("player_id") and p.get("name")]

    articles_by_player: dict[str, list[dict]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers()) as executor:
        futures = {
            executor.submit(fetch_news_for_player, p["name"], p.get("team_name")): p["player_id"]
            for p in valid_players
        }
        for future in concurrent.futures.as_completed(futures):
            player_id = futures[future]
            try:
                articles_by_player[player_id] = future.result()
            except Exception as exc:
                print(f"Warnung: News-Fetch fuer Spieler '{player_id}' fehlgeschlagen: {exc}", file=sys.stderr)
                articles_by_player[player_id] = []

    flat_articles = [
        (player_id, article)
        for player_id, articles in articles_by_player.items()
        for article in articles
    ]
    sentiments = classify_sentiment(SentimentModel(), [article["title"] for _pid, article in flat_articles])

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    entries = []
    for (player_id, article), sentiment in zip(flat_articles, sentiments):
        article_hash = hashlib.sha1(article["link"].encode()).hexdigest()[:12]
        entries.append({
            "article_hash": article_hash,
            "player_id": player_id,
            "date": today,
            "pub_date": article["pub_date"],
            "headline": article["title"],
            "snippet": article["snippet"],
            "link": article["link"],
            "sentiment_label": sentiment["label"],
            "sentiment_score": sentiment["score"],
        })
    return entries
