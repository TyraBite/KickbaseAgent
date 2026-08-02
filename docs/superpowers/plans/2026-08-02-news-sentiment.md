# News/Sentiment-Ingestion (Phase B: ML-Marktwert-Turning-Points) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Für alle ~450 Spieler des Kandidatenpools täglich die letzten `NEWS_LOOKBACK_DAYS` Google-News-RSS-Treffer sammeln, per `germansentiment` (deutsches BERT-Sentiment-Modell) klassifizieren und als Rohdaten in einer neuen Firestore-Collection `player_news_log` ablegen — Rohdaten-Basis für Phase C (ML-Feature-Integration, eigene, noch nicht geschriebene Spec).

**Architecture:** Neues, eigenständiges Modul `src/news_sentiment.py`, orchestriert von einem eigenen, vom Dashboard-Cron komplett unabhängigen GitHub-Actions-Workflow (`player-news-sentiment.yml`, 1×/Tag). Liest `dashboard_snapshot/latest`'s `players`-Map nur lesend (kein neuer Kickbase-API-Call), holt pro Spieler parallelisiert (`ThreadPoolExecutor`, analog `market_predictor._max_workers()`) die RSS-Treffer, klassifiziert alle gesammelten Artikel-Titel in EINEM Batch-Aufruf des BERT-Modells und schreibt über Phase A's generalisierten Batch-Writer (`firestore_db.upsert_history_entries`) nach `player_news_log`.

**Tech Stack:** Python, `requests` (RSS-Fetch), `xml.etree.ElementTree` (RSS-Parsing), `germansentiment` (BERT-Sentiment, zieht `torch`+`transformers` transitiv), Firestore (`google-cloud-firestore`), GitHub Actions.

## Global Constraints

