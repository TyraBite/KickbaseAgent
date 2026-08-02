# Sentiment-ML-Integration (Phase C: ML-Marktwert-Turning-Points) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die in Phase B gesammelten News-Sentiment-Rohdaten (`player_news_log`) zu zwei neuen Trainings-Features (`avg_sentiment_7d`, `news_volume_7d`) für `market_predictor.py`s tägliche ML-Marktwertprognose verdichten.

**Architecture:** Reine Feature-Funktion (`_sentiment_features_as_of()`, rollierendes 7-Tage-Fenster über Artikel-Sentiment) plus ein Loader (`_load_news_events_by_player()`), der einmal pro Trainingslauf `player_news_log` aus Firestore liest und nach `player_id` gruppiert — 1:1 dasselbe Muster wie die bestehende Fitness-Historie-Pipeline (`_fitness_features_as_of()`/`_load_fitness_events_by_player()`), aber mit Fenster-Aggregation statt "Tage seit letztem Ereignis"-Berechnung (andere Semantik, deshalb eigene Funktion). `_fetch_player_training_frame()` bekommt einen weiteren Parameter und berechnet die beiden neuen Spalten pro Trainings-Zeile, genau wie die bestehenden Fitness-Feature-Spalten.

**Tech Stack:** Python, pandas, Firestore (`google-cloud-firestore`, über `src/firestore_db.py`), `unittest`.

## Global Constraints

