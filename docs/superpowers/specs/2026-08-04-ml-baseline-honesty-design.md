# ML-Prognose: ehrliche Baseline-Vergleiche + Embargo-/Clip-Fix — Design

## Kontext / Warum

Live-Check am 2026-08-04 (siehe HANDOFF.md, Firestore `feedback/current` als Auslöser
für den Fokus-Wechsel des Users): die gemeldete Richtungs-Trefferquote
(`ml_accuracy_trend`) klettert von ~58% (Mai) auf ~97% (August). Live-Nachrechnung
gegen echte Kickbase-Marktwert-Historie (60 Spieler, volle Saison) zeigt: eine
triviale Trägheits-Baseline ("morgen = gleiche Richtung wie gestern") trifft
konstant 90–99%, die ganze Saison über. Das ML-Modell hat die meiste Zeit
schlechter performt als dieser Ein-Zeilen-Trick und ihn erst ab Juni/Juli
eingeholt. Ursache vermutlich: frühe Walk-Forward-Folds trainieren mit kaum
mehr als `MIN_TRAINING_ROWS`, überanpassen sich mit den aktuell recht schweren
Modell-Parametern (RandomForest Tiefe 20/500 Bäume, HistGradientBoosting
200 Iterationen/127 Blätter) an Rauschen und verlieren dadurch gegen simple
Trägheit.

Zwei weitere, verwandte Bugs fallen in dieselbe Kategorie (beide bereits vorher
in `HANDOFF.md` als bewusst zurückgestellt vermerkt bzw. in dieser Session neu
gefunden) und werden in derselben Runde mitgefixt, weil sie dieselbe
Fold-Konstruktions-Logik betreffen:

- **Fehlendes Embargo bei Mehrtage-Horizonten** (`market_predictor.py::_walk_forward_backtest()`,
  bereits dokumentiert): ein Trainings-Tag kurz vor einem Cutoff hat bei
  `horizon_days=3` ein Label, das Marktwerte NACH dem Cutoff kennt.
- **Ziel-Clip-Leck** (neu gefunden 2026-08-04): `_engineer_features()` berechnet
  die IQR-Clip-Grenzen für `mv_target_clipped`/`mv_target_3d_clipped` einmal
  über den GESAMTEN Corpus (Vergangenheit + Zukunft relativ zu jedem
  Backtest-Cutoff), nicht nur aus der bis dahin bekannten Vergangenheit.

**Ziel dieser Session:** die Genauigkeits-Kennzahlen ehrlich machen (Baseline-
Vergleich, Trendwende-Metrik, Richtung/Betrag-Trennung) UND die beiden
Leak-Bugs beheben — in einem Zug, weil alle vier Änderungen dieselbe
Fold-Logik anfassen.

## Architektur

### Backend (`src/market_predictor.py`)

**Neue reine Helfer** (ersetzen dreifach dupliziertes Fold-Setup in
`_train_and_evaluate`, `_walk_forward_backtest`, `backfill_prediction_log`):

- `_clip_target(unclipped: pd.Series, train_mask: pd.Series) -> pd.Series`
  — berechnet IQR-Clip-Grenzen NUR aus `unclipped[train_mask]`, wendet sie auf
  die gesamte Serie an. `_engineer_features()` liefert ab jetzt nur noch die
  **ungeklippten** `mv_target`/`mv_target_3d` — kein globaler Clip mehr dort.
  Jeder der drei Aufrufer klippt selbst, direkt vor `.fit()`, mit den
  Grenzen aus seinem eigenen `train`-Split.

- `_score_predictions(y_actual, y_pred, baseline_pred) -> dict` — zentrale
  Metrik-Berechnung, gibt zurück:
  - `sign_accuracy`, `mae` (wie bisher, unverändert im Verhalten)
  - `mae_given_correct_sign` (NEU: MAE nur über Zeilen mit richtigem
    Vorzeichen; `None`/kein Feld wenn keine solche Zeile existiert)
  - `baseline_sign_accuracy`, `baseline_mae` (Trägheits-Baseline:
    `baseline_pred` = `mv_change_1d` für den 1-Tage-Horizont bzw.
    `mv_change_3d` für 3 Tage — beide Spalten existieren schon, kein neuer
    Fetch)
  - `reversal_sign_accuracy`, `reversal_n` (Modell-Trefferquote NUR auf
    Zeilen, wo die Baseline falsch lag — die "schweren" Fälle; `None`-Werte
    bei `reversal_n == 0`)

- **Gemeinsamer Fold-Runner** für `_walk_forward_backtest`/`backfill_prediction_log`:
  eine Funktion, die für eine Liste von Cutoffs pro Cutoff (a) bei
  `horizon_days > 1` die letzten `horizon_days` Tage vor dem Cutoff aus
  `train` entfernt (Embargo-Fix), (b) `_clip_target` anwendet, (c) beide
  Modell-Kandidaten fitted, (d) `_score_predictions` aufruft. Unterschied
  zwischen den beiden Aufrufern bleibt nur: welche Cutoff-Liste (letzte
  `BACKTEST_FOLDS` vs. bis zu `days`) und was mit den Pro-Fold-Ergebnissen
  passiert (aggregiert zu einem Gesamt-Ergebnis vs. einzeln nach
  `ml_accuracy_daily` geschrieben).