- **Cross-Phase-Abhängigkeit (verpflichtend, MUSS vor Ausführung dieses Plans geprüft werden):** Dieser Plan setzt voraus, dass Phase A (`docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md`, Implementierungsplan falls vorhanden unter `docs/superpowers/plans/2026-08-02-startelf-status-historie.md`) **bereits umgesetzt ist** und `firestore_db.upsert_history_entries(client, collection, entries)` / `firestore_db.get_history(client, collection)` bereits existieren. **Zum Zeitpunkt der Erstellung dieses Plans (2026-08-02) existierte die Phase-A-Plan-Datei noch nicht** — die hier verwendeten Signaturen stammen direkt aus dem Design-Spec-Sketch und müssen vor Ausführung dieses Plans gegen Phase A's tatsächliche Implementierung verifiziert werden (siehe Task 5, Step 0).
- **Update 2026-08-02, nach Phase A's Fertigstellung — der folgende Absatz beschreibt NICHT mehr die tatsächliche Lösung, siehe Korrektur direkt danach:** ~~Konkreter, im Design-Spec-Sketch NICHT sichtbarer Konflikt, den dieser Plan auflöst: Phase A's `upsert_history_entries` ersetzt `upsert_fitness_history_entries`, deren Doc-Id fest `{date}_{player_id}` ist (ein Event pro Spieler pro Tag). Phase B braucht dagegen `{date}_{player_id}_{article_hash}` (mehrere Artikel pro Spieler pro Tag möglich) — eine fest hartkodierte `{date}_{player_id}`-Formel in `upsert_history_entries` würde mehrere Artikel desselben Spielers am selben Tag im selben Batch-Write gegenseitig überschreiben. Dieser Plan geht davon aus, dass `upsert_history_entries` den Firestore-Doc-Key aus einem expliziten `doc_id`-Feld liest, das JEDES entry-Dict selbst mitbringt.~~
  **Tatsächliche Lösung (verifiziert gegen Phase A's echte Implementierung, `src/firestore_db.py`, nach Abschluss von Phase A/`docs/superpowers/plans/2026-08-02-startelf-status-historie.md` Task 2):** `upsert_history_entries(client, collection, entries, doc_id_fn=lambda e: f"{e['date']}_{e['player_id']}")` — der Doc-Key wird von einer ÜBERSCHREIBBAREN `doc_id_fn`-Callback-Funktion gebildet (Default = die bestehende Fitness-/Startelf-Formel), NICHT aus einem im Entry-Dict gespeicherten `doc_id`-Feld gelesen. Für `player_news_log` muss der Aufruf deshalb explizit `doc_id_fn=lambda e: f"{e['date']}_{e['player_id']}_{e['article_hash']}"` übergeben — jedes entry-Dict braucht dafür ein `article_hash`-Feld (nicht ein fertig zusammengesetztes `doc_id`-Feld). Jede Stelle in diesem Plan, die von einem `doc_id`-Feld im Entry-Dict ausgeht (Task 4's Rückgabewert, die zugehörigen Tests, Task 5's Aufruf), ist entsprechend korrigiert — siehe die Inline-Korrekturen dort.
- **Wichtiger, live verifizierter Fund (2026-08-02, per WebFetch gegen die echte Google-News-RSS-URL geprüft), der die Design-Spec-Annahme korrigiert:** Google News RSS liefert **keinen echten Anriss-/Snippet-Text**. Das `<description>`-Feld enthält nur eine HTML-verpackte Dopplung des Titels plus den Verlagsnamen (`&lt;a href="..."&gt;{title}&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;{Verlag}&lt;/font&gt;`) — keine zusätzliche inhaltliche Information. Dieser Plan nutzt stattdessen das separate `<source>`-Element (reiner Klartext-Verlagsname, kein HTML-Parsing nötig) für das im Spec vorgesehene `snippet`-Feld, dokumentiert aber klar, dass es sich dabei um den Verlagsnamen handelt, nicht um einen inhaltlichen Anriss. Als Sentiment-Klassifikations-Input wird deshalb ausschließlich `title` verwendet (nicht `title + snippet` — der Verlagsname trägt kein Sentiment-Signal und würde den BERT-Input nur verrauschen).
- Kein neuer Kickbase-API-Call — Spieler-Namen/Team kommen ausschließlich aus `dashboard_snapshot/latest`'s bereits vorhandener `players`-Map (read-only).
- Netzwerkfehler beim RSS-Fetch werden PRO SPIELER abgefangen (leere Liste, Lauf geht weiter) — Modell-Ladefehler (`germansentiment`) werden NICHT abgefangen, sollen den Workflow-Schritt sichtbar fehlschlagen lassen (kein sinnvoller Teilerfolg möglich, das Modell wird für alle Spieler gebraucht).
- Firestore-Schreibfehler werden abgefangen (Warnung auf stderr, kein Crash) — dieser Workflow ist komplett unabhängig vom kritischen Dashboard-Pfad, ein Fehlschlag bedeutet nur "heute keine neuen News-Daten".
- Doc-Id-Schema `{date}_{player_id}_{article_hash}`, `article_hash = hashlib.sha1(link.encode()).hexdigest()[:12]` — idempotent bei täglichem Rerun.
- Parallelisierung nur für die RSS-Fetches (`ThreadPoolExecutor`, `NEWS_SENTIMENT_MAX_WORKERS`-Env-Var, Default 8, exakt analog `market_predictor._max_workers()`/`MARKET_PREDICTOR_MAX_WORKERS`) — das Sentiment-Modell selbst läuft NICHT parallel (ein BERT-Modell mehrfach zu laden wäre reiner Speicher-Overhead ohne Nutzen bei diesem Batch-Volumen).
- `germansentiment==1.1.0` (PyPI, zieht `torch>=1.8.1` und `transformers` transitiv — mehrere hundert MB, akzeptiert laut Design-Spec). `pip install -r requirements.txt` muss einmalig vor Task 3 (erster Task, der die Bibliothek importiert) neu ausgeführt werden.
- Kein Rate-Limiting/Backoff vorab (nur bei tatsächlich beobachtetem Google-Blocking nachrüsten, nicht spekulativ einbauen).
- Kein Volltext-Abruf verlinkter Artikel, keine Frontend-Anzeige, keine Aggregation/Zeitfenster-Feature-Berechnung — alles Phase C.
- TDD durchgehend: Test zuerst, dann Implementierung. Backend-Verifikation nach jedem Task: `python3 -m unittest discover -s tests`.
- Aus jedem Task: `git add` nur die in diesem Task geänderten Dateien, dann committen ohne Co-Authored-By-Zeile (Push erlaubt, wenn Tests grün — bestehende Projekt-Policy).

---

## Task 1: Query-Builder `_build_query()`

**Files:**
- Create: `src/news_sentiment.py`
- Create: `tests/test_news_sentiment.py`

**Interfaces:**
- Produces: `_build_query(player_name: str, team_name: str | None) -> str`.

- [ ] **Step 1: Failing Test schreiben**

`tests/test_news_sentiment.py` neu anlegen:

```python
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
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'src.news_sentiment'`)

