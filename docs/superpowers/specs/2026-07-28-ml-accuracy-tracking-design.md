# ML-Genauigkeit tracken + datengetriebene Modellwahl (Phase 4)

## Warum

Laut Original-Spec (`2026-07-27-kickbase-firestore-dashboard-design.md`,
Phase 4) sollte die jetzt in Firestore abfragbare `ml_prediction_log`-
Historie eine Genauigkeits-Trend-Anzeige und perspektivisch eine
datengetriebene Modell-/Hyperparameter-Wahl ermoeglichen — bisher nur als
Kurzabsatz skizziert, hier konkret ausgearbeitet.

**Wichtiger Fund waehrend der Recherche**: `market_predictor.py::
_load_prediction_log()` liest aktuell NUR aus der lokalen
`data/ml_prediction_log.jsonl`. Seit der `dashboard.yml`-Aenderung dieser
Session (kein `git commit`/`push` der lokalen DB mehr, da Firestore die
einzige noetige Datenquelle ist) persistiert diese lokale Datei NICHT mehr
zwischen CI-Laeufen — jeder 2h-Lauf startet mit demselben eingefrorenen
Datei-Stand. `_evaluate_realized_accuracy()` (Tag-fuer-Tag-Genauigkeit
gegen echte Marktwert-Aenderungen) laeuft dadurch in Produktion vermutlich
leer/verzerrt. Diese Aenderung fixt das nebenbei (Read-Pfad auf Firestore
umstellen).

## Scope (User-Entscheidungen aus Brainstorming)

1. **Nicht nur Sichtbarkeit** — auch die taegliche Live-Modellwahl soll
   auf echter Firestore-Historie basieren, nicht mehr nur auf dem
   taeglichen synthetischen 75/25-Split.
2. **Beide Modelle taeglich loggen** (RandomForest UND
   HistGradientBoosting), nicht nur der Tagessieger — ermoeglicht echten
   Kopf-an-Kopf-Vergleich ueber die Zeit.
3. **Trailing-Fenster-Auswahl mit Fallback**: sobald genug echte
   Realdaten vorliegen, gewinnt das Modell mit besserer realer
   `sign_accuracy` im Trailing-30d-Fenster; in der Kaltstart-Phase
   (zu wenig Historie) faellt die Auswahl auf den heutigen synthetischen
   Split zurueck wie bisher.
4. **Einmaliger Backfill**: die letzten bis zu 90 Tage (begrenzt durch
   verfuegbare Kickbase-Historie + genug Trainingsdaten je Cutoff) werden
   per Walk-Forward-Mechanismus rueckwirkend berechnet und als echte
   Log-Eintraege nach Firestore geschrieben, damit die Trailing-Fenster-
   Auswahl nicht 90 echte Kalendertage abwarten muss. Bleibt als
   dauerhafte Utility-Funktion im Code (kein Wegwerf-Skript), falls die
   Firestore-Historie spaeter mal zurueckgesetzt werden muss.
5. **Neuer Dashboard-Tab "ML-Genauigkeit"** (nicht der bestehende
   Header-Einzeiler) mit Kopf-an-Kopf-Uebersicht + Trend-Chart.

## Datenmodell-Aenderung: `ml_prediction_log`

**Doc-Id-Schema aendert sich** von `{date}_{player_id}` auf
`{date}_{player_id}_{model_type}` (`model_type` ∈
`{"RandomForest", "HistGradientBoosting"}`). Jeder Log-Eintrag bekommt ein
neues Feld `model_type`.

Alte Eintraege aus dieser Session (Test-Firestore-Schreibvorgaenge waehrend
Entwicklung, altes Schema) bleiben unangetastet liegen — harmloser
Datenmuell, keine Migration noetig (kleine Datenmenge, keine Konsumenten
lesen das alte Schema mehr nach diesem Wechsel).

`firestore_db.py`:
- **Neu**: `get_prediction_log_entries(client: firestore.Client) -> list[dict]`
  — liest die komplette `ml_prediction_log`-Collection (kein Datumsfilter
  noetig, Datenmenge bleibt ueberschaubar: ~450 Spieler × 2 Modelle ×
  max. ~1 Jahr Trailing-Retention).
