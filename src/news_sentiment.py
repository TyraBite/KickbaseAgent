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