- **Abhängigkeit von Phase A** (`docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md`): dieses Plan nutzt den dort generalisierten Firestore-Reader `firestore_db.get_history(client, collection)` (ersetzt `firestore_db.get_fitness_history(client)`). Phase A muss implementiert sein, bevor dieser Plan ausgeführt wird.
- **Abhängigkeit von Phase B** (`docs/superpowers/specs/2026-08-02-news-sentiment-design.md`): dieses Plan liest die dort definierte Collection `player_news_log` mit dem Dokumentschema `player_id`, `date`, `pub_date`, `headline`, `snippet`, `link`, `sentiment_label`, `sentiment_score`. Phase B muss implementiert sein und tatsächlich Daten schreiben, bevor dieser Plan sinnvolle Werte liefert.
- **Kein Backfill möglich** — wie bei allen History-basierten Features in diesem Projekt (Fitness, Startelf, jetzt Sentiment): weder Kickbase noch Google News liefern eine rückwirkende Zeitreihe. Jede Trainings-Zeile vor Phase B's tatsächlichem Launch-Datum bekommt automatisch den Cold-Start-Platzhalter — **das Feature ist erst nach Wochen/Monaten realer Datensammlung durch Phase A+B überhaupt aussagekräftig, nicht sofort nach diesem Plan.** Kein Bug, gleiche Einschränkung wie bei den Fitness-Features.
- **Cold-Start-Platzhalter ist `0`/`0`**, NICHT `9999` wie bei den Recency-Features (`FITNESS_NO_HISTORY_DAYS`) — semantisch passend: "kein Sentiment-Signal" ist neutral (0), nicht "unbekannt seit sehr langer Zeit".
- `_sentiment_features_as_of()` ist eine EIGENE Funktion, NICHT in `_fitness_features_as_of()` (bzw. Phase A's generalisierte Nachfolgefunktion) hineingepresst — unterschiedliche Aggregationssemantik (rollierendes Fenster über eine variable Artikelzahl/Tag statt Tage-seit-letztem-diskreten-Ereignis).
- Ein unbekannter `sentiment_label`-Wert löst bewusst einen `KeyError` aus (kein `.get()` mit Default) — ein solcher Wert wäre ein echter Datenfehler in Phase B, der auffallen soll, kein Fall, der stillschweigend als "0 werten" verschluckt wird.
- Kein Modell-Neu-Tuning durch diesen Plan ausgelöst — bereits als eigener Backlog-Punkt in `HANDOFF.md` getrackt, erst sinnvoll sobald A+B+C über Wochen/Monate echte Historie gesammelt haben.
- Keine Frontend-Anzeige (durchgängige Entscheidung über alle 3 Phasen).
- **Cross-Plan-Risiko:** Weder der Phase-A- noch der Phase-B-Implementierungsplan existierten zum Zeitpunkt der Erstellung dieses Plans (nur deren Design-Specs) — die konkreten Code-Ausschnitte unten spiegeln den Stand von `src/market_predictor.py`/`src/firestore_db.py` VOR Phase A/B wider. Task 2 verlangt deshalb explizit, die aktuellen Funktionssignaturen frisch nachzulesen, bevor Code geändert wird (siehe Hinweis dort).
- TDD durchgehend: Test zuerst, dann Implementierung. Backend-Verifikation nach jedem Task: `python3 -m unittest discover -s tests`.
- Aus jedem Task: `git add` nur die in diesem Task geänderten Dateien, dann committen (Push erlaubt, wenn Tests grün — bestehende Projekt-Policy).

---

## Task 1: Reine Feature-Funktion `_sentiment_features_as_of()`

**Files:**
- Modify: `src/market_predictor.py`
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Consumes: nichts aus anderen Tasks (reine Funktion, unabhängig testbar).
- Produces: `_sentiment_features_as_of(articles: list[dict], as_of_date: datetime.date) -> dict` mit Keys `avg_sentiment_7d: float`, `news_volume_7d: int`. Konstanten `SENTIMENT_LABEL_SCORE = {"positive": 1, "neutral": 0, "negative": -1}`, `SENTIMENT_WINDOW_DAYS = 7`. `articles`-Elemente haben mindestens `{"pub_date": "YYYY-MM-DD", "sentiment_label": "positive"|"neutral"|"negative", ...}` (Format wie `player_news_log`-Dokumente aus Phase B) — Reihenfolge der Liste ist egal.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_market_predictor.py`, die bestehende `from src.market_predictor import (...)`-Klammer (Dateikopf) erweitern — `_sentiment_features_as_of,` direkt nach `_fitness_features_as_of,` und `SENTIMENT_WINDOW_DAYS,` direkt nach `FITNESS_NO_HISTORY_DAYS,` einfügen:

```python
from src.market_predictor import (
    _summarize_from_daily,
    _build_daily_accuracy_updates,
    _realized_by_model_from_daily,
    _trend_from_daily,
    _load_local_prediction_log,
    _load_recent_prediction_log,
    _append_todays_predictions,
    _save_prediction_log,
    _select_live_model,
    _infer_today,
    _performance_frame,
    _fitness_features_as_of,
    _sentiment_features_as_of,
    _fetch_player_training_frame,
    _load_fitness_events_by_player,
    _engineer_features,
    FITNESS_NO_HISTORY_DAYS,
    SENTIMENT_WINDOW_DAYS,
    _train_and_evaluate,
    _walk_forward_backtest,
    _train_and_track_horizon,
    predict_market_value_changes,
    TARGET,
    TARGET_3D,
)
from src.market_predictor import backfill_prediction_log, _build_candidates
```

(Falls Phase A `_fitness_features_as_of`/`_load_fitness_events_by_player`/`FITNESS_NO_HISTORY_DAYS` bereits umbenannt hat, z.B. zu `_change_recency_features`/`_load_change_events_by_player`/`NO_HISTORY_DAYS_PLACEHOLDER` — die entsprechenden Namen dieses Plans hier NICHT anfassen, nur die neuen `_sentiment_features_as_of`/`SENTIMENT_WINDOW_DAYS`-Imports ergänzen, unabhängig davon wie die Nachbar-Imports gerade heißen.)

Direkt nach der Klasse `FitnessFeaturesAsOfTests` (vor `LoadFitnessEventsByPlayerTests`) einfügen:

```python
class SentimentFeaturesAsOfTests(unittest.TestCase):
    def test_no_articles_returns_neutral_placeholder(self):
        result = _sentiment_features_as_of([], datetime.date(2026, 8, 2))
        self.assertEqual(result["avg_sentiment_7d"], 0)
        self.assertEqual(result["news_volume_7d"], 0)

    def test_only_positive_articles_averages_to_one(self):
        articles = [
            {"pub_date": "2026-08-01", "sentiment_label": "positive"},
            {"pub_date": "2026-07-30", "sentiment_label": "positive"},
        ]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertEqual(result["avg_sentiment_7d"], 1)
        self.assertEqual(result["news_volume_7d"], 2)

    def test_mixed_sentiment_averages_correctly(self):
        articles = [
            {"pub_date": "2026-08-01", "sentiment_label": "positive"},
            {"pub_date": "2026-08-01", "sentiment_label": "negative"},
            {"pub_date": "2026-07-31", "sentiment_label": "neutral"},
        ]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertEqual(result["avg_sentiment_7d"], 0)
        self.assertEqual(result["news_volume_7d"], 3)

    def test_article_older_than_window_is_excluded(self):
        as_of = datetime.date(2026, 8, 2)
        too_old = (as_of - datetime.timedelta(days=8)).isoformat()
        articles = [{"pub_date": too_old, "sentiment_label": "positive"}]
        result = _sentiment_features_as_of(articles, as_of)
        self.assertEqual(result["news_volume_7d"], 0)
        self.assertEqual(result["avg_sentiment_7d"], 0)

    def test_article_exactly_on_window_boundary_is_excluded(self):
        as_of = datetime.date(2026, 8, 2)
        boundary_date = (as_of - datetime.timedelta(days=SENTIMENT_WINDOW_DAYS)).isoformat()
        articles = [{"pub_date": boundary_date, "sentiment_label": "positive"}]
        result = _sentiment_features_as_of(articles, as_of)
        self.assertEqual(result["news_volume_7d"], 0)

    def test_article_published_after_as_of_date_is_excluded_lookahead_guard(self):
        as_of = datetime.date(2026, 8, 2)
        future_date = (as_of + datetime.timedelta(days=1)).isoformat()
        articles = [{"pub_date": future_date, "sentiment_label": "negative"}]
        result = _sentiment_features_as_of(articles, as_of)
        self.assertEqual(result["news_volume_7d"], 0)
        self.assertEqual(result["avg_sentiment_7d"], 0)

    def test_unknown_sentiment_label_raises_key_error(self):
        articles = [{"pub_date": "2026-08-01", "sentiment_label": "surprised"}]
        with self.assertRaises(KeyError):
            _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_market_predictor.SentimentFeaturesAsOfTests -v`
Expected: FAIL (`ImportError: cannot import name '_sentiment_features_as_of'`)

- [ ] **Step 3: Implementierung**

In `src/market_predictor.py`, im Konstanten-Block direkt nach `FITNESS_COUNT_WINDOW_DAYS = 90` (bzw. dessen Phase-A-Nachfolgekonstante, falls bereits umbenannt) einfügen:

```python
SENTIMENT_LABEL_SCORE = {"positive": 1, "neutral": 0, "negative": -1}
SENTIMENT_WINDOW_DAYS = 7
```

Direkt nach `_fitness_features_as_of()` (bzw. deren Phase-A-Nachfolgefunktion, direkt vor `_fetch_player_training_frame()`) einfügen:

```python
def _sentiment_features_as_of(articles: list[dict], as_of_date: datetime.date) -> dict:
    """articles: EIN Spielers Eintraege aus player_news_log (jeweils
    {'pub_date': 'YYYY-MM-DD', 'sentiment_label': 'positive'|'neutral'|'negative', ...}).
    Nur Artikel mit pub_date im (as_of_date - SENTIMENT_WINDOW_DAYS, as_of_date]-Fenster
    fliessen ein - kein Lookahead in die Zukunft dieser Trainings-Zeile (identisches
    Prinzip wie _fitness_features_as_of, hier aber ueber ein rollierendes Fenster
    statt "Tage seit letztem Ereignis", da es bei Nachrichten kein einzelnes
    diskretes 'Ereignis' wie einen Status-Wechsel gibt, sondern eine variable
    Anzahl Artikel pro Tag). Siehe
    docs/superpowers/specs/2026-08-02-sentiment-ml-integration-design.md.
    Absichtlich EIGENE Funktion statt Wiederverwendung der Recency-Feature-
    Funktion - andere Aggregationssemantik (Fenster-Durchschnitt statt
    Tage-seit-letztem-Ereignis)."""
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

- [ ] **Step 4: Tests laufen lassen, Erfolg bestätigen**

Run: `python3 -m unittest tests.test_market_predictor -v`
Expected: alle PASS

- [ ] **Step 5: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: reine Feature-Funktion _sentiment_features_as_of() ergaenzt"
```

---

## Task 2: Loader `_load_news_events_by_player()` + Verdrahtung in den ML-Corpus + `FEATURES`

**Files:**
- Modify: `src/market_predictor.py`
- Test: `tests/test_market_predictor.py`

**Interfaces:**
- Consumes: `firestore_db.get_history(client, collection)` (Phase A — vorausgesetzt bereits implementiert, siehe Global Constraints), `_sentiment_features_as_of()`/`SENTIMENT_WINDOW_DAYS` (Task 1).
- Produces: `_load_news_events_by_player() -> dict[str, list[dict]]`. Neuer Parameter `news_events_by_player: dict[str, list[dict]]` bei `_fetch_player_training_frame()` (letzter Positionsparameter) und `_build_corpus()` (letzter Positionsparameter). `FEATURES` enthält zwei neue Einträge `"avg_sentiment_7d"`, `"news_volume_7d"`.

**Wichtiger Hinweis vor diesem Task:** Die Code-Ausschnitte unten zeigen den Stand von `src/market_predictor.py` VOR Phase A (aktuell: ein einzelner `fitness_events_by_player`-Parameter bei `_fetch_player_training_frame()`/`_build_corpus()`, Funktion `_load_fitness_events_by_player()`, Reader `firestore_db.get_fitness_history()`). Da Phase A vor diesem Plan implementiert wird und dieselben Funktionen generalisiert (siehe `docs/superpowers/specs/2026-08-02-startelf-status-historie-design.md`), zuerst **frisch in `src/market_predictor.py` nachlesen**, wie `_fetch_player_training_frame()`, `_build_corpus()`, `backfill_prediction_log()` und `predict_market_value_changes()` zu diesem Zeitpunkt tatsächlich aussehen (z.B. zusätzlicher `starting_rank_events_by_player`-Parameter, oder ein zusammengefasstes `dict[str, dict[str, list[dict]]]` statt zwei einzelner Parameter — Phase A's eigener Plan entscheidet das). In jedem Fall: `news_events_by_player: dict[str, list[dict]]` wird als NEUER, zusätzlicher Parameter ans Ende der jeweiligen Parameterliste angehängt, unabhängig davon, wie Phase A die bestehenden Fitness-/Startelf-Parameter organisiert hat. Die folgenden Schritte gehen vom Vor-Phase-A-Stand aus — Parameter-Positionen ggf. entsprechend anpassen, die Grundlogik (ein weiterer Parameter, eine weitere `.apply(...)`-Berechnung, zwei weitere Spalten) bleibt in jedem Fall identisch.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_market_predictor.py`, die Import-Klammer aus Task 1 um `_load_news_events_by_player,` (direkt nach `_load_fitness_events_by_player,`) erweitern:

```python
from src.market_predictor import (
    _summarize_from_daily,
    _build_daily_accuracy_updates,
    _realized_by_model_from_daily,
    _trend_from_daily,
    _load_local_prediction_log,
    _load_recent_prediction_log,
    _append_todays_predictions,
    _save_prediction_log,
    _select_live_model,
    _infer_today,
    _performance_frame,
    _fitness_features_as_of,
    _sentiment_features_as_of,
    _fetch_player_training_frame,
    _load_fitness_events_by_player,
    _load_news_events_by_player,
    _engineer_features,
    FITNESS_NO_HISTORY_DAYS,
    SENTIMENT_WINDOW_DAYS,
    _train_and_evaluate,
    _walk_forward_backtest,
    _train_and_track_horizon,
    predict_market_value_changes,
    TARGET,
    TARGET_3D,
)
from src.market_predictor import backfill_prediction_log, _build_candidates
```

Direkt nach der Klasse `FetchPlayerTrainingFrameFitnessColumnsTests` (vor `EngineerFeatures3dTargetTests`) einfügen:

```python
class LoadNewsEventsByPlayerTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_groups_entries_by_player_id(self, mock_connect, mock_get):
        mock_get.return_value = [
            {"player_id": "p1", "pub_date": "2026-07-20", "sentiment_label": "positive"},
            {"player_id": "p1", "pub_date": "2026-07-25", "sentiment_label": "negative"},
            {"player_id": "p2", "pub_date": "2026-07-22", "sentiment_label": "neutral"},
        ]
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            result = _load_news_events_by_player()
        self.assertEqual(len(result["p1"]), 2)
        self.assertEqual(len(result["p2"]), 1)
        mock_get.assert_called_once_with(mock_connect.return_value, "player_news_log")

    def test_returns_empty_dict_without_firestore_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_load_news_events_by_player(), {})

    @patch("src.market_predictor.firestore_db.get_history")
    @patch("src.market_predictor.firestore_db.connect")
    def test_returns_empty_dict_on_firestore_error(self, mock_connect, mock_get):
        mock_get.side_effect = RuntimeError("Firestore down")
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            self.assertEqual(_load_news_events_by_player(), {})


class FetchPlayerTrainingFrameSentimentColumnsTests(unittest.TestCase):
    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_adds_sentiment_columns_computed_as_of_each_row_date(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({
            "date": pd.to_datetime(["2026-07-25", "2026-08-01"]),
            "mv": [10_000_000, 10_200_000],
        })
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])
        news_events_by_player = {
            "p1": [{"player_id": "p1", "pub_date": "2026-07-24", "sentiment_label": "positive"}],
        }

        result = _fetch_player_training_frame("tok", "l1", "c1", "p1", "t1", {}, news_events_by_player)

        self.assertEqual(list(result["avg_sentiment_7d"]), [1, 0])
        self.assertEqual(list(result["news_volume_7d"]), [1, 0])

    @patch("src.market_predictor._performance_frame")
    @patch("src.market_predictor._market_value_frame")
    def test_player_without_any_news_events_gets_neutral_placeholder(self, mock_mv_frame, mock_perf_frame):
        mock_mv_frame.return_value = pd.DataFrame({"date": pd.to_datetime(["2026-08-01"]), "mv": [10_000_000]})
        mock_perf_frame.return_value = pd.DataFrame(columns=["date", "md", "p", "mp", "mp_avg_3", "t1", "t2", "t1g", "t2g"])

        result = _fetch_player_training_frame("tok", "l1", "c1", "p_unknown", "t1", {}, {})

        self.assertEqual(list(result["avg_sentiment_7d"]), [0])
        self.assertEqual(list(result["news_volume_7d"]), [0])
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `python3 -m unittest tests.test_market_predictor.LoadNewsEventsByPlayerTests tests.test_market_predictor.FetchPlayerTrainingFrameSentimentColumnsTests -v`
Expected: FAIL (`ImportError: cannot import name '_load_news_events_by_player'` bzw. `TypeError: _fetch_player_training_frame() takes ... positional arguments but 7 were given`)

- [ ] **Step 3: Implementierung — `_load_news_events_by_player()`**

Direkt nach `_load_fitness_events_by_player()` (bzw. deren Phase-A-Nachfolgefunktion, vor `_fetch_competition_player_ids`) einfügen:

```python
def _load_news_events_by_player() -> dict[str, list[dict]]:
    """Liest player_news_log (siehe firestore_db.get_history, Phase A's
    generalisierter Reader - Phase B fuellt diese Collection, siehe
    docs/superpowers/specs/2026-08-02-news-sentiment-design.md) einmal pro
    Lauf und gruppiert nach player_id - Basis fuer
    _sentiment_features_as_of() in _fetch_player_training_frame(). Leeres
    Dict bei deaktiviertem Firestore oder Lesefehler (gleiches
    Resilienz-Muster wie _load_fitness_events_by_player) - jeder Spieler
    bekommt dann ueberall den neutralen Cold-Start-Platzhalter (0/0), kein
    Crash."""
    events_by_player: dict[str, list[dict]] = defaultdict(list)
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            for entry in firestore_db.get_history(firestore_db.connect(), "player_news_log"):
                events_by_player[entry["player_id"]].append(entry)
        except Exception as exc:
            print(f"Warnung: player_news_log-Lesezugriff fehlgeschlagen: {exc}", file=sys.stderr)
            return {}
    return dict(events_by_player)
```

- [ ] **Step 4: Implementierung — `_fetch_player_training_frame()` erweitern**

Signatur um den neuen letzten Parameter erweitern, z.B. von (Vor-Phase-A-Stand):

```python
def _fetch_player_training_frame(
    token: str, league_id: str, competition_id: str, player_id: str, team_id: str,
    fitness_events_by_player: dict[str, list[dict]],
) -> pd.DataFrame | None:
```

zu:

```python
def _fetch_player_training_frame(
    token: str, league_id: str, competition_id: str, player_id: str, team_id: str,
    fitness_events_by_player: dict[str, list[dict]],
    news_events_by_player: dict[str, list[dict]],
) -> pd.DataFrame | None:
```

(Falls Phase A hier bereits weitere Parameter ergänzt hat, `news_events_by_player` stattdessen nach deren letztem Parameter anhängen — Reihenfolge der bestehenden Parameter nicht verändern.)

Am Ende der Funktion, direkt nach dem bestehenden Fitness-Feature-Block, ergänzen von:

```python
    events = fitness_events_by_player.get(player_id, [])
    fitness_features = merged["date"].apply(lambda ts: _fitness_features_as_of(events, ts.date()))
    merged["days_since_last_status_change"] = fitness_features.apply(lambda f: f["days_since_last_status_change"])
    merged["status_change_count_90d"] = fitness_features.apply(lambda f: f["status_change_count_90d"])

    return merged
```

zu:

```python
    events = fitness_events_by_player.get(player_id, [])
    fitness_features = merged["date"].apply(lambda ts: _fitness_features_as_of(events, ts.date()))
    merged["days_since_last_status_change"] = fitness_features.apply(lambda f: f["days_since_last_status_change"])
    merged["status_change_count_90d"] = fitness_features.apply(lambda f: f["status_change_count_90d"])

    news_events = news_events_by_player.get(player_id, [])
    sentiment_features = merged["date"].apply(lambda ts: _sentiment_features_as_of(news_events, ts.date()))
    merged["avg_sentiment_7d"] = sentiment_features.apply(lambda f: f["avg_sentiment_7d"])
    merged["news_volume_7d"] = sentiment_features.apply(lambda f: f["news_volume_7d"])

    return merged
```

- [ ] **Step 5: Tests laufen lassen, Erfolg bestätigen (Zwischenstand)**

Run: `python3 -m unittest tests.test_market_predictor.LoadNewsEventsByPlayerTests tests.test_market_predictor.FetchPlayerTrainingFrameSentimentColumnsTests -v`
Expected: alle PASS

- [ ] **Step 6: `_build_corpus()` + Aufrufstellen + `FEATURES` verdrahten**

`_build_corpus()`-Signatur um den neuen letzten Parameter erweitern, z.B. von (Vor-Phase-A-Stand):

```python
def _build_corpus(
    token: str, league_id: str, competition_id: str, fitness_events_by_player: dict[str, list[dict]]
) -> pd.DataFrame:
```

zu:

```python
def _build_corpus(
    token: str, league_id: str, competition_id: str,
    fitness_events_by_player: dict[str, list[dict]],
    news_events_by_player: dict[str, list[dict]],
) -> pd.DataFrame:
```

Im Funktionskörper, die `executor.submit(...)`-Zeile erweitern von:

```python
            executor.submit(_fetch_player_training_frame, token, league_id, competition_id, pid, tid, fitness_events_by_player): pid
```

zu:

```python
            executor.submit(_fetch_player_training_frame, token, league_id, competition_id, pid, tid, fitness_events_by_player, news_events_by_player): pid
```

In `FEATURES` (Konstanten-Block am Dateikopf), ergänzen von:

```python
FEATURES = [
    "p", "mv", "days_to_next",
    "mv_change_1d", "mv_trend_1d",
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence",
    "days_since_last_status_change", "status_change_count_90d",
]
```

zu:

```python
FEATURES = [
    "p", "mv", "days_to_next",
    "mv_change_1d", "mv_trend_1d",
    "mv_change_3d", "mv_vol_3d",
    "mv_trend_7d", "market_divergence",
    "days_since_last_status_change", "status_change_count_90d",
    "avg_sentiment_7d", "news_volume_7d",
]
```

(Falls Phase A bereits `days_since_last_starting_rank_change`/`starting_rank_change_count_90d` ergänzt hat, `avg_sentiment_7d`/`news_volume_7d` einfach zusätzlich ans Ende anhängen — Reihenfolge der bestehenden Einträge nicht verändern.)

In `backfill_prediction_log()`, ersetze:

```python
    fitness_events_by_player = _load_fitness_events_by_player()
    corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player)
