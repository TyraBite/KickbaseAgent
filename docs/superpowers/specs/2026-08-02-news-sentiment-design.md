# News/Sentiment-Ingestion (Phase B: ML-Marktwert-Turning-Points) — Design

**Feedback-Quelle:** `feedback/current` Item `6b08e2cf`, Phase B von 3 (siehe `docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md` für Phase A und die Gesamt-Zerlegung). Ziel: automatisiert Nachrichten der letzten Tage pro Spieler sammeln, Sentiment ermitteln, als Rohdaten-Basis für Phase C (ML-Feature-Integration, eigene Spec).

**Globale Abhängigkeit: baut auf Phase A auf, muss NACH Phase A implementiert werden.** Phase A generalisiert `firestore_db.py`s History-Helper (`upsert_history_entries(client, collection, entries)`/`get_history(client, collection)`, ersetzen die bisherigen `fitness_history_log`-spezifischen Funktionen). Phase B nutzt exakt diese generalisierten Helper für eine neue Collection (`player_news_log`) — keine dritte Kopie derselben Batch-Write-Logik.

## Recherche-Ergebnis (2026-08-02, vor diesem Design geprüft)

Die ursprünglich im Feedback genannten Quellen sind **beide nicht nutzbar**:
- **Kicker.de**: `robots.txt` sperrt `ClaudeBot` und weitere AI-Crawler namentlich, zusätzlich expliziter `§44b UrhG`-Rechtsvorbehalt (Text-and-Data-Mining-Opt-Out) — rechtlicher Opt-Out, kein technisches Hindernis zum Umgehen.
- **Transfermarkt.de**: technisch nicht erreichbar (kompletter Fetch-Fehl beim Recherche-Versuch), passt zum bekannten Anti-Bot-Schutz (Cloudflare o.ä.).

**Akzeptierte Alternative (User-Entscheidung):** Google News RSS (`https://news.google.com/rss/search?q=...&hl=de&gl=DE`) — aggregiert, keine direkte Berührung der beiden gesperrten Seiten, liefert Headline+Snippet (kein Volltext — für Volltext müsste man dem Artikel-Link folgen und landet wieder beim selben Zugriffsproblem). **Headline+Snippet gilt als ausreichend für Sentiment-Zwecke** (User-Bestätigung).

**Sentiment-Methode (User-Entscheidung):** `germansentiment` (PyPI-Paket, wrapt `oliverguhr/german-sentiment-bert`, fertig trainiertes deutsches BERT-Sentiment-Modell) — einzige Option ohne eigenen Trainingsdatensatz-Aufwand. Zieht `torch`+`transformers` als neue Dependencies (mehrere hundert MB, bisher hatte das Backend keine Deep-Learning-Abhängigkeit) — akzeptiert, da CPU-Inferenz bei diesem Volumen (s.u.) unproblematisch ist und es kein laufendes Kostenproblem gibt (lokal, kein API-Call).

## Architektur

### Neues Modul: `src/news_sentiment.py`

```python
import datetime
import hashlib
import xml.etree.ElementTree as ET
import requests
from germansentiment import SentimentModel

NEWS_LOOKBACK_DAYS = 7
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"

def _build_query(player_name: str, team_name: str | None) -> str:
    """Spielername + Vereinsname zur Eindeutigkeit (reiner Nachname wie
    'Müller' waere sonst viel zu unspezifisch fuer sinnvolle Treffer)."""
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
    market_predictor._fetch_player_training_frame)."""
    ...

def classify_sentiment(model: "SentimentModel", texts: list[str]) -> list[dict]:
    """Batch-Klassifikation ueber germansentiment - gibt pro Text
    {label: 'positive'|'negative'|'neutral', ...} zurueck. Batch statt
    Einzelaufruf pro Artikel, da germansentiment.predict_sentiment() nativ
    Listen akzeptiert - spart Modell-Overhead pro Aufruf."""
    ...

def collect_news_sentiment(players: list[dict]) -> list[dict]:
    """Orchestriert: pro Spieler fetch_news_for_player(), dann alle
    gesammelten Artikel-Texte in EINEM Batch durch classify_sentiment()
    (nicht pro Spieler einzeln - Modell-Ladezeit faellt nur einmal an).
    Gibt eine flache Liste von Rohdaten-Dicts zurueck, bereit fuer
    firestore_db.upsert_history_entries(client, "player_news_log", ...).
    Parallelisiert die RSS-Fetches ueber ThreadPoolExecutor (gleiches Muster
    wie market_predictor._max_workers(), Netzwerk-IO-gebunden, das Sentiment-
    Modell selbst laeuft NICHT parallel - ein BERT-Modell mehrfach gleichzeitig
    zu laden waere reiner Speicher-Overhead ohne Nutzen bei dieser Batch-Groesse)."""
    ...
```