- [ ] **Step 3: Implementierung**

`src/news_sentiment.py` neu anlegen:

```python
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


def _build_query(player_name: str, team_name: str | None) -> str:
    """Spielername + Vereinsname zur Eindeutigkeit - ein reiner Nachname
    (z.B. 'Mueller') waere sonst viel zu unspezifisch fuer sinnvolle
    Treffer. Anfuehrungszeichen um den Namen erzwingen bei Google News eine
    Phrasensuche statt einer Treffermenge fuer die Einzelwoerter."""
    parts = [f'"{player_name}"']
    if team_name:
        parts.append(team_name)
    return " ".join(parts)
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment -v`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/news_sentiment.py tests/test_news_sentiment.py
git commit -m "news_sentiment: Query-Builder _build_query() ergaenzt"
```

---

## Task 2: RSS-Fetch `fetch_news_for_player()`

**Files:**
- Modify: `src/news_sentiment.py`
- Test: `tests/test_news_sentiment.py`

**Interfaces:**
- Consumes: `_build_query()` (Task 1).
- Produces: `fetch_news_for_player(player_name: str, team_name: str | None) -> list[dict]`. Rückgabe-Dicts haben `title: str`, `snippet: str` (Verlagsname, siehe Global Constraints), `link: str` (Google-News-Redirect-URL, kein Direktlink zum Original-Artikel), `pub_date: str` (ISO-Datum, `YYYY-MM-DD`). Leere Liste bei Fehler oder keinen Treffern innerhalb `NEWS_LOOKBACK_DAYS`.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_news_sentiment.py`, Imports am Dateikopf ergänzen und nach `BuildQueryTests` einfügen:

```python
import datetime
import unittest
from email.utils import format_datetime
from unittest.mock import MagicMock, patch

import requests

from src.news_sentiment import _build_query, fetch_news_for_player


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
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment.FetchNewsForPlayerTests -v`
Expected: FAIL (`ImportError: cannot import name 'fetch_news_for_player'`)

- [ ] **Step 3: Implementierung**

In `src/news_sentiment.py`, Imports nach dem Modul-Docstring ergänzen und `NEWS_LOOKBACK_DAYS`/`GOOGLE_NEWS_RSS_URL`/`RSS_REQUEST_TIMEOUT_SECONDS`-Konstanten sowie `fetch_news_for_player()` nach `_build_query()` einfügen:

```python
import datetime
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

NEWS_LOOKBACK_DAYS = 7
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
RSS_REQUEST_TIMEOUT_SECONDS = 15


def _build_query(player_name: str, team_name: str | None) -> str:
    ...
```

(Der `_build_query()`-Funktionskörper bleibt unverändert aus Task 1.)

Direkt danach:

```python
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
        if pub_date is None or pub_date < cutoff:
            continue
        articles.append({
            "title": item.findtext("title") or "",
            "snippet": item.findtext("source") or "",
            "link": item.findtext("link") or "",
            "pub_date": pub_date.date().isoformat(),
        })
    return articles
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment -v`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/news_sentiment.py tests/test_news_sentiment.py
git commit -m "news_sentiment: RSS-Fetch fetch_news_for_player() ergaenzt"
```

---

## Task 3: `_max_workers()` + Sentiment-Klassifikation `classify_sentiment()`

**Files:**
- Modify: `requirements.txt`
- Modify: `src/news_sentiment.py`
- Test: `tests/test_news_sentiment.py`

**Interfaces:**
- Consumes: nichts aus anderen Tasks (reine Funktion, Modell wird als Parameter übergeben).
- Produces: `_max_workers() -> int` (liest `NEWS_SENTIMENT_MAX_WORKERS`-Env-Var, Default 8). `classify_sentiment(model: "SentimentModel", texts: list[str]) -> list[dict]`. Rückgabe-Dicts haben `label: str` (`"positive"|"negative"|"neutral"`), `score: float` (Wahrscheinlichkeit des vorhergesagten Labels).

- [ ] **Step 1: `germansentiment` zu requirements.txt ergänzen und installieren**

In `requirements.txt`, ans Ende anfügen:

```
germansentiment==1.1.0
```

Run: `pip install -r requirements.txt`
Erwartung: installiert zusätzlich `torch`/`transformers` (mehrere hundert MB, kann je nach Verbindung einige Minuten dauern) — einmalig nötig, danach sind alle folgenden Tasks in diesem Plan schnell.

- [ ] **Step 2: Failing Tests schreiben**

In `tests/test_news_sentiment.py`, Imports ergänzen und am Ende der Datei einfügen:

```python
from unittest.mock import MagicMock, patch

