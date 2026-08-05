# 3-Tage-Modell Hyperparameter-Suche (embargo-korrekt) — Ergebnis

> Ergänzt `docs/superpowers/plans/2026-08-04-ml-3d-hyperparameter-tuning.md`. Dieses Dokument hält das
> Ergebnis des vollständigen Laufs fest — für spätere Referenz, falls die 3-Tage-Hyperparameter nochmal
> angefasst werden. Löst `docs/superpowers/plans/2026-08-01-ml-3d-tuning-results.md` ab: der damalige
> Lauf war durch das inzwischen gefixte Embargo-Leck kontaminiert (siehe dortiges Dokument) — dies ist
> der erste 3-Tage-Hyperparameter-Test unter tatsächlich korrekter Methodik.

## Ablauf

`TUNING_BUDGET_HOURS=11`, gestartet 2026-08-04 23:14 UTC, sauber beendet nach 324 Konfigurationen durch
die Sicherheitsmarge (`letzte_Config_Laufzeit × 1.3 > Restbudget`). Rohes Log (nicht committed,
`tuning-results/` ist gitignored): `tuning-results/target3d.log`.

**Suchraum, diesmal breiter als beim letzten Versuch:** RandomForest, HistGradientBoosting (sklearn,
Produktions-Dependency) sowie LightGBM und XGBoost (nur experimentell, `.venv-tuning/`, nie in
`requirements.txt` übernommen). Randomisierte Ziehung, roughly gleichmäßig über alle vier Familien
verteilt: RandomForest 67, HistGradientBoosting 98, LightGBM 79, XGBoost 80 Trials — keine Familie
wurde durch einen Bug systematisch benachteiligt (das war während der Implementierung selbst ein
gefundenes und gefixtes Risiko, siehe Technische Anmerkungen unten).

**Methodik-Fix gegenüber dem letzten Versuch:** `_walk_forward_backtest()` (`src/market_predictor.py`)
bekam zwei neue optionale Parameter, `candidates=` und `n_folds=`, sodass das Such-Skript exakt denselben
produktiven Eval-Code (inkl. Embargo, NaN-Tail-Schutz, Scoring) wiederverwendet statt ihn zu duplizieren
— genau die Duplikation, die letztes Mal das Leck verursacht hat, ist jetzt strukturell ausgeschlossen.

## Baseline (aktuelle, geteilte `_build_candidates()`-Config gegen `TARGET_3D`, 30-Fold, Embargo aktiv)

| Modell | Sign-Accuracy | MAE | Folds |
|---|---|---|---|
| RandomForest | 84.9% | 88.294,84 € | 28/30 |
| HistGradientBoosting | 84.5% | 87.987,73 € | 28/30 |

(2 von 30 Folds fehlen strukturell — die letzten 2 Tage der Historie kennen ihren 3-Tage-Ausgang noch
nicht, gleicher NaN-Tail-Schutz wie im Produktionscode.)

## Kriterium

Eine Konfiguration gilt als "besser", wenn **Sign-Accuracy ≥ Baseline+1pt UND MAE ≤ Baseline** (gegen
die jeweils relevante Baseline; identisch zum Kriterium der bereits erfolgreichen 1-Tages-Suche).
Tiebreaker bei mehreren Erfüllern: bessere `reversal_sign_accuracy` (Trendwenden-Trefferquote).

## Ergebnis: kein Gewinner

Von 324 getesteten Konfigurationen erfüllte **keine** das Kriterium.

**Bestes gefundenes MAE** (nicht qualifizierend): XGBoost, `learning_rate=0.03, max_depth=9,
n_estimators=300, min_child_weight=10, reg_lambda=1.0` — **86.417,61 € MAE** (−1,8% ggü. der besten
Baseline), aber nur **84.6% Sign-Accuracy** (Baseline HistGradientBoosting: 84.5%/87.987,73 €) — verfehlt
die geforderte +1pt-Accuracy-Schwelle deutlich (85.5% nötig). Ein reiner MAE-Gewinn ohne Accuracy-Gewinn
qualifiziert bewusst nicht (Schutz gegen ein Modell, das Betragsgenauigkeit auf Kosten der
Richtungsgenauigkeit optimiert — dieselbe Überlegung wie beim 1-Tages-Kriterium).