```

durch:

```python
    fitness_events_by_player = _load_fitness_events_by_player()
    news_events_by_player = _load_news_events_by_player()
    corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player, news_events_by_player)
```

In `predict_market_value_changes()`, ersetze:

```python
        fitness_events_by_player = _load_fitness_events_by_player()
        corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player)
```

durch:

```python
        fitness_events_by_player = _load_fitness_events_by_player()
        news_events_by_player = _load_news_events_by_player()
        corpus = _build_corpus(token, league_id, competition_id, fitness_events_by_player, news_events_by_player)
```

(In beiden Fällen: falls Phase A hier bereits einen zusätzlichen `starting_rank_events_by_player`-Load/Parameter eingefügt hat, `news_events_by_player`/dessen Load-Aufruf einfach zusätzlich ergänzen, an der jeweils gleichen Stelle wie die bestehenden Event-Loads.)

- [ ] **Step 7: Kompletten Backend-Testlauf verifizieren**

Run: `python3 -m unittest discover -s tests`
Expected: alle PASS (inkl. `BuildCandidatesTests`, `EngineerFeatures3dTargetTests` und aller `_walk_forward_backtest`/`_train_and_track_horizon`-nahen Tests — die beiden neuen `FEATURES`-Einträge dürfen keinen bestehenden Test brechen, da `_sentiment_features_as_of()` nie `NaN` liefert und `_engineer_features()`s `dropna(subset=[...])`-Aufrufe diese beiden neuen Spalten unverändert durchreichen)

- [ ] **Step 8: Live-Smoke-Test (Sandbox hat echten Kickbase/Firestore-Zugriff, siehe HANDOFF.md)**

Run: `python3 -m src.market_predictor`
Expected: läuft ohne Absturz durch, druckt eine Prognose-Zusammenfassung. Prüfen: taucht `avg_sentiment_7d`/`news_volume_7d` sinnvoll in den `FEATURES`-Spalten von `today_df` auf (z.B. per kurzem Debug-Print vor dem eigentlichen Lauf, danach wieder entfernen) — solange `player_news_log` noch keine (oder nur sehr wenige) Einträge hat, MUSS der Wert für die meisten/alle Spieler `0`/`0` sein (Cold-Start, siehe Spec) — das ist der erwartete, korrekte Zustand, kein Fehler.

- [ ] **Step 9: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: Sentiment-Historie als zwei neue Features (avg_sentiment_7d, news_volume_7d) eingebaut"
```

