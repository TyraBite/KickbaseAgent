# 3-Tage-Modell Hyperparameter-Suche — Ergebnis

> Ergänzt `docs/superpowers/plans/2026-08-01-ml-3d-tuning.md` (Implementierung des Suchskripts). Dieses Dokument hält das Ergebnis des vollständigen Laufs fest — für spätere Referenz, falls die 3-Tage-Hyperparameter nochmal angefasst werden.

## Ablauf

- **Kurzer Check** (1.5h, `TUNING_BUDGET_HOURS=1.5`): 3 von 400 Konfigurationen getestet, kein Gewinner — aber auch keine verlässliche Aussage, da eine einzelne LightGBM-Konfiguration durch eine (später als Anomalie identifizierte, nicht reproduzierbare) Verlangsamung fast das komplette Budget aufgebraucht hat. Diagnose (separates Skript, nicht committed) zeigte: dieselbe Konfiguration lief beim erneuten Test in 93s statt 70.5min — kein inhärentes Problem der Konfiguration oder Daten, sondern eine einmalige Ressourcen-Anomalie in der Sandbox.
- **Langer Lauf** (11h Budget, `TUNING_BUDGET_HOURS=11`, gestartet 2026-08-01 19:11 UTC): **325 von 400 Konfigurationen** getestet, dann durch die Sicherheitsmarge (`letzte Konfig * 1.3 > verbleibendes Budget`) sauber beendet — 10.76h tatsächliche Laufzeit. Rohes Log (nicht committed, `tuning-results/` ist gitignored): `tuning-results/target3d.log`, 2284 Zeilen.

## Baseline (aktuelle, geteilte `_build_candidates()`-Config gegen `TARGET_3D`, davor nie gemessen)

| Modell | Sign-Accuracy | MAE | Fold-Std | Folds |
|---|---|---|---|---|
| RandomForest (n_estimators=500, max_depth=20, min_samples_split=5, min_samples_leaf=2, max_features=sqrt) | 82.4% | 93224 | 5.7p | 28/30 |
| HistGradientBoosting (learning_rate=0.05, max_iter=200, max_leaf_nodes=127, min_samples_leaf=20, l2=0.0) | 82.6% | 91231 | 5.6p | 28/30 |

(2 von 30 Folds fehlen strukturell — die letzten 2 Tage der Historie kennen ihren 3-Tage-Ausgang noch nicht, siehe NaN-Tail-Schutz im Skript.)

## Kriterium (aus dem Tuning-Plan, identisch zur bereits erfolgreichen 1-Tages-Suche)

Eine Konfiguration gilt als "besser", wenn **Sign-Accuracy ≥ Baseline+1pt UND MAE ≤ Baseline** (gegen die jeweils relevante Baseline).

## Ergebnis: kein Gewinner (nach Korrektur — siehe unten, ursprünglich ANDERS eingeschätzt)

Von 325 getesteten Konfigurationen erfüllten auf den ersten Blick **5** das Kriterium — alle RandomForest mit `max_depth=None` (unbegrenzte Tiefe) **und** `min_samples_leaf=1`, angeführt von `n_estimators=800, min_samples_split=2, min_samples_leaf=1, max_features="sqrt", max_depth=None` mit **86.6% / MAE 91060** (klar über beiden Baselines). Dieser Fund wurde zunächst in `src/market_predictor.py` übernommen (Commit `8fb8837`) — **und danach wieder zurückgenommen** (Commit `bfa5b19`, Revert), nachdem eine finale Code-Review + eine gezielte Nachmessung zeigten: das Ergebnis war überwiegend ein Artefakt der Eval-Methodik, kein echter Gewinn.

### Was die finale Review fand

Eine unabhängige Review der Integration (opus-Modell) fand einen plausiblen Daten-Leck-Mechanismus in der Walk-Forward-Auswertung selbst (identisch in `market_predictor.py::_walk_forward_backtest()` und im — inzwischen entfernten — Tuning-Skript): eine Trainingszeile mit Datum `cutoff-1` trägt beim 3-Tage-Ziel das Label `mv[cutoff+2] - mv[cutoff-1]` — kodiert also Marktwerte **zwei Tage nach dem Test-Cutoff**. Bei genug Baumtiefe (hier: `max_depth=None`) kann ein Random Forest eine Testzeile in ein Blatt routen, das von genau dieser (bereits "zukunftswissenden") Trainingszeile desselben Spielers dominiert wird — über die spielerspezifische Autokorrelation der Features, nicht über echtes generalisierbares Signal. Beim 1-Tages-Ziel existiert dieses Leck nicht (eine `cutoff-1`-Zeile beschreibt `cutoff-1 → cutoff`, und `mv[cutoff]` ist zum Test-Zeitpunkt bereits bekanntes Feature).