- `upsert_prediction_log_entries()` bleibt strukturell gleich (nimmt
  weiterhin eine Liste von Dicts, Doc-Id-Bildung wandert von
  `{date}_{player_id}` auf `{date}_{player_id}_{model_type}`).

`market_predictor.py`:
- `_load_prediction_log()`: bei `FIRESTORE_ENABLED` liest von Firestore
  (`firestore_db.get_prediction_log_entries`) statt/zusaetzlich zur
  lokalen Datei. Lokale JSONL bleibt bestehen als Offline-/Lokal-Dev-
  Fallback (gleiches `FIRESTORE_ENABLED`-Gating-Pattern wie ueberall
  sonst im Projekt) — kein kompletter Ersatz, additiv.
- `_train_and_evaluate()`: trainiert weiterhin taeglich beide Modelle
  (unveraendert), liefert wie bisher Metriken fuer BEIDE Kandidaten (nicht
  nur den synthetischen Sieger) an den Aufrufer zurueck, damit beide
  Prognosen geloggt werden koennen.
- `_append_todays_predictions()`: schreibt jetzt fuer JEDEN Spieler ZWEI
  Eintraege (einen pro Modell), nicht nur die Prognose des heutigen
  Siegers.
- `_evaluate_realized_accuracy()`: wird pro `model_type` getrennt
  ausgewertet (aktuell nur "der jeweilige Tagessieger, egal welches
  Modell das war") — liefert `{"RandomForest": {...}, "HistGradientBoosting": {...}}`
  je Trailing-Fenster (7d/30d, `ACCURACY_WINDOWS_DAYS` bleibt).
- **Neue Auswahl-Funktion** `_select_live_model(realized_by_model, synthetic_metrics) -> tuple[str, str]`
  (Modellname, Auswahl-Grund): prueft ob beide Modelle im 30d-Fenster
  genug Datenpunkte haben (Schwelle: `MIN_REALIZED_SAMPLES_FOR_SELECTION = 14`,
  neue Konstante neben `ACCURACY_WINDOWS_DAYS`); wenn ja, nimmt das Modell
  mit hoeherer realer `sign_accuracy`; sonst faellt auf
  `synthetic_metrics["model_type"]` zurueck (heutiges Verhalten).
  `predict_market_value_changes()` nutzt das Ergebnis, um zu entscheiden,
  welches der beiden bereits trainierten Modelle fuer die tatsaechliche
  Live-Prognose (`model.predict(today_df[FEATURES])`) verwendet wird.
  `metrics["model_type"]` und ein neues `metrics["selection_reason"]`
  (`"realized_trailing_30d"` / `"synthetic_split_fallback"`) werden
  zurueckgegeben.

## Backfill-Utility

Neue Funktion `market_predictor.backfill_prediction_log(days: int = 90) -> dict`:

- Baut den Corpus wie gewohnt (`_build_corpus`/`_engineer_features`).
- Laeuft analog zu `_walk_forward_backtest()`, aber mit bis zu `days`
  Cutoff-Tagen (statt der fest verdrahteten `BACKTEST_FOLDS = 6`) — real
  begrenzt durch: wie viele distincte Tage `history_df` hat UND wie viele
  davon genug Trainingszeilen (`BACKTEST_MIN_TRAIN_ROWS`) VOR sich haben.
  Frueheste Tage im ~365-Tage-Fenster fallen typischerweise raus (zu wenig
  Trainingshistorie davor), betrifft aber nicht die juengsten ~90 Tage.
- Pro Fold/Modell: statt nur aggregiertem `sign_hits`/`abs_errors` werden
  jetzt echte Pro-Spieler-`predicted_delta`-Werte gesammelt (`y_pred`
  liegt schon vor, muss nur mit `player_id` gezippt und behalten werden
  statt nur in die Aggregat-Listen zu wandern).
- Schreibt alle gesammelten Eintraege in EINEM
  `firestore_db.upsert_prediction_log_entries()`-Aufruf (Batching
  uebernimmt `_write_in_batches`, kein manuelles Chunking noetig).
- Aufruf: `python -m src.market_predictor --backfill 90` (neues
  `argparse`-basiertes CLI-Flag im `if __name__ == "__main__":`-Block,
  Default-Verhalten ohne Flag bleibt der normale taegliche Lauf
  unveraendert).
- Rueckgabewert `{"folds_run": int, "entries_written": int}` fuer
  Terminal-Ausgabe/Verifikation.

## Dashboard: neuer Tab "ML-Genauigkeit"

**Backend** (`dashboard_export.py`): neue Funktion
`_build_ml_accuracy_trend(log_entries, mv_lookup) -> dict` — nutzt die
volle Firestore-Historie (nicht nur "heute" wie
`_evaluate_realized_accuracy`), berechnet pro Kalendertag (oder pro Woche
bei laengerer Historie, um die Punktezahl im Chart handhabbar zu halten)
und pro `model_type` die realisierte `sign_accuracy`, liefert eine
Zeitreihe plus die aktuelle Trailing-30d-Kopf-an-Kopf-Zusammenfassung
(gleiche Rohdaten wie `_select_live_model` nutzt, hier nur zur Anzeige
aufbereitet, keine zweite Berechnungslogik). In `data["ml_accuracy_trend"]`
eingehaengt.

**Frontend** (`index.html`): neuer Tab "ML-Genauigkeit" analog zu den
bestehenden Tabs — `renderMlGenauigkeit()`, eingehaengt in `renderAll()`
und `updateTabBadges()`. Inhalt:
- Kopf-an-Kopf-Karte: aktuell aktives Modell + Auswahl-Grund
  (`selection_reason`), Trailing-30d `sign_accuracy`/MAE beider Modelle
  nebeneinander.
- Trend-Chart (`sign_accuracy` beider Modelle ueber die Zeit) — **vor dem
  eigentlichen Chart-Code wird das `dataviz`-Skill geladen**, damit Form/
  Farben konsistent zum Rest des Dashboards bleiben (bisher gibt es noch
  keinen Chart in diesem Projekt, erster dieser Art).

## Nicht Teil dieser Aenderung

- Hyperparameter-Tuning der beiden Modell-Kandidaten selbst (nur WELCHES
  Modell gewaehlt wird, nicht WIE es konfiguriert ist) — waere ein
  separates, groesseres Thema.
- Automatisches Nachziehen/Aktualisieren des Backfills bei jedem Lauf —
  einmalige Utility, kein Teil des taeglichen Pipeline-Flows.
- Aufraeumen der alten Log-Eintraege im alten Schema — bewusst liegen
  gelassen (siehe Datenmodell-Abschnitt).

## Verifikation

1. Neue/angepasste Unit-Tests: `_select_live_model` (Kaltstart-Fallback
   vs. genug Daten -> Realwert-Sieger), `_build_ml_accuracy_trend`
   (Fixture-Log-Eintraege -> erwartete Zeitreihe/Kopf-an-Kopf-Werte),
   `firestore_db.get_prediction_log_entries`/`upsert_prediction_log_entries`
   (neues Doc-Id-Schema, MagicMock-Muster wie bestehende Tests).
2. `python3 -m unittest discover -s tests -v` — alle gruen.
3. Lokaler Backfill-Testlauf: `FIRESTORE_ENABLED=1
   GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json
   python3 -m src.market_predictor --backfill 90` — Ausgabe zeigt
   plausible `folds_run`/`entries_written`, Firestore-Console zeigt neue
   `ml_prediction_log`-Dokumente im neuen Schema.
4. Lokaler Dashboard-Export-Testlauf, `data["ml_accuracy_trend"]` im
   Ergebnis vorhanden und plausibel befuellt.
5. Browser-Test (User): neuer Tab "ML-Genauigkeit" zeigt Kopf-an-Kopf-
   Karte + Trend-Chart mit den Backfill-Daten.