**Doc-Id-Schema:** `{date}_{player_id}_{article_hash}` (`article_hash` = kurzer Hash über den Artikel-Link, per `hashlib.sha1(link.encode()).hexdigest()[:12]`) — idempotent bei täglichem Rerun (derselbe Artikel taucht in den nächsten `NEWS_LOOKBACK_DAYS`-1 Tagen erneut in der RSS-Antwort auf, würde ohne Dedup mehrfach als "neue" Nachricht gezählt und Phase C's spätere Aggregation verzerren). Firestore-Dokument-Felder: `player_id`, `date` (Tag DIESES Laufs, nicht `pub_date` des Artikels — Konsistenz mit dem Diff-Log-Muster aus Phase A, wo `date` ebenfalls der Lauf-Tag ist), `pub_date` (Original-Veröffentlichungsdatum des Artikels, separat gespeichert), `headline`, `snippet`, `link`, `sentiment_label`, `sentiment_score`.

### Scheduling: neuer, eigener GitHub-Actions-Workflow

`.github/workflows/player-news-sentiment.yml`, 1x/Tag, **unabhängig vom bestehenden Dashboard-Cron** (`dashboard.yml`/`dashboard-marktwerte.yml`) — gleiche Trennungs-Philosophie wie der bestehende Light/Heavy-Split: dieser Lauf hat andere Fehler-/Timing-Charakteristik (Netzwerk-Fetches gegen eine externe RSS-Quelle + BERT-Inferenz über ~450 Spieler, potenziell mehrere Minuten Laufzeit) und darf den kritischen `dashboard_snapshot`-Write nicht mit zusätzlichem Zeitdruck/Fehlerrisiko belasten. Liest `all_players` NICHT selbst neu von der Kickbase-API (unnötiger zusätzlicher API-Call) — nutzt stattdessen `dashboard_snapshot/latest`s bereits vorhandene `players`-Map als Namens-/Team-Quelle (read-only, dieselbe Collection, die Light-Cron sowieso stündlich aktualisiert).

### Umfang

**Alle Spieler** aus `dashboard_snapshot/latest`s `players`-Map (~450, dasselbe Universum wie `market_predictor.py`s Trainingskorpus) — nicht nur eigener Kader/Wunschkader, da das Ziel eine generell bessere Prognose ist, nicht nur für die eigene Liga-Auswahl relevant.

## Datenfluss

```
dashboard_snapshot/latest.players (read-only, bereits vorhanden)
  │
  └─ pro Spieler: fetch_news_for_player(name, team_name)
       → Google News RSS, letzte 7 Tage, parallelisiert (ThreadPoolExecutor)
       │
       └─ alle gesammelten Artikel-Texte in EINEM Batch
            → classify_sentiment() (germansentiment, BERT, CPU)
            │
            └─ firestore_db.upsert_history_entries(client, "player_news_log", entries)
                 (wiederverwendet Phase A's generalisierten Batch-Writer,
                 KEIN neuer dritter Firestore-Helper)
```

## Fehlerfälle

- **Google News RSS liefert nichts/Fehler für einen Spieler** — abgefangen, leere Liste, Lauf geht mit den übrigen Spielern weiter (kein Crash, gleiches Muster wie `_fetch_player_training_frame`).
- **`germansentiment`-Modell-Ladefehler** (z.B. Download der Modell-Gewichte schlägt in GitHub Actions fehl) — wird den kompletten Lauf betreffen, da das Modell für alle Spieler gebraucht wird; in diesem Fall bricht der Workflow-Schritt ab (kein sinnvoller Teil-Erfolg möglich) — Workflow-Fehlschlag ist hier akzeptabel, betrifft nicht den kritischen Dashboard-Pfad (eigener, unabhängiger Workflow).
- **Firestore-Schreibfehler** — abgefangen wie bei allen sekundären Features in diesem Projekt, Warnung auf stderr, kein Crash. Da dieser Workflow ohnehin komplett unabhängig vom Dashboard läuft, gibt es hier keinen "kritischen Write", der besonders geschützt werden müsste — ein kompletter Fehlschlag dieses Laufs bedeutet nur "heute keine neuen News-Daten", nichts Schlimmeres.
- **Firestore-Write-Volumen** (Vorsicht geboten, siehe Quota-Vorfall vom 28.07. in `HANDOFF.md`): ~450 Spieler × realistisch wenige Artikel pro Spieler pro Tag (die meisten Tage: 0-1 relevante Treffer pro Spieler, gelegentliche Ausreißer bei großen Meldungen) — deutlich unter dem 20.000-Writes/Tag-Limit des Spark-Free-Tiers, aber `_write_in_batches` (max. 500 Ops/Batch, bereits vorhanden) wird trotzdem verwendet statt Einzel-Writes, aus Prinzip.
- **Google-News-Rate-Limiting** — bei 450 sequentiellen Requests/Tag ohne jede Drosselung ist ein Blocken durch Google denkbar. Parallelisierung über `ThreadPoolExecutor` mit begrenzter Worker-Zahl (analog `MARKET_PREDICTOR_MAX_WORKERS`, Default 8) statt unbegrenzter Parallelität — kein explizites Rate-Limiting/Backoff in diesem ersten Entwurf, da unklar ohne echten Testlauf, ob es überhaupt nötig ist. Falls sich beim ersten echten Lauf Blocking zeigt, ist das ein Nachbesserungspunkt (nicht vorab spekulativ einbauen).

## Testing

- `_build_query`: reine Funktion, testbar ohne Netzwerk — Namens-/Team-Kombination korrekt zusammengesetzt.
- `fetch_news_for_player`: RSS-XML-Parsing als reine Funktion testbar, indem eine Beispiel-RSS-Antwort (String-Fixture) statt eines echten HTTP-Calls verarbeitet wird — `requests.get()` selbst wird gemockt (etabliertes Muster in diesem Projekt, z.B. `tests/test_dashboard_export.py`).
- `classify_sentiment`: `germansentiment` selbst wird NICHT unit-getestet (fremdes, fertig trainiertes Modell) — nur, dass die Funktion die Bibliothek korrekt aufruft und ihr Rückgabeformat korrekt weiterverarbeitet (Mock des Modell-Objekts).
- `collect_news_sentiment`: Integrationstest mit gemocktem `fetch_news_for_player` + gemocktem Sentiment-Modell, prüft die Doc-Id-Generierung (`{date}_{player_id}_{article_hash}`) und dass leere Ergebnisse pro Spieler den Gesamtlauf nicht abbrechen.

## Betroffene Dateien

- Create: `src/news_sentiment.py`
- Create: `tests/test_news_sentiment.py`
- Create: `.github/workflows/player-news-sentiment.yml`
- Modify: `requirements.txt` (neu: `germansentiment`)
- Modify: `src/firestore_db.py` NUR falls Phase A's `upsert_history_entries`/`get_history` noch nicht existieren, wenn Phase B umgesetzt wird (sollte nicht der Fall sein, da A vor B geplant ist — siehe globale Abhängigkeit oben)

## Out of Scope (bewusst)

- **Phase C** (Sentiment-Daten als ML-Feature in `market_predictor.py` einbauen) — eigene, dritte Spec, liest `player_news_log` genauso wie Phase C für Startelf-Status `starting_rank_history_log` lesen wird.
- Keine Frontend-Anzeige (User-Entscheidung, wie bei Phase A: rein ML-intern).
- Kein Volltext-Abruf der verlinkten Artikel — Headline+Snippet gilt als ausreichend (User-Bestätigung).
- Kein Rate-Limiting/Backoff-Mechanismus vorab — nur bei tatsächlich beobachtetem Blocking nachrüsten.
- Keine Aggregation/Zeitfenster-Feature-Berechnung (z.B. "durchschnittliches Sentiment letzte 7 Tage") — das ist Phase C, dieses Dokument liefert nur die Rohdaten-Sammlung.