from src.news_sentiment import _build_query, _max_workers, classify_sentiment, fetch_news_for_player


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
```

`import os` am Dateikopf ergänzen (für `MaxWorkersTests`), falls noch nicht vorhanden.

- [ ] **Step 3: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment.MaxWorkersTests tests.test_news_sentiment.ClassifySentimentTests -v`
Expected: FAIL (`ImportError: cannot import name '_max_workers'`)

- [ ] **Step 4: Implementierung**

In `src/news_sentiment.py`, Imports ergänzen (`os` alphabetisch vor `sys`):

```python
import datetime
import os
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from germansentiment import SentimentModel
```

Direkt nach den Konstanten (`RSS_REQUEST_TIMEOUT_SECONDS`), vor `_build_query()`:

```python
def _max_workers() -> int:
    """Analog market_predictor._max_workers() - begrenzte Parallelitaet
    fuer die RSS-Fetches statt unbegrenzter Parallelitaet, um ein Blocken
    durch Google bei ~450 taeglichen Requests zu vermeiden (siehe Design-
    Spec, Abschnitt 'Google-News-Rate-Limiting')."""
    return int(os.environ.get("NEWS_SENTIMENT_MAX_WORKERS", 8))
```

Nach `fetch_news_for_player()` einfügen:

```python
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
```

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment -v`
Expected: alle PASS (dieser Testlauf importiert jetzt `germansentiment`/`torch`/`transformers` transitiv über `src/news_sentiment.py` — falls Import-Fehler auftreten, `pip install -r requirements.txt` erneut prüfen, siehe Step 1)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/news_sentiment.py tests/test_news_sentiment.py
git commit -m "news_sentiment: germansentiment-Dependency + classify_sentiment()/_max_workers() ergaenzt"
```

---

## Task 4: Orchestrierung `collect_news_sentiment()`

**Files:**
- Modify: `src/news_sentiment.py`
- Test: `tests/test_news_sentiment.py`

**Interfaces:**
- Consumes: `fetch_news_for_player()` (Task 2), `classify_sentiment()`/`_max_workers()` (Task 3), `SentimentModel` (aus `germansentiment`, Task 3-Import).
- Produces: `collect_news_sentiment(players: list[dict]) -> list[dict]`. `players`-Elemente haben mindestens `{"player_id": str, "name": str, "team_name": str | None}` (Einträge ohne `player_id`/`name` werden übersprungen, kein Crash). Rückgabe-Dicts haben `article_hash: str` (nicht ein fertiges `doc_id`-Feld — der Firestore-Doc-Key wird erst in Task 5 per `upsert_history_entries`s `doc_id_fn`-Parameter aus `date`+`player_id`+`article_hash` gebildet, siehe Global Constraints), `player_id: str`, `date: str` (Lauf-Tag, ISO), `pub_date: str` (Original-Artikel-Datum, ISO), `headline: str`, `snippet: str`, `link: str`, `sentiment_label: str`, `sentiment_score: float`.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_news_sentiment.py`, Imports ergänzen und am Ende der Datei einfügen:

```python
import datetime
import hashlib
from unittest.mock import MagicMock, patch