**Live-Pfad** (`_build_daily_accuracy_updates`): bekommt dieselbe
Baseline-Berechnung (Baseline-Vorhersage aus `mv_lookup` ableitbar: Differenz
zum Vortag, kein neuer Rohdaten-Bedarf). Aggregiert pro Tag/Modell/Horizont
zusätzlich `baseline_sign_correct`, `baseline_abs_error_sum`,
`abs_error_sum_given_correct_sign`, `n_baseline_wrong`,
`model_sign_correct_when_baseline_wrong` — reine Summen/Counter, genau wie
die bestehenden Felder über Zeitfenster aufsummierbar.
`_summarize_from_daily`/`_realized_by_model_from_daily` leiten daraus
`baseline_sign_accuracy`, `baseline_mae`, `mae_given_correct_sign`,
`reversal_sign_accuracy`, `reversal_n` für die 7d/30d-Fenster ab (Division
nur wenn Nenner > 0, sonst `None`).

### Firestore-Schema

`ml_accuracy_daily`-Dokumente (`{date}_{model_type}_{horizon_days}`): 5 neue
Zahlenfelder wie oben. `ml_metrics`/`ml_metrics_3d`'s `per_model`-Block: die
5 abgeleiteten Kennzahlen zusätzlich zu den bestehenden (`rmse`, `mae`, `r2`,
`sign_accuracy` bleiben unverändert). Keine neue Collection, keine neuen
Docs/Tag.

**Migration**: alte Docs haben die neuen Felder nicht. Kein defensiver Code
dafür — nach Deploy einmalig `backfill_prediction_log(days=90)` erneut laufen
lassen (idempotente Doc-Ids, überschreibt komplette Historie vollständig).

### Frontend (`frontend/src/components/MlGenauigkeitTab.tsx`, `types.ts`, `lib/derive.ts`)

`types.ts`: die 5 neuen Felder in den entsprechenden Metrik-Interfaces ergänzen
(Rohdaten vom Backend, unverändert 1:1 durchgereicht).

`derive.ts`: jede Vergleichs-/Ableitungslogik (z.B. Differenz Modell- vs.
Baseline-Trefferquote in Prozentpunkten für den Delta-Badge) — reine Funktion,
kein Zugriff auf `Date.now()`.

`MlGenauigkeitTab.tsx`: pro Horizont-Kachel (1T/3T), zusätzlich zu den
bestehenden, unveränderten Zahlen:
- Baseline-Vergleich als Delta-Badge (z.B. "+12pp ggü. Trägheits-Annahme")
- Trendwende-Trefferquote MIT Stichprobengröße — denselben
  "geringe Datenbasis"-UI-Baustein wiederverwenden, der im Code für sowas
  schon existiert, kein neuer Schwellenwert
- MAE-bei-richtiger-Richtung neben dem bestehenden MAE, eigenes Label

Erklärtext (was Baseline/Trendwende bedeuten) ans Seitenende der Sektion.
Trend-Chart selbst bleibt in dieser Runde unverändert (nur die statischen
Kacheln bekommen die neuen Zahlen, kein Baseline-Verlauf im Chart — bewusst
kleinerer Scope).

## Testing

- `_clip_target`, `_score_predictions`: reine Funktionen, Unit-Tests mit
  handgerechneten Fixtures — `tests/test_market_predictor.py`.
- Embargo-Fix: Regressionstest mit synthetischem `history_df`, das bei
  `horizon_days=3` eine Zeile mit Zukunfts-Label knapp vor dem Cutoff enthält
  — muss aus `train` verschwinden; bei `horizon_days=1` bleibt sie drin.
  Test zuerst rot (reproduziert den Bug vor dem Fix), dann grün.
- Clip-Leck-Fix: Regressionstest, wo globale vs. Train-only-Quantile
  unterschiedliche Clip-Grenzen ergeben — Assert auf die Train-only-Grenzen.
- Gemeinsamer Fold-Runner: direkt getestet, nicht doppelt über beide
  Aufrufer.
- `_build_daily_accuracy_updates`/`_summarize_from_daily`: synthetischer
  `mv_lookup`, neue Felder korrekt befüllt/aufsummiert.
- Frontend: bestehenden CT-Test für `MlGenauigkeitTab` erweitern falls
  vorhanden, sonst neu anlegen (während der Plan-Erstellung gegen den
  echten aktuellen Testbestand verifizieren). Neue Elemente (Delta-Badge,
  Trendwende-Zeile+n, MAE-Split) müssen abgedeckt sein.
- Jeder neue/geänderte Test per Mutation-Check verifiziert.

## Rollout / Nach Abschluss (Haupt-Thread, nicht Subagent)

1. Merge → Heavy-Lauf erzwingen (`gh workflow run dashboard-marktwerte.yml`).
2. `backfill_prediction_log(days=90)` einmalig manuell laufen lassen
   (Skript-Datei, kein inline `python3 -c`).
3. Alte vs. neue 3T-Genauigkeit vergleichen (alte Werte bereits aus dieser
   Session bekannt), Ergebnis dem User explizit mitteilen — auch wenn's
   schlechter aussieht (CLAUDE.md-Pflicht, keine stille Korrektur).
4. `HANDOFF.md`: Embargo-Bug + Clip-Leck als erledigt entfernen, ggf. Notiz
   zur neu bewerteten 3T-Zahl ergänzen.

## Out of Scope (bewusst nicht Teil dieser Runde)

- Modell-Hyperparameter-Neuanpassung an die jetzt sichtbare
  Baseline-Schwäche in frühen Folds (z.B. adaptive Komplexität nach
  `train_rows`) — erst nach dieser Runde mit echten neuen Zahlen sinnvoll
  entscheidbar.
- Baseline-Verlauf im Trend-Chart (nur die statischen Kacheln in dieser
  Runde).
- Externe Signale, Modell-Neu-Tuning generell (siehe HANDOFF.md, bestehende
  User-Entscheidung, kein aktueller Auftrag).