---

## Verification (gesamt)

- [ ] `python3 -m unittest discover -s tests` grün nach jedem Task.
- [ ] Nach Task 2: `python3 -m src.market_predictor` einmal live laufen lassen (Sandbox hat Zugriff) — bestätigt, dass die neue Verdrahtung im echten Pipeline-Lauf nicht crasht.
- [ ] Push nach jedem Task erlaubt, wenn Tests grün (bestehende Projekt-Policy).
- [ ] Nach Abschluss beider Tasks: `HANDOFF.md` aktualisieren (Phase C abgeschlossen, Cold-Start-Status, Hinweis dass eine Auswertung/Neu-Tuning erst sinnvoll ist, sobald Phase A+B über Wochen/Monate echte Historie gesammelt haben).

## Self-Review

- **Spec-Abdeckung:** Feature-Berechnung inkl. Lookahead-Schutz (Task 1, deckt alle 5 in der Design-Spec genannten Testfälle ab plus zwei zusätzliche Grenzfall-/Fehlerfall-Tests), Laden der Rohdaten + Gruppierung (Task 2 Step 1-3, deckt den in der Spec genannten Lesefehler-Pfad ab), Verdrahtung in `_fetch_player_training_frame()`/`_build_corpus()`/`FEATURES` (Task 2 Step 4-6) — alle Abschnitte der Design-Spec (`Architektur`, `Datenfluss`, `Fehlerfälle`, `Testing`, `Betroffene Dateien`) haben eine entsprechende Stelle in diesem Plan. `Out of Scope`-Punkte (Modell-Neu-Tuning, konfidenz-gewichtetes Sentiment, Frontend) werden bewusst nicht umgesetzt, wie in der Spec vorgegeben.
- **Cross-Plan-Abhängigkeit explizit behandelt:** da weder Phase-A- noch Phase-B-Implementierungsplan zum Zeitpunkt der Erstellung existierten, markiert Task 2 explizit, dass die gezeigten Code-Ausschnitte den Vor-Phase-A-Stand widerspiegeln und die tatsächlichen Signaturen vor Beginn frisch verifiziert werden müssen — keine stillschweigende Annahme, dass Phase A exakt so landet wie in dessen Design-Spec skizziert.
- **Platzhalter-Scan:** keine TBD/TODO, jeder Code-Block ist vollständig und lauffähig, jeder Testschritt hat echten, konkreten Testcode. Die "(falls Phase A bereits ... umbenannt hat)"-Hinweise sind keine Implementierungs-Platzhalter, sondern explizite Adaptionsanweisungen für eine echte, im Voraus benannte Cross-Plan-Unbekannte (vom Auftraggeber selbst als bekanntes Risiko benannt).
- **Typ-Konsistenz:** `_sentiment_features_as_of()` (Task 1) liefert `{"avg_sentiment_7d": ..., "news_volume_7d": ...}` — Task 2 nutzt exakt diese beiden Keys in `_fetch_player_training_frame()` und in `FEATURES`. `_load_news_events_by_player()` (Task 2) liefert `dict[str, list[dict]]`, identisch zur bestehenden `_load_fitness_events_by_player()`-Signatur, konsistent als `news_events_by_player` durchgereicht an `_fetch_player_training_frame()`/`_build_corpus()`.
- **YAGNI-Entscheidung:** `_build_corpus()`/`predict_market_value_changes()`/`backfill_prediction_log()` selbst bleiben (wie schon bei der Fitness-Historie-Einführung) ohne direkten Unit-Test für die neue Verdrahtung — stattdessen ein Live-Smoke-Test (Task 2 Step 8), da ein vollständiger Mock des threadenden Corpus-Aufbaus unverhältnismäßig aufwendig wäre und dieses Projekt dafür bereits die etablierte Konvention hat (siehe `docs/superpowers/plans/2026-07-31-fitness-history.md`, Task 5 Step 8).
