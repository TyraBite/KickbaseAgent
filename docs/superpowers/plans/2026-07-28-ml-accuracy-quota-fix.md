# Firestore-Read-Quota-Fix: Tages-Aggregate statt Rohdaten-Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Firestore-Read-Last der `ml_prediction_log`-Auswertung von
"komplette, taeglich wachsende Collection bei JEDEM der 12 taeglichen
Laeufe scannen" (aktuell ~832% der 50k-Reads/Tag-Quota, selbst nach dem
Doppel-Call-Fix noch ~416%) auf ein tragbares Mass senken — per
Tages-Aggregat-Dokumente (`ml_accuracy_daily`, 2 Dokumente/Tag statt
~900 Rohdaten-Dokumente/Tag). Zusaetzlich: Hyperparameter-Inkonsistenz
zwischen Backfill/Live-Modell fixen, Header-Anzeige (synthetischer
Split-Sieger vs. Live-gewaehltes Modell) entschaerfen.

**Architecture:** `ml_prediction_log` (Rohdaten pro Spieler) wird zur
KURZLEBIGEN Staging-Zone — nur die letzten `EVALUATION_LOOKBACK_DAYS`
werden je Lauf gelesen (serverseitig datumsgefiltert), nicht die komplette
Historie. Sobald ein Tag auswertbar ist (Folgetag-Marktwert bekannt), wird
er zu einem winzigen Aggregat-Dokument (`{date, model_type, n,
sign_correct, abs_error_sum}`) verdichtet und in eine neue Collection
`ml_accuracy_daily` geschrieben. Trailing-Fenster-Auswahl UND Trend-Chart
lesen nur noch aus `ml_accuracy_daily` (bleibt bei ~2 Dokumenten/Tag,
selbst nach einem Jahr nur ~730 Dokumente total). Der externe
Rueckgabewert-Vertrag von `predict_market_value_changes()`
(`metrics["accuracy_trend"]`/`metrics["realized_by_model"]`) bleibt
UNVERAENDERT in Form/Shape — `dashboard_export.py`/`index.html` brauchen
dadurch (bis auf eine kleine Label-Klarstellung) KEINE Aenderung.

**Backfill-Utility** schreibt kuenftig direkt Tages-Aggregate (kennt Predicted
UND tatsaechlichen Wert im selben Walk-Forward-Fold, braucht also gar
keine separate spaetere Auswertung wie der Live-Pfad).

## Global Constraints

- **HEUTE KEINE echten Firestore-Calls mehr** (User-Anweisung nach dem
  Quota-Vorfall) — jede Verifikation in diesem Plan laeuft NUR ueber
  gemockte Unit-Tests (`unittest.mock.MagicMock`/`patch`), NIEMALS ein
  echter `FIRESTORE_ENABLED=1`-Testlauf. Die eigentliche Live-Verifikation
  (inkl. Rest-Backfill) passiert morgen zusammen mit der
  Backfill-Fortsetzung (siehe HANDOFF.md).
- Externe Ergebnisform von `predict_market_value_changes()["metrics"]`
  (`accuracy_trend`, `realized_by_model`, `model_type`, `selection_reason`)
  bleibt gleich — `dashboard_export.py`/`index.html` sollen NICHT
  angefasst werden muessen (Ausnahme: Task 4s kleine Label-Klarstellung).
- Kein Loeschen alter `ml_prediction_log`-Rohdaten noetig — das
  serverseitige Datumsfilter (`where("date", ">=", since)`) allein loest
  das Skalierungsproblem, unabhaengig davon ob alte Dokumente noch
  irgendwo rumliegen (kein zusaetzlicher Lösch-Mechanismus in diesem Plan).
- **Git-Workflow**: Commits lokal lassen, NICHT pushen, keine Feature-
  Branches — User pusht selbst (Ruleset `NeverPushOnMain`).

---

### Task 1: `firestore_db.py` — Aggregat-Collection + gefiltertes Lesen

**Files:** Modify: `src/firestore_db.py`; Modify: `tests/test_firestore_db.py`

**Interfaces:**
- Produziert: `get_recent_prediction_log_entries(client, since_date: str) -> list[dict]`,
  `upsert_accuracy_daily(client, entries: list[dict]) -> None`,
  `get_accuracy_daily(client) -> list[dict]`. Von Task 2 genutzt.
- **Entfernt**: `get_prediction_log_entries(client)` (unfiltertes Voll-
  Scan, wird durch die datumsgefilterte Variante ersetzt, kein Aufrufer
  bleibt danach uebrig — siehe Task 2).

- [ ] **Schritt 1: Import ergaenzen (oben in der Datei, `from google.cloud import firestore`-Zeile)**

```python
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
```

- [ ] **Schritt 2: `get_prediction_log_entries` ENTFERNEN, durch zwei neue Funktionen ersetzen (an derselben Stelle in der Datei)**

