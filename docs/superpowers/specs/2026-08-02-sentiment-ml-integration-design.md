# Sentiment-ML-Integration (Phase C: ML-Marktwert-Turning-Points) — Design

**Feedback-Quelle:** `feedback/current` Item `6b08e2cf`, Phase C von 3 (siehe `docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md` für Phase A/Gesamt-Zerlegung, `docs/superpowers/specs/2026-08-02-news-sentiment-design.md` für Phase B). Ziel: die in Phase B gesammelten Rohdaten (`player_news_log`) zu Trainings-Features für `market_predictor.py` verdichten.

**Globale Abhängigkeit: baut auf Phase B auf, muss NACH Phase B implementiert werden.** Ohne `player_news_log`-Daten liefert dieses Feature nur Cold-Start-Platzhalter — technisch trotzdem umsetzbar, aber ohne jeden Wert vor Phase B's Launch.

**Kleinerer Umfang als ursprünglich erwartet:** die Startelf-Status-Feature-Integration (`days_since_last_starting_rank_change`/`starting_rank_change_count_90d`) ist bereits Teil von Phase A selbst (dort direkt in `FEATURES` aufgenommen) — Phase C behandelt ausschließlich die Sentiment-Seite.

## Architektur

### `src/market_predictor.py`

Neue reine Funktion, analog `_change_recency_features()` aus Phase A, aber mit Fenster-Aggregation statt Recency-Berechnung (unterschiedliche Semantik, daher eigene Funktion, keine erzwungene Vereinheitlichung mit `_change_recency_features`):

```python
SENTIMENT_LABEL_SCORE = {"positive": 1, "neutral": 0, "negative": -1}
SENTIMENT_WINDOW_DAYS = 7

def _sentiment_features_as_of(articles: list[dict], as_of_date: datetime.date) -> dict:
    """articles: EIN Spielers Eintraege aus player_news_log (jeweils
    {'pub_date': 'YYYY-MM-DD', 'sentiment_label': 'positive'|'neutral'|'negative', ...}).
    Nur Artikel mit pub_date im [as_of_date - SENTIMENT_WINDOW_DAYS, as_of_date]-Fenster
    fliessen ein - kein Lookahead in die Zukunft dieser Trainings-Zeile (identisches
    Prinzip wie _change_recency_features, hier aber ueber ein rollierendes Fenster
    statt "Tage seit letztem Ereignis", da es bei Nachrichten kein einzelnes
    diskretes 'Ereignis' wie einen Status-Wechsel gibt, sondern eine variable
    Anzahl Artikel pro Tag)."""
    cutoff = as_of_date - datetime.timedelta(days=SENTIMENT_WINDOW_DAYS)
    relevant = [
        a for a in articles
        if cutoff < datetime.date.fromisoformat(a["pub_date"]) <= as_of_date
    ]
    if not relevant:
        return {"avg_sentiment_7d": 0, "news_volume_7d": 0}
    avg_sentiment = sum(SENTIMENT_LABEL_SCORE[a["sentiment_label"]] for a in relevant) / len(relevant)
    return {"avg_sentiment_7d": avg_sentiment, "news_volume_7d": len(relevant)}
```

**Cold-Start-Platzhalter `0`/`0`** (nicht `9999` wie bei den Recency-Features) — semantisch passend: "kein Sentiment-Signal" ist neutral (0), nicht "unbekannt seit sehr langer Zeit". Für jede Trainings-Zeile vor Phase B's Launch-Datum ist das automatisch der Fall (keine Artikel vorhanden) — erwartet, kein Bug, gleiche Einschränkung wie bei den Fitness-/Startelf-Features.

**Neue `FEATURES`-Einträge:** `"avg_sentiment_7d"`, `"news_volume_7d"`.

**Laden der Rohdaten:** neue `_load_news_events_by_player()`, analog zu Phase A's `_load_change_events_by_player("starting_rank_history_log")`, aber liest `player_news_log` (per `firestore_db.get_history(client, "player_news_log")` — Phase B's Collection nutzt denselben generalisierten Reader wie Phase A, siehe dortige Spec). Gruppiert nach `player_id`, wie bei den Fitness-/Startelf-Events.