**Beste gefundene Trendwenden-Trefferquote:** RandomForest, `max_depth=25, max_features=0.7,
min_samples_leaf=2, min_samples_split=5, n_estimators=300` — 75.8% (Baseline: 71.5%/74.0%), bei
MAE 89.479,27 € (schlechter als beide Baselines) — auch das kein Gesamt-Gewinner nach Kriterium.

**Keine Konfiguration lag systematisch weit über der Baseline** — anders als beim kontaminierten
2026-08-01-Lauf (dort eine bimodale Verteilung mit einer isolierten Gruppe klar abgesetzter
"Gewinner", die sich als Leck-Artefakt herausstellte) verteilen sich alle 324 Ergebnisse dieses Mal
graduell um die Baseline herum, ohne verdächtige Sprünge — ein Indiz, dass hier kein Leck (mehr)
wirkt.

## Dependency-Schwelle (LightGBM/XGBoost)

Da keine Konfiguration überhaupt qualifizierte, kam die Schwelle (≥5% relative MAE-Verbesserung ODER
≥2pt Accuracy ggü. dem besten qualifizierenden sklearn-Kandidaten) nicht zur Anwendung — es gibt keinen
qualifizierenden Kandidaten, sklearn oder sonst, gegen den verglichen werden könnte.

## Konsequenz

- Keine Code-Änderung an den Live-Hyperparametern — die geteilte `_build_candidates()`-Config bleibt
  bestehen, jetzt mit echtem, embargo-korrekten Beleg, dass sie auch für `TARGET_3D` ein guter,
  schwer zu schlagender Punkt ist (324 Konfigurationen über 4 Modell-Familien getestet).
- `src/experiment_target3d_tuning.py` wird per `git rm` entfernt (etabliertes Repo-Muster,
  unabhängig vom Ergebnis).
- Die Signatur-Erweiterung von `_walk_forward_backtest()` (`candidates=`/`n_folds=`, Task 1 des
  Umsetzungsplans) bleibt bestehen und wird gemergt — generisch nützliche, getestete Infrastruktur für
  eine spätere Suche, unabhängig vom Ausgang dieses konkreten Laufs.
- Firestore-Lesequota war zum Startzeitpunkt des Laufs erschöpft (429 auf allen drei
  Event-Collections) — der Corpus wurde deshalb mit `fitness_events=0, starting_rank_events=0,
  news_events=0` gebaut (6 von 15 FEATURES-Spalten liefen für den gesamten Lauf auf konstante
  Cold-Start-Platzhalter). Baumbasierte Modelle ignorieren varianzlose Features praktisch folgenlos
  beim Splitten, daher wird das Ergebnis als gültig für die verbleibenden 9 Features eingestuft — aber
  als Randbedingung hier festgehalten, falls das Ergebnis je reproduziert oder in Frage gestellt wird.

## Lehre für zukünftige Versuche

Die `candidates=`/`n_folds=`-Erweiterung von `_walk_forward_backtest()` ist der richtige Weg für jede
zukünftige Suche (1-Tage oder 3-Tage) — kein neues Experiment-Skript sollte mehr eigene
Embargo-/Scoring-Logik mitbringen. Vor einer größeren Firestore-lastigen Suche außerdem die
Tages-Quota (50k Reads/20k Writes/20k Deletes, Reset Mitternacht Pacific Time) gegen bereits an diesem
Tag verbrauchtes Kontingent prüfen (siehe CLAUDE.md, „Firestore-Reads/Writes/Deletes sind ein Budget").