Von:
```python
def get_prediction_log_entries(client: firestore.Client) -> list[dict]:
    """Liest die komplette ml_prediction_log-Collection - keine Datumsfilterung
    noetig, Datenmenge bleibt ueberschaubar (~450 Spieler x 2 Modelle x
    max. ~1 Jahr Trailing-Retention)."""
    return [doc.to_dict() for doc in client.collection("ml_prediction_log").stream()]
```
Zu:
```python
def get_recent_prediction_log_entries(client: firestore.Client, since_date: str) -> list[dict]:
    """Liest NUR ml_prediction_log-Eintraege ab since_date (inklusive,
    serverseitig gefiltert via FieldFilter) - die Collection waechst
    taeglich um ~900 Rohdaten-Dokumente (450 Spieler x 2 Modelle), ein
    ungefiltertes Voll-Scan bei jedem der 12 taeglichen Laeufe wuerde
    Firestores Read-Quota sprengen (siehe HANDOFF.md, Quota-Vorfall
    2026-07-28). `ml_prediction_log` ist seit Phase-4-Quota-Fix nur noch
    eine kurzlebige Staging-Zone fuer NEUE, noch nicht ausgewertete
    Prognosen - siehe market_predictor.EVALUATION_LOOKBACK_DAYS."""
    query = client.collection("ml_prediction_log").where(filter=FieldFilter("date", ">=", since_date))
    return [doc.to_dict() for doc in query.stream()]


def upsert_accuracy_daily(client: firestore.Client, entries: list[dict]) -> None:
    """Aggregierte Tages-/Modell-Genauigkeit (EIN Dokument pro (date,
    model_type) statt Rohdaten pro Spieler) - Doc-Id `{date}_{model_type}`.
    Ermoeglicht Trailing-Fenster-/Trend-Berechnung ueber lange Zeitraeume
    mit nur ~2 Dokumenten pro Tag statt ~900 - der eigentliche Fix fuers
    Quota-Problem. Idempotent (Ueberschreiben bei erneuter Auswertung
    desselben Tages ist unproblematisch)."""
    docs = {f"{e['date']}_{e['model_type']}": e for e in entries}
    _write_in_batches(client, "ml_accuracy_daily", docs)


def get_accuracy_daily(client: firestore.Client) -> list[dict]:
    """Liest die komplette ml_accuracy_daily-Collection - unkritisch klein
    (2 Dokumente pro Tag, auch nach einem Jahr nur ~730 Dokumente total,
    verglichen mit ~164.000+ bei der alten Rohdaten-basierten Variante)."""
    return [doc.to_dict() for doc in client.collection("ml_accuracy_daily").stream()]
```

- [ ] **Schritt 3: Tests in `tests/test_firestore_db.py` anpassen**

Die bestehende Test-Klasse fuer `get_prediction_log_entries` (suche
danach, z.B. `GetPredictionLogEntriesTests`) MUSS entfernt/ersetzt werden,
da die Funktion nicht mehr existiert. Neue Tests:

```python
class GetRecentPredictionLogEntriesTests(unittest.TestCase):
    def test_filters_by_date_server_side(self):
        client = MagicMock()
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100}
        client.collection.return_value.where.return_value.stream.return_value = [doc1]

        result = firestore_db.get_recent_prediction_log_entries(client, "2026-07-25")

        client.collection.assert_any_call("ml_prediction_log")
        client.collection.return_value.where.assert_called_once()
        self.assertEqual(len(result), 1)


class UpsertAccuracyDailyTests(unittest.TestCase):
    def test_doc_id_is_date_and_model_type(self):
        client = MagicMock()
        entries = [{"date": "2026-07-27", "model_type": "RandomForest", "n": 450, "sign_correct": 300, "abs_error_sum": 12345.0}]

        firestore_db.upsert_accuracy_daily(client, entries)

        doc_ids = _doc_ids(client)
        self.assertIn("2026-07-27_RandomForest", doc_ids)


class GetAccuracyDailyTests(unittest.TestCase):
    def test_returns_all_documents(self):
        client = MagicMock()
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"date": "2026-07-27", "model_type": "RandomForest", "n": 450, "sign_correct": 300, "abs_error_sum": 12345.0}
        client.collection.return_value.stream.return_value = [doc1]

        result = firestore_db.get_accuracy_daily(client)

        client.collection.assert_any_call("ml_accuracy_daily")
        self.assertEqual(len(result), 1)
```
Entferne auch etwaige Tests, die `upsert_prediction_log_entries`s ALTES
Doc-Id-Schema pruefen, falls die sich NICHT geaendert haben (Schema fuer
`upsert_prediction_log_entries` selbst bleibt unveraendert in diesem
Task — nur `get_prediction_log_entries` wird ersetzt).

- [ ] **Schritt 4: Tests laufen lassen (NUR mit Mocks, KEIN echter Firestore-Call)**

```
python3 -m unittest discover -s tests -v
```
Erwartung: alle gruen.

- [ ] **Schritt 5: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/firestore_db.py tests/test_firestore_db.py
git commit -m "Firestore: Tages-Aggregat-Collection ml_accuracy_daily + datumsgefilterter Read statt Voll-Scan"
```

---

### Task 2: `market_predictor.py` — Aggregat-basierte Auswertung/Trend + `synthetic_winner`

**Files:** Modify: `src/market_predictor.py`; Modify: `tests/test_market_predictor.py`

**Interfaces:**
- Konsumiert: Task 1s neue Firestore-Funktionen.
- Produziert: unveraenderte externe Form von
  `predict_market_value_changes()["metrics"]["accuracy_trend"]`/
  `["realized_by_model"]`, PLUS neues Feld `metrics["synthetic_winner"]`.

**WICHTIG**: Dieser Task ist der komplexeste — mehrere alte Funktionen
werden ersetzt. Lies den kompletten aktuellen Stand der betroffenen
Funktionen in `src/market_predictor.py` (Zeilen ca. 371-789, exakte
Zeilen koennen sich seit diesem Brief leicht verschoben haben) SELBST
nochmal, bevor du anfaengst, um sicherzugehen dass die "Von"-Bloecke
unten noch exakt matchen.

- [ ] **Schritt 1: Neue Konstante ergaenzen (bei den anderen Konstanten, nach `MIN_REALIZED_SAMPLES_FOR_SELECTION`)**

```python
EVALUATION_LOOKBACK_DAYS = 3
```
(Puffer: heute frisch geloggt/noch nicht auswertbar + gestern jetzt
auswertbar + 1 Tag Sicherheitsabstand fuer Cron-Timing-Schwankungen.)

- [ ] **Schritt 2: `_load_prediction_log()` durch ZWEI Funktionen ersetzen**

Von (kompletter aktueller Funktionskoerper):
```python
def _load_prediction_log() -> list[dict]:
    """Liest bei FIRESTORE_ENABLED aus Firestore (persistiert ueber CI-Laeufe
    hinweg, anders als die lokale Datei) - Firestore-Lesefehler faellt
    zurueck auf die lokale Datei statt die Pipeline zu crashen. Ohne
    FIRESTORE_ENABLED (lokaler Testlauf) bleibt alles wie bisher."""
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            return firestore_db.get_prediction_log_entries(firestore_db.connect())
        except Exception as exc:
            print(
                f"Warnung: ml_prediction_log-Lesezugriff fehlgeschlagen, nutze lokale Datei: {exc}",
                file=sys.stderr,
            )
    if not PREDICTION_LOG_PATH.exists():
        return []
    entries = []
    for line in PREDICTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries
```
Zu (zwei separate Funktionen — eine NUR fuer die lokale Datei, eine
gefiltert fuer die "was ist neu auswertbar"-Logik):
```python
def _load_local_prediction_log() -> list[dict]:
    """Liest AUSSCHLIESSLICH die lokale data/ml_prediction_log.jsonl (kein
    Firestore-Zugriff) - fuer die lokale Datei-Fallback-Pflege
    (_append_todays_predictions/_save_prediction_log), die ein
    Read-Modify-Write auf der KOMPLETTEN lokalen Datei braucht. Firestore
    braucht dafuer KEINEN vorherigen Read (Upsert ist idempotent per
    Doc-Id) - ein Firestore-Read hier waere reine Verschwendung."""
    if not PREDICTION_LOG_PATH.exists():
        return []
    entries = []
    for line in PREDICTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def _load_recent_prediction_log(today: str) -> list[dict]:
    """Liest NUR die letzten EVALUATION_LOOKBACK_DAYS Tage roher Pro-Spieler-
    Prognosen (Firestore serverseitig datumsgefiltert bei FIRESTORE_ENABLED,
    sonst die lokale Datei client-seitig gefiltert) - genug um neu
    auswertbare Eintraege zu finden, OHNE die komplette (taeglich
    wachsende) Historie zu scannen. Firestore-Lesefehler faellt auf die
    lokale Datei zurueck statt zu crashen."""
    since = (datetime.date.fromisoformat(today) - datetime.timedelta(days=EVALUATION_LOOKBACK_DAYS)).isoformat()
    if os.environ.get("FIRESTORE_ENABLED"):
        try:
            return firestore_db.get_recent_prediction_log_entries(firestore_db.connect(), since)
        except Exception as exc:
            print(
                f"Warnung: ml_prediction_log-Lesezugriff fehlgeschlagen, nutze lokale Datei: {exc}",
                file=sys.stderr,
            )
    return [e for e in _load_local_prediction_log() if e["date"] >= since]
```

- [ ] **Schritt 3: `_append_todays_predictions()` auf `_load_local_prediction_log()` umstellen**

Von:
```python
    log = _load_prediction_log() + new_entries
    _save_prediction_log(log)
```
Zu:
```python
    log = _load_local_prediction_log() + new_entries
    _save_prediction_log(log)
```
(Nur diese eine Zeile aendert sich in `_append_todays_predictions` — der
Rest der Funktion bleibt unveraendert.)

- [ ] **Schritt 4: `_summarize_window` durch `_summarize_from_daily` ersetzen (arbeitet auf Aggregat-Dokumenten statt Rohdaten-Listen)**

Von:
```python
def _summarize_window(evaluated: list[dict], today: str, days: int) -> dict | None:
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    window = [e for e in evaluated if e["date"] >= cutoff]
    if not window:
        return None
    sign_accuracy = sum(1 for e in window if e["sign_correct"]) / len(window) * 100
    mae = sum(e["abs_error"] for e in window) / len(window)
    return {"n": len(window), "sign_accuracy": round(sign_accuracy, 1), "mae": round(mae, 2)}
```
Zu:
```python
def _summarize_from_daily(daily_docs: list[dict], today: str, days: int) -> dict | None:
    """Wie zuvor `_summarize_window`, aber auf bereits AGGREGIERTEN
    Tages-/Modell-Dokumenten (ein Dokument pro Kalendertag, nicht pro
    Spieler) - Summiert n/sign_correct/abs_error_sum ueber das Fenster,
    statt jede Rohdaten-Zeile einzeln zu iterieren."""
    cutoff = (datetime.date.fromisoformat(today) - datetime.timedelta(days=days)).isoformat()
    window = [d for d in daily_docs if d["date"] >= cutoff]
    n = sum(d["n"] for d in window)
    if n == 0:
        return None
    sign_accuracy = sum(d["sign_correct"] for d in window) / n * 100
    mae = sum(d["abs_error_sum"] for d in window) / n
    return {"n": n, "sign_accuracy": round(sign_accuracy, 1), "mae": round(mae, 2)}
```

- [ ] **Schritt 5: `_evaluate_realized_accuracy_by_model` durch `_realized_by_model_from_daily` ersetzen**

Von:
```python
def _evaluate_realized_accuracy_by_model(log_entries: list[dict], mv_lookup: dict, today: str) -> dict[str, dict]:
    """Wie zuvor, aber getrennt pro model_type - ermoeglicht echten
    Kopf-an-Kopf-Vergleich ueber die Zeit statt nur 'der jeweilige
    Tagessieger, egal welches Modell das war'. Log-Eintraege ohne
    model_type (altes Schema, vor Phase 4) werden uebersprungen statt
    einen KeyError zu werfen - bewusst keine Migration noetig."""
    evaluated_by_model: dict[str, list[dict]] = {"RandomForest": [], "HistGradientBoosting": []}
    for entry in log_entries:
        model_type = entry.get("model_type")
        if model_type not in evaluated_by_model:
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        evaluated_by_model[model_type].append(
            {
                "date": date,
                "sign_correct": np.sign(entry["predicted_delta"]) == np.sign(actual_delta),
                "abs_error": abs(entry["predicted_delta"] - actual_delta),
            }
        )
    return {
        name: {f"realized_{days}d": _summarize_window(evaluated, today, days) for days in ACCURACY_WINDOWS_DAYS}
        for name, evaluated in evaluated_by_model.items()
    }