**`_fetch_player_training_frame()`** bekommt einen weiteren Parameter (`news_events_by_player`), berechnet pro Trainings-Zeile `_sentiment_features_as_of(events, ts.date())` genau wie die bestehenden Fitness-/Startelf-Feature-Spalten.

## Datenfluss

```
player_news_log (Phase B, Firestore)
  │
  └─ _load_news_events_by_player()  [einmal pro Trainingslauf, gruppiert nach player_id]
       │
       └─ pro Trainings-Zeile (in _fetch_player_training_frame):
            _sentiment_features_as_of(events, ts.date())
              → avg_sentiment_7d, news_volume_7d
              → zwei neue Spalten in FEATURES
```

## Fehlerfälle

- **`player_news_log`-Lesefehler** (Firestore down/Quota) — abgefangen, leeres Dict, jeder Spieler bekommt die Cold-Start-Platzhalter (`0`/`0`) für diesen Lauf, kein Crash (identisches Resilienz-Muster wie `_load_fitness_events_by_player`/Phase A's `_load_change_events_by_player`).
- **`sentiment_label` mit unbekanntem Wert** (sollte nicht vorkommen, `germansentiment` liefert laut Phase-B-Spec nur die drei bekannten Label) — falls doch, würde `SENTIMENT_LABEL_SCORE[...]` einen `KeyError` werfen; das ist bewusst NICHT stillschweigend abgefangen (ein unbekanntes Label ist ein echter Datenfehler in Phase B, der auffallen soll, kein Fall, der als "einfach 0 werten" verschluckt werden sollte).
- **Kein Backfill möglich** — wie bei allen History-basierten Features in diesem Projekt (Fitness, Startelf, jetzt Sentiment): Kickbase/Google News liefern keine rückwirkende Zeitreihe, die Historie wächst nur ab dem Tag der jeweiligen Feature-Einführung.

## Testing

`_sentiment_features_as_of`: reine Funktion, direkt testbar ohne Firestore/Netzwerk.
- Cold-Start (keine Artikel): `{"avg_sentiment_7d": 0, "news_volume_7d": 0}`.
- Nur positive Artikel im Fenster → `avg_sentiment_7d == 1`.
- Gemischt positiv/negativ → korrekter Durchschnitt.
- Artikel außerhalb des 7-Tage-Fensters (zu alt) → werden nicht mitgezählt.
- Artikel mit `pub_date > as_of_date` (Zukunft relativ zur Trainings-Zeile) → werden nicht mitgezählt (Lookahead-Schutz, wichtigster Testfall — Regressionsschutz analog zum bereits bestehenden Lookahead-Schutz bei den Fitness-Features).

`_load_news_events_by_player`: Lesefehler-Pfad testbar wie das bestehende Pendant (`_load_fitness_events_by_player`) — leeres Dict bei Exception, kein Crash.

## Betroffene Dateien

- Modify: `src/market_predictor.py` (`_sentiment_features_as_of()`, `_load_news_events_by_player()`, zwei neue `FEATURES`-Einträge, `_fetch_player_training_frame()` erweitert)
- Modify: `tests/test_market_predictor.py` (neue Testfälle)

## Out of Scope (bewusst)

- **Modell-Neu-Tuning** — bereits als eigener Backlog-Punkt im `HANDOFF.md` getrackt ("Modelle nochmal tunen sobald genug Daten da sind"), wird durch diese Spec nicht ausgelöst — erst sinnvoll, sobald A+B+C's Features über Wochen/Monate echte Historie gesammelt haben (identischer Vorbehalt wie bei den Fitness-Features).
- **Konfidenz-gewichtetes Sentiment** (z.B. `sentiment_score` statt nur `sentiment_label` nutzen, falls `germansentiment` eine Wahrscheinlichkeit mitliefert) — bewusst MVP-Ansatz mit einfacher Label-Zuordnung (+1/0/-1), keine vorzeitige Verfeinerung ohne echte Evidenz, dass die einfache Version nicht ausreicht.
- Keine Frontend-Anzeige (durchgängige Entscheidung über alle 3 Phasen).