from src.news_sentiment import (
    _build_query,
    _max_workers,
    classify_sentiment,
    collect_news_sentiment,
    fetch_news_for_player,
)


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
            return [] if name == "Broken" else [
                {"title": "Meldung", "snippet": "Quelle", "link": "https://example.com/b1", "pub_date": "2026-08-01"}
            ]
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
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment.CollectNewsSentimentTests -v`
Expected: FAIL (`ImportError: cannot import name 'collect_news_sentiment'`)

- [ ] **Step 3: Implementierung**

In `src/news_sentiment.py`, Imports ergänzen (`concurrent.futures`, `hashlib` alphabetisch):

```python
import concurrent.futures
import datetime
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from germansentiment import SentimentModel
```

Nach `classify_sentiment()` einfügen:

```python
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
            articles_by_player[player_id] = future.result()

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
```

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment -v`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/news_sentiment.py tests/test_news_sentiment.py
git commit -m "news_sentiment: Orchestrierung collect_news_sentiment() ergaenzt"
```

---

## Task 5: Firestore-Anbindung + Entry-Point `run_news_sentiment_ingestion()`

**Files:**
- Modify: `src/news_sentiment.py`
- Test: `tests/test_news_sentiment.py`

**Interfaces:**
- Consumes: `collect_news_sentiment()` (Task 4), `firestore_db.connect()`, `firestore_db.get_dashboard_snapshot()` (beide bereits vorhanden, siehe `src/firestore_db.py`), `firestore_db.upsert_history_entries(client, collection, entries)` (Phase A — siehe Step 0 unten).
- Produces: `_players_from_snapshot(snapshot: dict | None) -> list[dict]`, `run_news_sentiment_ingestion() -> dict` (Rückgabe `{"players_checked": int, "entries_written": int}`).

- [ ] **Step 0: Pre-Task-Check — Phase A tatsächlich vorhanden und kompatibel?**

Vor Beginn dieses Tasks prüfen:

```bash
grep -n "def upsert_history_entries\|def get_history" src/firestore_db.py
```

Erwartung: beide Funktionen existieren bereits (Phase A abgeschlossen — bestätigt, `docs/superpowers/plans/2026-08-02-startelf-status-historie.md`, alle 7 Tasks umgesetzt und gemerged). Falls NICHT (z.B. Ausführung dieses Plans in einem anderen Branch-Stand): Phase A zuerst umsetzen — dieser Task darf NICHT mit einer eigenen dritten Kopie der Batch-Write-Logik umgehen.

Zusätzlich verifizieren, dass `upsert_history_entries` genau die erwartete Signatur hat: `upsert_history_entries(client, collection, entries, doc_id_fn=lambda e: f"{e['date']}_{e['player_id']}")` — der Firestore-Doc-Key wird von der überschreibbaren `doc_id_fn`-Callback gebildet (Default = die Fitness-/Startelf-Formel), NICHT aus einem im Entry-Dict gespeicherten `doc_id`-Feld gelesen (siehe Global Constraints). Prüfen: `sed -n '/def upsert_history_entries/,/^def /p' src/firestore_db.py`. Falls die tatsächliche Signatur keinen `doc_id_fn`-Parameter hat (z.B. weil eine andere/spätere Version von Phase A ihn wieder entfernt hätte): das ist mit `player_news_log`s Mehrfach-Artikel-pro-Tag-Fall NICHT kompatibel (Artikel würden sich unter dem Default-Key gegenseitig überschreiben) — in diesem Fall Phase A's `upsert_history_entries` zuerst um den `doc_id_fn`-Parameter ergänzen, bevor mit Step 1 fortgefahren wird.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_news_sentiment.py`, Imports ergänzen und am Ende der Datei einfügen:

```python
from unittest.mock import MagicMock, patch

from src.news_sentiment import (
    _build_query,
    _max_workers,
    _players_from_snapshot,
    classify_sentiment,
    collect_news_sentiment,
    fetch_news_for_player,
    run_news_sentiment_ingestion,
)


class PlayersFromSnapshotTests(unittest.TestCase):
    def test_extracts_player_id_name_team_name_from_players_map(self):
        snapshot = {"players": {
            "p1": {"name": "Krauss", "team_name": "Bremen", "status_code": 0},
            "p2": {"name": "Mueller", "team_name": "Muenchen", "status_code": 1},
        }}
        result = _players_from_snapshot(snapshot)
        self.assertEqual(len(result), 2)
        self.assertIn({"player_id": "p1", "name": "Krauss", "team_name": "Bremen"}, result)
        self.assertIn({"player_id": "p2", "name": "Mueller", "team_name": "Muenchen"}, result)

    def test_none_snapshot_returns_empty_list(self):
        self.assertEqual(_players_from_snapshot(None), [])

    def test_snapshot_without_players_key_returns_empty_list(self):
        self.assertEqual(_players_from_snapshot({}), [])


class RunNewsSentimentIngestionTests(unittest.TestCase):
    @patch("src.news_sentiment.firestore_db.upsert_history_entries")
    @patch("src.news_sentiment.collect_news_sentiment")
    @patch("src.news_sentiment.firestore_db.get_dashboard_snapshot")
    @patch("src.news_sentiment.firestore_db.connect")
    def test_writes_collected_entries_when_firestore_enabled(self, mock_connect, mock_get_snapshot, mock_collect, mock_upsert):
        mock_get_snapshot.return_value = {"players": {"p1": {"name": "Krauss", "team_name": "Bremen"}}}
        mock_collect.return_value = [{"article_hash": "abc123", "date": "2026-08-02", "player_id": "p1"}]

        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = run_news_sentiment_ingestion()

        mock_upsert.assert_called_once()
        call_args = mock_upsert.call_args
        self.assertEqual(call_args.args, (mock_connect.return_value, "player_news_log", mock_collect.return_value))
        doc_id_fn = call_args.kwargs["doc_id_fn"]
        self.assertEqual(doc_id_fn({"date": "2026-08-02", "player_id": "p1", "article_hash": "abc123"}), "2026-08-02_p1_abc123")
        self.assertEqual(result, {"players_checked": 1, "entries_written": 1})

    @patch("src.news_sentiment.firestore_db.connect")
    def test_skips_without_firestore_enabled(self, mock_connect):
        with patch.dict(os.environ, {}, clear=True):
            result = run_news_sentiment_ingestion()

        mock_connect.assert_not_called()
        self.assertEqual(result, {"players_checked": 0, "entries_written": 0})

    @patch("src.news_sentiment.collect_news_sentiment")
    @patch("src.news_sentiment.firestore_db.get_dashboard_snapshot")
    @patch("src.news_sentiment.firestore_db.connect")
    def test_no_players_in_snapshot_skips_collection(self, mock_connect, mock_get_snapshot, mock_collect):
        mock_get_snapshot.return_value = {"players": {}}

        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = run_news_sentiment_ingestion()

        mock_collect.assert_not_called()
        self.assertEqual(result, {"players_checked": 0, "entries_written": 0})

    @patch("src.news_sentiment.firestore_db.upsert_history_entries")
    @patch("src.news_sentiment.collect_news_sentiment")
    @patch("src.news_sentiment.firestore_db.get_dashboard_snapshot")
    @patch("src.news_sentiment.firestore_db.connect")
    def test_firestore_write_failure_is_caught_not_raised(self, mock_connect, mock_get_snapshot, mock_collect, mock_upsert):
        mock_get_snapshot.return_value = {"players": {"p1": {"name": "Krauss", "team_name": "Bremen"}}}
        mock_collect.return_value = [{"article_hash": "abc123", "date": "2026-08-02", "player_id": "p1"}]
        mock_upsert.side_effect = RuntimeError("Firestore down")

        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = run_news_sentiment_ingestion()

        self.assertEqual(result, {"players_checked": 1, "entries_written": 1})
```

`import os` ist bereits seit Task 3 am Dateikopf vorhanden.

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_news_sentiment.PlayersFromSnapshotTests tests.test_news_sentiment.RunNewsSentimentIngestionTests -v`
Expected: FAIL (`ImportError: cannot import name '_players_from_snapshot'`)

- [ ] **Step 3: Implementierung**

In `src/news_sentiment.py`, Import ergänzen (nach den bestehenden Third-Party-Imports):

```python
from src import firestore_db
```

Am Ende der Datei einfügen:

```python
def _players_from_snapshot(snapshot: dict | None) -> list[dict]:
    """Wandelt dashboard_snapshot/latest's players-Map (player_id ->
    {name, team_name, ...}) in die von collect_news_sentiment() erwartete
    flache Liste um - liest ausschliesslich name/team_name, alle anderen
    Felder der Map (status_code, market_value, ...) werden hier nicht
    gebraucht. None/fehlende players-Map (Cold Start, dashboard_snapshot/
    latest noch nie geschrieben) gibt eine leere Liste zurueck, kein
    Crash."""
    if not snapshot:
        return []
    players_map = snapshot.get("players", {})
    return [
        {"player_id": pid, "name": data.get("name"), "team_name": data.get("team_name")}
        for pid, data in players_map.items()
    ]