```
Zu (zwei neue Funktionen: eine baut die Tages-Aggregate aus frischen
Rohdaten, eine liest die Trailing-Fenster aus bereits gespeicherten
Aggregaten):
```python
def _build_daily_accuracy_updates(recent_entries: list[dict], mv_lookup: dict, today: str) -> list[dict]:
    """Wertet alle in recent_entries bereits auswertbaren Eintraege aus
    (Datum < today, Folgetag-Marktwert im aktuellen Corpus bekannt) und
    aggregiert sie zu EINEM Dokument pro (date, model_type) - fuer
    ml_accuracy_daily. Log-Eintraege ohne model_type (altes Schema, vor
    Phase 4) werden uebersprungen statt einen KeyError zu werfen."""
    agg: dict[tuple[str, str], dict] = {}
    for entry in recent_entries:
        model_type = entry.get("model_type")
        if model_type not in ("RandomForest", "HistGradientBoosting"):
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        sign_correct = bool(np.sign(entry["predicted_delta"]) == np.sign(actual_delta))
        abs_error = abs(entry["predicted_delta"] - actual_delta)
        key = (date, model_type)
        bucket = agg.setdefault(key, {"date": date, "model_type": model_type, "n": 0, "sign_correct": 0, "abs_error_sum": 0.0})
        bucket["n"] += 1
        bucket["sign_correct"] += int(sign_correct)
        bucket["abs_error_sum"] += abs_error
    return list(agg.values())


def _realized_by_model_from_daily(daily_docs: list[dict], today: str) -> dict[str, dict]:
    """Trailing-Fenster-Zusammenfassung pro Modell aus bereits gespeicherten
    Tages-Aggregaten (ml_accuracy_daily) - ersetzt die alte, Rohdaten-
    basierte _evaluate_realized_accuracy_by_model. Externe Rueckgabeform
    ist IDENTISCH zur alten Funktion (dict[model_type, dict[fenster_label,
    summary]])."""
    by_model: dict[str, list[dict]] = {"RandomForest": [], "HistGradientBoosting": []}
    for doc in daily_docs:
        if doc.get("model_type") in by_model:
            by_model[doc["model_type"]].append(doc)
    return {
        name: {f"realized_{days}d": _summarize_from_daily(docs, today, days) for days in ACCURACY_WINDOWS_DAYS}
        for name, docs in by_model.items()
    }
```

- [ ] **Schritt 6: `_build_accuracy_trend` durch `_trend_from_daily` ersetzen**

Von:
```python
def _build_accuracy_trend(log_entries: list[dict], mv_lookup: dict, today: str) -> list[dict]:
    """Taegliche realisierte sign_accuracy pro Modell UEBER DIE KOMPLETTE
    Historie (nicht nur 'heute' wie _evaluate_realized_accuracy_by_model) -
    Rohdaten fuer den Trend-Chart im 'ML-Genauigkeit'-Tab. Gruppiert nach
    Log-Datum, ein Eintrag pro Tag mit beiden Modellen nebeneinander."""
    by_date: dict[str, dict[str, list[bool]]] = {}
    for entry in log_entries:
        model_type = entry.get("model_type")
        if model_type not in ("RandomForest", "HistGradientBoosting"):
            continue
        date = entry["date"]
        if date >= today:
            continue
        next_date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
        mv_then = mv_lookup.get((entry["player_id"], date))
        mv_next = mv_lookup.get((entry["player_id"], next_date))
        if mv_then is None or mv_next is None:
            continue
        actual_delta = mv_next - mv_then
        sign_correct = bool(np.sign(entry["predicted_delta"]) == np.sign(actual_delta))
        by_date.setdefault(date, {"RandomForest": [], "HistGradientBoosting": []})[model_type].append(sign_correct)

    trend = []
    for date in sorted(by_date):
        day = {"date": date}
        for model_type, hits in by_date[date].items():
            day[model_type] = round(float(np.mean(hits)) * 100, 1) if hits else None
        trend.append(day)
    return trend
```
Zu (viel einfacher — die Aggregate SIND bereits pro Tag, kein Neuberechnen
noetig):
```python
def _trend_from_daily(daily_docs: list[dict]) -> list[dict]:
    """Taegliche realisierte sign_accuracy pro Modell fuer den Trend-Chart -
    liest direkt aus bereits gespeicherten ml_accuracy_daily-Aggregaten
    (keine Rohdaten/mv_lookup mehr noetig, die Auswertung ist schon
    passiert als das jeweilige Aggregat geschrieben wurde). Externe
    Rueckgabeform ist IDENTISCH zur alten Funktion (Liste von
    {date, RandomForest, HistGradientBoosting})."""
    by_date: dict[str, dict] = {}
    for doc in daily_docs:
        model_type = doc.get("model_type")
        if model_type not in ("RandomForest", "HistGradientBoosting"):
            continue
        day = by_date.setdefault(doc["date"], {"date": doc["date"]})
        day[model_type] = round(doc["sign_correct"] / doc["n"] * 100, 1) if doc["n"] else None
    return [by_date[date] for date in sorted(by_date)]
```

- [ ] **Schritt 7: `predict_market_value_changes()` verdrahten**

Von (aktueller Abschnitt ab `today_iso = ...` bis vor `live_model_name, selection_reason = ...`):
```python
        today_iso = pd.Timestamp(corpus["date"].max()).date().isoformat()
        mv_lookup = _build_mv_lookup(corpus)
        log_entries = _load_prediction_log()
        realized_by_model = _evaluate_realized_accuracy_by_model(log_entries, mv_lookup, today_iso)
        metrics["realized_by_model"] = realized_by_model
        metrics["accuracy_trend"] = _build_accuracy_trend(log_entries, mv_lookup, today_iso)

        live_model_name, selection_reason = _select_live_model(realized_by_model, synthetic_winner)
        metrics["model_type"] = live_model_name
        metrics["selection_reason"] = selection_reason
```
Zu:
```python
        today_iso = pd.Timestamp(corpus["date"].max()).date().isoformat()
        mv_lookup = _build_mv_lookup(corpus)

        recent_entries = _load_recent_prediction_log(today_iso)
        daily_updates = _build_daily_accuracy_updates(recent_entries, mv_lookup, today_iso)
        if daily_updates and os.environ.get("FIRESTORE_ENABLED"):
            try:
                firestore_db.upsert_accuracy_daily(firestore_db.connect(), daily_updates)
            except Exception as exc:
                print(f"Warnung: Firestore-Schreibzugriff fuer ml_accuracy_daily fehlgeschlagen: {exc}", file=sys.stderr)

        daily_docs: list[dict] = []
        if os.environ.get("FIRESTORE_ENABLED"):
            try:
                daily_docs = firestore_db.get_accuracy_daily(firestore_db.connect())
            except Exception as exc:
                print(f"Warnung: ml_accuracy_daily-Lesezugriff fehlgeschlagen: {exc}", file=sys.stderr)

        realized_by_model = _realized_by_model_from_daily(daily_docs, today_iso)
        metrics["realized_by_model"] = realized_by_model
        metrics["accuracy_trend"] = _trend_from_daily(daily_docs)
        metrics["synthetic_winner"] = synthetic_winner

        live_model_name, selection_reason = _select_live_model(realized_by_model, synthetic_winner)
        metrics["model_type"] = live_model_name
        metrics["selection_reason"] = selection_reason