Indizien aus dem Log, die für Leck statt echte Verbesserung sprachen:
- **Bimodale Verteilung mit leerer Lücke**: 317/325 Konfigurationen bei 81.3–82.8%, 8 bei 85.2–86.6%, **nichts dazwischen**. Echte, kapazitätsgetriebene Verbesserungen sehen graduell aus, nicht wie ein Schalter.
- **`min_samples_leaf=1` allein bewirkt nichts** — mit `max_depth=30` liegt es bei 82.2–82.4%; erst mit `max_depth=None` springt es auf 85.2–86.6%. Der gesamte Gewinn steckt in Splits tiefer als 30 — genau den Splits, die einzelne Trainingszeilen isolieren.
- **Der Gewinner ist nicht mal die beste MAE** — XGBoost erreichte MAE 89772 bei 82.4% Accuracy. Der Gewinn ist fast rein Richtungs-Genauigkeit — genau das, was ein überlappendes Label-Fenster am direktesten verrät.

### Entscheidender Test: Embargo-Nachmessung

Auf Vorschlag der Review wurden Baseline und Gewinner erneut gemessen, diesmal mit einem **Embargo** (Trainingszeilen innerhalb von `horizon_days` vor dem Cutoff werden ausgeschlossen — entfernt genau das überlappende Label-Fenster):

| Konfiguration | ohne Embargo | mit Embargo | Δ Accuracy |
|---|---|---|---|
| Baseline (1-Tages-getunt) | 83.1% / MAE 85525 | 82.8% / MAE 92739 | −0.3pt |
| Gewinner (800/None/1/2/sqrt) | 86.9% / MAE 84256 | **84.1% / MAE 93707** | **−2.8pt** |

(Absolutwerte weichen leicht vom ursprünglichen Lauf ab — der Corpus ist zwischen den Läufen um ~43 Zeilen gewachsen, echte neue Tagesdaten, verschiebt das 30-Fold-Fenster leicht. Die Embargo-vs-ohne-Vergleiche INNERHALB dieses einen Laufs sind die relevante Größe.)

Die Baseline verliert unter Embargo nur wenig (−0.3pt — der normale Preis dafür, die jüngsten Trainingsdaten zu verlieren). Der Gewinner verliert **etwa 9x so viel** (−2.8pt) — genau das erwartete Muster, wenn ein Teil seines scheinbaren Vorsprungs aus dem Leck stammt, das die Baseline (durch begrenzte Tiefe) gar nicht ausnutzen kann.

**Fairer Vergleich (beide mit Embargo, das korrekte Bild):** Gewinner 84.1% / MAE 93707 vs. Baseline 82.8% / MAE 92739 — Accuracy liegt knapp über der Schwelle (+1.3pt), aber **MAE ist SCHLECHTER** (93707 > 92739) statt besser. Das Kriterium (Accuracy≥Baseline+1pt UND MAE≤Baseline) ist unter fairer Messung **nicht erfüllt** — der ursprüngliche 86.6%/91060-Fund war überwiegend Leck, kein echter, kriteriums-erfüllender Gewinn.

### Konsequenz

- Commit `8fb8837` (Produktions-Integration) wurde per `git revert` zurückgenommen (Commit `bfa5b19`) — `_build_candidates()` bleibt horizon-unabhängig, wie vorher.
- `src/experiment_target3d_tuning.py` bleibt trotzdem entfernt (`git rm`, Commit `51b80fe`) — Nutzer-Vorgabe, unabhängig vom Ergebnis, analog zu allen anderen `experiment_*.py`-Dateien dieses Repos.
- Kein neuer Analyse-Code wurde committed (Embargo-Check war ein Wegwerf-Skript, wie die Diagnosen davor).

### Wichtiger Folge-Fund: das Leck existiert auch in der PRODUKTIVEN Auswertung

Der beschriebene Mechanismus ist nicht auf das Tuning-Skript beschränkt — `market_predictor.py::_walk_forward_backtest()` hat für `horizon_days=3` **kein Embargo**, exakt dieselbe Schwäche. Das bedeutet: die bereits LIVE angezeigte `ml_metrics_3d`/3-Tage-Genauigkeit im Modell-Tracking-Tab (frisch im Frontend sichtbar gemacht, siehe `docs/superpowers/plans/2026-08-01-ml-horizonte-frontend-anzeige.md`) ist für den 3-Tage-Horizont vermutlich etwas zu optimistisch — unabhängig von diesem Tuning-Versuch, ein bereits bestehendes, bisher unbemerktes Problem. **Nicht in dieser Session behoben** — würde bereits live gemeldete Genauigkeits-Zahlen verändern, verdient eine eigene, bewusste Betrachtung (siehe HANDOFF.md "Not Yet Done").

## Lehre für zukünftige Versuche

Falls die 3-Tage-Hyperparameter nochmal angefasst werden: **zuerst das Embargo in die Eval-Methodik einbauen**, dann erst suchen — sonst wird jede unregularisierte/tiefe Modellvariante fälschlich bevorzugt. Das Aufsetzen des Embargos ist unabhängig von einer neuen Suche sinnvoll (siehe Folge-Fund oben).