def run_news_sentiment_ingestion() -> dict:
    """Oeffentlicher Entry-Point fuer den eigenstaendigen
    player-news-sentiment-Workflow (siehe
    .github/workflows/player-news-sentiment.yml). Liest
    dashboard_snapshot/latest (read-only, kein neuer Kickbase-API-Call,
    siehe Design-Spec 'Scheduling'), sammelt Sentiment fuer alle Spieler
    und schreibt nach player_news_log. Firestore-Schreibfehler werden
    abgefangen (Warnung, kein Crash) - Modell-Ladefehler in
    collect_news_sentiment()/germansentiment werden bewusst NICHT
    abgefangen, sollen den Workflow-Schritt sichtbar fehlschlagen lassen
    (siehe Design-Spec 'Fehlerfaelle': ein Teilerfolg ist hier nicht
    sinnvoll moeglich, das Modell wird fuer ALLE Spieler gebraucht)."""
    if not os.environ.get("FIRESTORE_ENABLED"):
        print("Warnung: FIRESTORE_ENABLED nicht gesetzt, Sentiment-Lauf uebersprungen.", file=sys.stderr)
        return {"players_checked": 0, "entries_written": 0}

    fs_client = firestore_db.connect()
    snapshot = firestore_db.get_dashboard_snapshot(fs_client)
    players = _players_from_snapshot(snapshot)
    if not players:
        print("Warnung: dashboard_snapshot/latest liefert keine Spieler, Sentiment-Lauf uebersprungen.", file=sys.stderr)
        return {"players_checked": 0, "entries_written": 0}

    entries = collect_news_sentiment(players)
    try:
        firestore_db.upsert_history_entries(
            fs_client, "player_news_log", entries,
            doc_id_fn=lambda e: f"{e['date']}_{e['player_id']}_{e['article_hash']}",
        )
    except Exception as exc:  # sekundaerer, eigenstaendiger Workflow - darf nicht crashen
        print(f"Warnung: player_news_log-Schreibzugriff fehlgeschlagen: {exc}", file=sys.stderr)

    return {"players_checked": len(players), "entries_written": len(entries)}


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    result = run_news_sentiment_ingestion()
    print(f"Spieler geprueft: {result['players_checked']}, Sentiment-Eintraege geschrieben: {result['entries_written']}")
```

- [ ] **Step 4: Kompletten Backend-Testlauf verifizieren**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS (kompletter Backend-Testlauf, nicht nur die neue Klasse — Regressionscheck)

- [ ] **Step 5: Commit**

```bash
git add src/news_sentiment.py tests/test_news_sentiment.py
git commit -m "news_sentiment: Firestore-Anbindung + Entry-Point run_news_sentiment_ingestion() ergaenzt"
```

---

## Task 6: Eigenständiger GitHub-Actions-Workflow

**Files:**
- Create: `.github/workflows/player-news-sentiment.yml`

**Interfaces:**
- Consumes: `run_news_sentiment_ingestion()` (Task 5) über `python -m src.news_sentiment`.
- Produces: nichts für spätere Tasks (letzter Task dieses Plans).

- [ ] **Step 1: Workflow-Datei anlegen**

`.github/workflows/player-news-sentiment.yml` neu anlegen:

```yaml
name: Player News Sentiment (taeglich, unabhaengig vom Dashboard-Cron)

on:
  schedule:
    # Taeglich 05:47 UTC - bewusst versetzt zum stuendlichen Light-Cron
    # (Minute 17, dashboard.yml) und zum Heavy-Marktwert-Cron (~19:04 UTC,
    # dashboard-marktwerte.yml), rein um GitHub-Actions-Ressourcen-
    # Ueberlappung zu vermeiden - kein funktionaler Zeitbezug zu Kickbase
    # noetig, dieser Lauf liest nur dashboard_snapshot/latest aus
    # Firestore, macht keinen eigenen Kickbase-API-Call (siehe
    # docs/superpowers/specs/2026-08-02-news-sentiment-design.md,
    # Abschnitt 'Scheduling').
    - cron: '47 5 * * *'
  workflow_dispatch: {}

permissions:
  contents: read

jobs:
  player-news-sentiment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Write Firebase service account key
        run: echo '${{ secrets.FIREBASE_SERVICE_ACCOUNT }}' > "$RUNNER_TEMP/firebase-service-account.json"

      - name: News fetchen, Sentiment klassifizieren, player_news_log schreiben
        env:
          FIRESTORE_ENABLED: '1'
          GOOGLE_APPLICATION_CREDENTIALS: ${{ runner.temp }}/firebase-service-account.json
        run: python -m src.news_sentiment
```

Hinweis: dieser Workflow braucht — anders als `dashboard.yml`/`dashboard-marktwerte.yml` — KEINE `KICKBASE_EMAIL`/`KICKBASE_PASSWORD`/`KICKBASE_LEAGUE_ID`-Secrets, da `run_news_sentiment_ingestion()` ausschließlich `dashboard_snapshot/latest` aus Firestore liest, keinen eigenen Kickbase-Login macht.

- [ ] **Step 2: YAML-Syntax verifizieren**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/player-news-sentiment.yml'))" && echo OK`
Expected: `OK` (kein `yaml.YAMLError`)