```
**Hinweis**: `daily_docs` ist absichtlich `[]` (nicht `None`/Crash) wenn
`FIRESTORE_ENABLED` nicht gesetzt ist (lokaler Testlauf ohne Firestore-
Zugriff) — es gibt bewusst KEINEN lokalen Datei-Fallback fuer
`ml_accuracy_daily` (neue Collection, keine lokale Datei dafuer). Das ist
kein Rueckschritt: `realized_by_model`/`accuracy_trend` degradieren dann
einfach auf "keine Historie" (alle Fenster `None`, leere Trend-Liste),
`_select_live_model` faellt automatisch auf den synthetischen Split
zurueck (bestehende Fallback-Logik, unveraendert).

- [ ] **Schritt 8: Tests in `tests/test_market_predictor.py` anpassen**

Die BESTEHENDEN Tests fuer `_evaluate_realized_accuracy_by_model`
(`EvaluateRealizedAccuracyByModelTests`) und `_load_prediction_log`
(`LoadPredictionLogTests`) muessen ENTFERNT/ERSETZT werden, da die
Funktionen nicht mehr existieren (bzw. umbenannt/aufgespalten wurden).
Neue Tests:

```python
from src.market_predictor import (
    _summarize_from_daily,
    _build_daily_accuracy_updates,
    _realized_by_model_from_daily,
    _trend_from_daily,
    _load_local_prediction_log,
    _load_recent_prediction_log,
)


class SummarizeFromDailyTests(unittest.TestCase):
    def test_aggregates_over_window(self):
        daily = [
            {"date": "2026-07-20", "n": 450, "sign_correct": 300, "abs_error_sum": 45000.0},
            {"date": "2026-07-21", "n": 450, "sign_correct": 270, "abs_error_sum": 40000.0},
        ]
        result = _summarize_from_daily(daily, "2026-07-28", 30)
        self.assertEqual(result["n"], 900)
        self.assertAlmostEqual(result["sign_accuracy"], 63.3, places=1)

    def test_returns_none_when_window_empty(self):
        result = _summarize_from_daily([{"date": "2026-01-01", "n": 10, "sign_correct": 5, "abs_error_sum": 100.0}], "2026-07-28", 7)
        self.assertIsNone(result)


class BuildDailyAccuracyUpdatesTests(unittest.TestCase):
    def test_aggregates_by_date_and_model(self):
        entries = [
            {"date": "2026-07-27", "player_id": "p1", "model_type": "RandomForest", "predicted_delta": 100},
            {"date": "2026-07-27", "player_id": "p2", "model_type": "RandomForest", "predicted_delta": -50},
        ]
        mv_lookup = {
            ("p1", "2026-07-27"): 1000.0, ("p1", "2026-07-28"): 1200.0,
            ("p2", "2026-07-27"): 1000.0, ("p2", "2026-07-28"): 1200.0,
        }
        result = _build_daily_accuracy_updates(entries, mv_lookup, "2026-07-29")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["n"], 2)
        self.assertEqual(result[0]["sign_correct"], 1)  # p1 richtig (positiv+positiv), p2 falsch (negativ vorhergesagt, tatsaechlich positiv)

    def test_skips_entries_without_model_type(self):
        entries = [{"date": "2026-07-01", "player_id": "p1", "predicted_delta": 100}]
        result = _build_daily_accuracy_updates(entries, {}, "2026-07-28")
        self.assertEqual(result, [])


class RealizedByModelFromDailyTests(unittest.TestCase):
    def test_separates_by_model(self):
        daily = [
            {"date": "2026-07-27", "model_type": "RandomForest", "n": 10, "sign_correct": 8, "abs_error_sum": 100.0},
            {"date": "2026-07-27", "model_type": "HistGradientBoosting", "n": 10, "sign_correct": 4, "abs_error_sum": 100.0},
        ]
        result = _realized_by_model_from_daily(daily, "2026-07-29")
        self.assertGreater(result["RandomForest"]["realized_7d"]["sign_accuracy"], result["HistGradientBoosting"]["realized_7d"]["sign_accuracy"])


class TrendFromDailyTests(unittest.TestCase):
    def test_builds_sorted_trend_with_both_models(self):
        daily = [
            {"date": "2026-07-27", "model_type": "RandomForest", "n": 10, "sign_correct": 6, "abs_error_sum": 50.0},
            {"date": "2026-07-26", "model_type": "HistGradientBoosting", "n": 10, "sign_correct": 5, "abs_error_sum": 50.0},
        ]
        trend = _trend_from_daily(daily)
        self.assertEqual([d["date"] for d in trend], ["2026-07-26", "2026-07-27"])
        self.assertEqual(trend[1]["RandomForest"], 60.0)
        self.assertIsNone(trend[1].get("HistGradientBoosting"))


class LoadLocalPredictionLogTests(unittest.TestCase):
    def test_never_touches_firestore(self):
        with patch("src.market_predictor.firestore_db.connect") as mock_connect:
            _load_local_prediction_log()
            mock_connect.assert_not_called()


class LoadRecentPredictionLogTests(unittest.TestCase):
    @patch("src.market_predictor.firestore_db.get_recent_prediction_log_entries")
    @patch("src.market_predictor.firestore_db.connect")
    def test_passes_date_filter_to_firestore(self, mock_connect, mock_get):
        mock_get.return_value = []
        with patch.dict(os.environ, {"FIRESTORE_ENABLED": "1"}):
            _load_recent_prediction_log("2026-07-28")
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[1], "2026-07-25")  # today - EVALUATION_LOOKBACK_DAYS(3)
```
(Passe die exakten Import-/Patch-Pfade an, falls sie nicht 1:1 passen —
schau dir die BESTEHENDEN Tests in derselben Datei fuer das korrekte
Patch-Pfad-Muster an, z.B. `src.market_predictor.firestore_db.connect`.)

- [ ] **Schritt 9: Tests laufen lassen (NUR Mocks, KEIN echter Firestore-Call)**

```
python3 -m unittest discover -s tests -v
```

- [ ] **Schritt 10: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: Auswertung/Trend auf ml_accuracy_daily-Aggregate umstellen (Firestore-Read-Quota-Fix)"
```

---

### Task 3: `backfill_prediction_log` — schreibt direkt Tages-Aggregate + geteilte Hyperparameter

**Files:** Modify: `src/market_predictor.py`; Modify: `tests/test_market_predictor.py`

**Interfaces:**
- Produziert: `_build_candidates() -> dict[str, object]` (neue geteilte
  Helper-Funktion, von `_train_and_evaluate` UND `backfill_prediction_log`
  genutzt — behebt die Hyperparameter-Inkonsistenz, RandomForest hat
  ueberall `n_estimators=500` wie in der echten Live-Prognose, nicht mehr
  `200` im Backfill).
- `backfill_prediction_log` schreibt jetzt nach `ml_accuracy_daily` statt
  `ml_prediction_log` (kennt Prognose UND echten Wert im selben Fold,
  braucht keine spaetere separate Auswertung wie der Live-Pfad).

**Wichtig**: `_walk_forward_backtest` (bestehende Funktion) NICHT
anfassen/umbauen — die nutzt bewusst `n_estimators=200` als eigene,
unabhaengige Design-Entscheidung (schnellerer taeglicher Backtest-Vergleich),
das ist NICHT Teil dieses Fixes und bleibt wie es ist.

- [ ] **Schritt 1: Neue Helper-Funktion `_build_candidates()` (vor `_train_and_evaluate`)**

```python
def _build_candidates() -> dict[str, object]:
    """Baut die zwei Modell-Kandidaten mit denselben Hyperparametern, die
    auch fuer die echte Live-Prognose (_train_and_evaluate) verwendet
    werden - wichtig fuer backfill_prediction_log, damit historisch
    geloggte Genauigkeit mit der Live-Prognose vergleichbar bleibt (vorher:
    Backfill nutzte irrtuemlich dieselben (kleineren) Parameter wie der
    unabhaengige _walk_forward_backtest, nicht die der echten
    Live-Prognose)."""
    return {
        "RandomForest": RandomForestRegressor(
            n_estimators=500,
            max_depth=20,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features="sqrt",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
        "HistGradientBoosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE),
    }
```

- [ ] **Schritt 2: `_train_and_evaluate` auf `_build_candidates()` umstellen**

Von (der `candidates = {...}`-Block in `_train_and_evaluate`):
```python
    candidates = {
        "RandomForest": RandomForestRegressor(
            n_estimators=500,
            max_depth=20,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features="sqrt",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
        "HistGradientBoosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE),
    }
```
Zu:
```python
    candidates = _build_candidates()
```

- [ ] **Schritt 3: `backfill_prediction_log` komplett umbauen — schreibt Tages-Aggregate statt Rohdaten**