- [ ] **Step 3: Kompletten Backend-Testlauf ein letztes Mal verifizieren**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/player-news-sentiment.yml
git commit -m "player-news-sentiment: eigenstaendigen taeglichen Workflow ergaenzt"
```

---

## Verification (gesamt)

- [ ] `python3 -m unittest discover -s tests` grün nach jedem Task.
- [ ] Nach Task 3: `pip install -r requirements.txt` einmal erfolgreich durchgelaufen (torch/transformers, mehrere hundert MB).
- [ ] Nach Task 6: optional lokaler Smoke-Test `python3 -m src.news_sentiment` (Sandbox hat laut Memory echten Firestore-Zugriff) — erste echte BERT-Modell-Ladezeit abschätzen, prüfen, dass `player_news_log` tatsächlich Dokumente bekommt und die Doc-Ids dem `{date}_{player_id}_{article_hash}`-Schema folgen.
- [ ] Push nach jedem Task erlaubt, wenn Tests grün (bestehende Projekt-Policy).
- [ ] Nach Abschluss aller 6 Tasks: HANDOFF.md aktualisieren (neue Collection `player_news_log`, neuer eigenständiger Workflow, Cold-Start-Hinweis dass Phase C erst nach einigen Tagen/Wochen Datenaufbau sinnvoll ist).

## Self-Review

- **Spec-Abdeckung:** RSS-Fetch (Task 2), Sentiment-Klassifikation (Task 3), Orchestrierung inkl. Parallelisierung (Task 4), Firestore-Schreiben über Phase A's generalisierten Writer (Task 5), eigenständiger Workflow (Task 6) — alle Abschnitte des Design-Spec (`Architektur`, `Scheduling`, `Umfang`, `Datenfluss`, `Fehlerfälle`, `Testing`, `Betroffene Dateien`) haben einen entsprechenden Task.
- **Zwei konkrete, während der Recherche gefundene Korrekturen am Design-Spec eingearbeitet (nicht nur Signatur-Nits):** (1) Google News RSS liefert keinen echten Snippet-Text (live per WebFetch verifiziert) — `snippet`-Feld wird stattdessen mit dem Verlagsnamen aus `<source>` befüllt, Sentiment-Input nutzt nur `title`. (2) Der Doc-Id-Konflikt zwischen Phase A's `{date}_{player_id}`-Formel und Phase B's benötigtem `{date}_{player_id}_{article_hash}` — **Korrektur nach Phase A's tatsächlicher Fertigstellung (2026-08-02):** ursprünglich ging dieser Plan von einem expliziten `doc_id`-Feld im entry-Dict aus; Phase A's echte Implementierung löst das statt dessen über einen überschreibbaren `doc_id_fn`-Parameter auf `upsert_history_entries`. Alle betroffenen Stellen (Global Constraints, Task 4's Interface/Tests/Implementierung, Task 5's Step 0/Tests/Implementierung) wurden entsprechend korrigiert, gefunden im finalen Whole-Branch-Review von Phase A.
- **Platzhalter-Scan:** keine TBD/TODO, jeder Code-Block enthält vollständigen, lauffähigen Code, jeder Testschritt hat echte Assertions.
- **Typ-/Namens-Konsistenz geprüft:** `fetch_news_for_player()` (Task 2) liefert `{title, snippet, link, pub_date}` — `collect_news_sentiment()` (Task 4) liest exakt diese vier Keys. `classify_sentiment()` (Task 3) liefert `{label, score}` — Task 4 verwendet exakt diese beiden Keys für `sentiment_label`/`sentiment_score`. `_players_from_snapshot()` (Task 5) liefert `{player_id, name, team_name}` — `collect_news_sentiment()` (Task 4) liest exakt diese drei Keys (`p["player_id"]`, `p["name"]`, `p.get("team_name")`).
- **YAGNI-Entscheidungen dokumentiert:** kein Rate-Limiting/Backoff (Design-Spec: nur bei beobachtetem Bedarf nachrüsten), kein dedizierter `_max_workers()`-Test über das übliche Maß hinaus (Konsistenz mit `market_predictor.py`, das `_max_workers()` ebenfalls nicht separat testet — hier trotzdem zwei einfache Tests ergänzt, da die Env-Var neu ist und ein Basis-Smoke-Test billig ist), kein `get_history("player_news_log")`-Aufruf in Phase B (erst Phase C braucht Lesezugriff).