Von (aktueller kompletter Funktionskoerper):
```python
def backfill_prediction_log(days: int = 90) -> dict:
    """Einmalige Utility (dauerhaft im Code, nicht Teil des taeglichen Laufs):
    baut denselben Corpus wie ein normaler Lauf, aber statt nur der letzten
    BACKTEST_FOLDS Cutoffs werden bis zu `days` rollierende historische
    Cutoffs durchlaufen (begrenzt durch verfuegbare Kickbase-Historie UND
    genug Trainingszeilen je Cutoff - fruehe Tage im ~365-Tage-Fenster
    fallen typischerweise raus). Pro Fold werden ECHTE Pro-Spieler-
    predicted_delta-Werte fuer BEIDE Modelle gesammelt (nicht nur
    aggregiertes Hit/Miss wie _walk_forward_backtest) und als
    ml_prediction_log-Eintraege nach Firestore geschrieben - schliesst die
    Kaltstart-Luecke fuer die Trailing-30d-Live-Auswahl, ohne 90 echte
    Kalendertage abwarten zu muessen. Wiederverwendbar, falls die
    Firestore-Historie je zurueckgesetzt werden muss."""
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        print("Warnung: KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen, Backfill uebersprungen.", file=sys.stderr)
        return {"folds_run": 0, "entries_written": 0}

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    me = get_me(token, league_id)
    competition_id = me.get("cpi") or "1"
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)

    dates = sorted(history_df["date"].unique())
    cutoffs = dates[-days:] if len(dates) > days else dates

    entries = []
    folds_run = 0
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[TARGET]
        x_test = test[FEATURES]
        cutoff_date = pd.Timestamp(cutoff).date().isoformat()

        candidates = {
            "RandomForest": RandomForestRegressor(
                n_estimators=200,
                max_depth=20,
                min_samples_split=5,
                min_samples_leaf=2,
                max_features="sqrt",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
            "HistGradientBoosting": HistGradientBoostingRegressor(random_state=RANDOM_STATE),
        }
        for model_type, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            entries.extend(
                {
                    "date": cutoff_date,
                    "player_id": player_id,
                    "model_type": model_type,
                    "predicted_delta": round(float(pred)),
                }
                for player_id, pred in zip(test["player_id"], y_pred)
            )

    if entries and os.environ.get("FIRESTORE_ENABLED"):
        try:
            fs_client = firestore_db.connect()
            firestore_db.upsert_prediction_log_entries(fs_client, entries)
        except Exception as exc:  # z.B. Firestore-Schreib-Quota (Spark-Free-Tier)
            # ausgeschoepft bei grossen `days`-Werten - _write_in_batches
            # committet Batches sequentiell, ein Teil koennte also schon
            # angekommen sein, bevor der Fehler auftrat. Kein Crash, damit
            # der User den Backfill in kleineren Portionen/an einem
            # Folgetag fortsetzen kann, statt komplett von vorn anzufangen.
            print(
                f"Warnung: Firestore-Schreibzugriff fuer Backfill fehlgeschlagen (evtl. Quota-Limit) - "
                f"ein Teil der {len(entries)} Eintraege ist evtl. schon angekommen: {exc}",
                file=sys.stderr,
            )

    return {"folds_run": folds_run, "entries_written": len(entries)}
```
Zu:
```python
def backfill_prediction_log(days: int = 90) -> dict:
    """Einmalige Utility (dauerhaft im Code, nicht Teil des taeglichen Laufs):
    baut denselben Corpus wie ein normaler Lauf, aber statt nur der letzten
    BACKTEST_FOLDS Cutoffs werden bis zu `days` rollierende historische
    Cutoffs durchlaufen (begrenzt durch verfuegbare Kickbase-Historie UND
    genug Trainingszeilen je Cutoff - fruehe Tage im ~365-Tage-Fenster
    fallen typischerweise raus). Anders als der Live-Pfad kennt jeder
    Walk-Forward-Fold Prognose UND tatsaechlichen Wert (mv_target) im
    selben Schritt - schreibt deshalb DIREKT Tages-Aggregate nach
    ml_accuracy_daily, keine Rohdaten-Zwischenstation noetig (auch das
    spart Schreibvolumen: 2 Dokumente/Tag statt 2 x ~450). Wiederverwendbar,
    falls die Firestore-Historie je zurueckgesetzt werden muss."""
    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        print("Warnung: KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen, Backfill uebersprungen.", file=sys.stderr)
        return {"folds_run": 0, "days_written": 0}

    token, _user, leagues = login(email, password)
    league_id = leagues[0]["id"]
    me = get_me(token, league_id)
    competition_id = me.get("cpi") or "1"
    corpus = _build_corpus(token, league_id, competition_id)
    history_df, _today_df = _engineer_features(corpus)

    dates = sorted(history_df["date"].unique())
    cutoffs = dates[-days:] if len(dates) > days else dates

    daily_updates = []
    folds_run = 0
    for cutoff in cutoffs:
        train = history_df[history_df["date"] < cutoff]
        test = history_df[history_df["date"] == cutoff]
        if len(train) < BACKTEST_MIN_TRAIN_ROWS or test.empty:
            continue
        folds_run += 1

        x_train, y_train = train[FEATURES], train[TARGET]
        x_test = test[FEATURES]
        y_test_actual = test["mv_target"]
        cutoff_date = pd.Timestamp(cutoff).date().isoformat()

        candidates = _build_candidates()
        for model_type, candidate in candidates.items():
            candidate.fit(x_train, y_train)
            y_pred = candidate.predict(x_test)
            sign_correct = np.sign(y_test_actual) == np.sign(y_pred)
            abs_error = np.abs(y_test_actual - y_pred)
            daily_updates.append(
                {
                    "date": cutoff_date,
                    "model_type": model_type,
                    "n": int(len(sign_correct)),
                    "sign_correct": int(sign_correct.sum()),
                    "abs_error_sum": float(abs_error.sum()),
                }
            )

    if daily_updates and os.environ.get("FIRESTORE_ENABLED"):
        try:
            fs_client = firestore_db.connect()
            firestore_db.upsert_accuracy_daily(fs_client, daily_updates)
        except Exception as exc:  # z.B. Firestore-Schreib-Quota (Spark-Free-Tier)
            print(
                f"Warnung: Firestore-Schreibzugriff fuer Backfill fehlgeschlagen (evtl. Quota-Limit) - "
                f"ein Teil der {len(daily_updates)} Tages-Aggregate ist evtl. schon angekommen: {exc}",
                file=sys.stderr,
            )

    return {"folds_run": folds_run, "days_written": len(daily_updates)}
```

- [ ] **Schritt 4: `__main__`-Block anpassen (Rueckgabewert-Key hat sich geaendert: `entries_written` -> `days_written`)**

Suche nach `result['entries_written']` im `if args.backfill is not None:`-Zweig
und aendere zu `result['days_written']`.

- [ ] **Schritt 5: Tests anpassen**

Bestehender Test `BackfillPredictionLogTests.test_returns_zero_without_credentials`
muss auf den neuen Rueckgabewert angepasst werden:
```python
class BackfillPredictionLogTests(unittest.TestCase):
    def test_returns_zero_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            result = backfill_prediction_log(90)
        self.assertEqual(result, {"folds_run": 0, "days_written": 0})
```
Neuer Test fuer `_build_candidates`:
```python
class BuildCandidatesTests(unittest.TestCase):
    def test_random_forest_matches_live_hyperparameters(self):
        candidates = _build_candidates()
        self.assertEqual(candidates["RandomForest"].n_estimators, 500)
        self.assertIn("HistGradientBoosting", candidates)
```

- [ ] **Schritt 6: Tests laufen lassen (NUR Mocks, KEIN echter Firestore-/Kickbase-Call)**

```
python3 -m unittest discover -s tests -v
```

- [ ] **Schritt 7: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "backfill_prediction_log: schreibt Tages-Aggregate direkt, geteilte Hyperparameter mit Live-Modell"
```

---

### Task 4: `index.html` — Header-Klarstellung synthetischer Sieger vs. Live-Modell

**Files:** Modify: `index.html`

**Interfaces:** Konsumiert: `DATA.ml_metrics.synthetic_winner` (neu, aus Task 2).

- [ ] **Schritt 1: Bestehenden Header-Einzeiler klarstellen**

Suche nach der Zeile mit `ML-Modell: R²=${DATA.ml_metrics.r2}, Richtung
korrekt ${DATA.ml_metrics.sign_accuracy}%` (in `renderMeta()` oder
aehnlicher Stelle). Diese Werte kommen aus `per_model_metrics[synthetic_winner]`
(synthetischer Split-Sieger), waehrend `DATA.ml_metrics.model_type` das
LIVE gewaehlte Modell zeigt — die koennen auseinanderlaufen. Ergaenze den
Text um eine Klarstellung, z.B.:

Von (sinngemaess, exakten Code an der Fundstelle pruefen):
```javascript
parts.push(`ML-Modell: R²=${DATA.ml_metrics.r2}, Richtung korrekt ${DATA.ml_metrics.sign_accuracy}%`);
```
Zu:
```javascript
parts.push(`ML-Modell (synth. Split, ${DATA.ml_metrics.synthetic_winner ?? DATA.ml_metrics.model_type}): R²=${DATA.ml_metrics.r2}, Richtung korrekt ${DATA.ml_metrics.sign_accuracy}%`);
```
(Fallback auf `model_type` falls `synthetic_winner` mal fehlt, z.B. bei
einem alten/degradierten Snapshot vor diesem Fix.)

- [ ] **Schritt 2: "ML-Genauigkeit"-Tab — Kopf-an-Kopf-Karte pruefen/ergaenzen**

Falls die Kopf-an-Kopf-Karte (aus der vorherigen Session, `renderMlGenauigkeit()`)
den Begriff "Live" bereits fuer `DATA.ml_metrics.model_type` verwendet
(sollte laut vorherigem Task schon der Fall sein), reicht das — nur
sicherstellen, dass klar zwischen "live gewaehlt" (Tab) und "synthetischer
Split von heute" (Header) unterschieden wird. Falls die Karte den
synthetischen Sieger noch gar nicht zeigt, optional ergaenzen (z.B. kleiner
Hinweis "Synthetischer Tages-Sieger: X" neben der Live-Anzeige) — nicht
zwingend, nur falls es sich organisch ergaenzen laesst ohne die Karte zu
ueberladen.

- [ ] **Schritt 3: Syntax-Check**

`<script type="module">`-Bloecke extrahieren, `node --check`.

- [ ] **Schritt 4: Tests laufen lassen**

```
python3 -m unittest discover -s tests -v
```

- [ ] **Schritt 5: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add index.html
git commit -m "Dashboard-Header: synthetischen Split-Sieger von live gewaehltem Modell unterscheiden"
```

---

### Task 5: Docstring-Cleanup + HANDOFF.md + Abschluss-Verifikation

**Files:** Modify: `src/market_predictor.py`, `src/firestore_db.py`, `HANDOFF.md`

- [ ] **Schritt 1: Veraltete Docstrings/Kommentare korrigieren**

- `src/market_predictor.py:1-3` (Modul-Docstring): "siehe `_train_and_evaluate`"
  fuer die Modellwahl-Erklaerung — jetzt praeziser: Modellwahl passiert in
  `_select_live_model`, `_train_and_evaluate` liefert nur die Kandidaten.
- `src/market_predictor.py:22-29` (Modul-Docstring): "Vollstaendig transient
  ... Einzige Ausnahme: data/ml_prediction_log.jsonl" — nicht mehr ganz
  akkurat, Firestore ist jetzt die primaere Quelle fuer Genauigkeits-
  Auswertung/Trend (`ml_accuracy_daily`), die lokale Datei ist nur noch
  Fallback/Staging. Kurz anpassen.
- `src/market_predictor.py` (`_walk_forward_backtest`-Docstring): Verweis
  auf `_evaluate_realized_accuracy` (Funktion existiert seit dieser
  Session nicht mehr unter dem Namen) — auf `_realized_by_model_from_daily`
  oder allgemeiner "dem Live-Log" umformulieren.
- `src/firestore_db.py` (Modul-Docstring, Zeile ~14-16): "`ml_prediction_log`
  ... dort liegt die Historie in data/ml_prediction_log.jsonl" — nicht
  mehr korrekt, `ml_accuracy_daily` ist jetzt die primaere Historie-Quelle,
  `ml_prediction_log` nur kurzlebige Staging-Zone. Kurz anpassen.

- [ ] **Schritt 2: `HANDOFF.md` aktualisieren**

Phase-4-Abschnitt um den Quota-Fix ergaenzen: neue Collection
`ml_accuracy_daily`, warum (Read-Quota-Vorfall), dass die externe
Snapshot-Form unveraendert blieb (kein Dashboard-Breaking-Change),
Hyperparameter-Fix (Backfill nutzt jetzt dieselben Parameter wie Live),
Header-Klarstellung. **Wichtig**: explizit vermerken, dass diese ganze
Aenderung HEUTE NUR per Unit-Tests (Mocks) verifiziert wurde, KEIN echter
Firestore-Lauf — die eigentliche Live-Verifikation (inkl. Rest-Backfill)
ist fuer morgen vorgesehen. Resume Instructions entsprechend ergaenzen:
morgen ZUERST einen `FIRESTORE_ENABLED=1 python -m src.dashboard_export`-
Testlauf machen und pruefen dass `ml_accuracy_daily` befuellt wird UND
die Read-Zahl (`gh api` oder Firebase-Console-Nutzungs-Tab) deutlich
niedriger ausfaellt als vorher, BEVOR der Rest-Backfill (`--backfill 15`
mehrfach) angestossen wird.

- [ ] **Schritt 3: Finale Verifikation (NUR Unit-Tests, KEIN Firestore-Call)**

```
python3 -m unittest discover -s tests -v
```
Erwartung: alle gruen.

- [ ] **Schritt 4: Commit — NUR COMMITTEN, NICHT PUSHEN**

```bash
git add src/market_predictor.py src/firestore_db.py HANDOFF.md
git commit -m "Docstrings aktualisieren, HANDOFF.md: Firestore-Read-Quota-Fix dokumentieren"
```

## Verifikation (Gesamt)

- `python3 -m unittest discover -s tests -v` — alle Tests gruen.
- **KEIN** echter Firestore-Call in dieser gesamten Session-Fortsetzung
  (User-Vorgabe nach dem Quota-Vorfall) — Live-Verifikation folgt morgen.
- `metrics["accuracy_trend"]`/`metrics["realized_by_model"]` haben
  identische Form wie vorher (kein Downstream-Breaking-Change fuer
  `dashboard_export.py`/`index.html`, ausser der bewussten Header-
  Klarstellung in Task 4).
- `node --check` fuer `index.html` fehlerfrei.
