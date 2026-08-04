# 3-Tage-Modell: embargo-korrekte Hyperparameter-Suche — Design

## Context

`docs/superpowers/specs/2026-08-04-ml-baseline-honesty-design.md` (diese Session) hat den Embargo-Fix in
`_walk_forward_backtest()`/`_train_and_evaluate()`/`backfill_prediction_log()` eingebaut und die live gezeigten
3-Tage-Kennzahlen ehrlich neu gemessen: Richtungsgenauigkeit blieb nahezu unverändert, aber MAE liegt jetzt
(korrekterweise, ohne Clip-Leck) 10-12% höher als bisher gezeigt (RandomForest 82.386€→91.015€, HistGradientBoosting
79.718€→89.657€, jeweils `realized_30d`). User möchte die verfügbare Zeit (~11h) nutzen, um die Modelle für den
3-Tage-Horizont gezielt auf MAE zu verbessern.

**Vorgeschichte:** `docs/superpowers/specs/2026-08-01-ml-3d-tuning-design.md` /
`docs/superpowers/plans/2026-08-01-ml-3d-tuning-results.md` dokumentieren einen bereits gelaufenen Versuch
(325 Konfigurationen, 10.76h). Der scheinbare Gewinner (RandomForest, `max_depth=None`, `min_samples_leaf=1`,
86.6% / MAE 91060) stellte sich bei genauerem Hinsehen als Artefakt **genau des Embargo-Lecks** heraus, das diese
Session gefixt hat — fair (mit Embargo) gemessen: 84.1% / MAE 93707, schlechter als die damalige Baseline
(82.8% / MAE 92739) beim MAE. Kein Gewinner wurde übernommen. Seitdem läuft der 3-Tage-Horizont weiter mit den
**für den 1-Tages-Horizont** getunten Hyperparametern (`_build_candidates()`, horizon-unabhängig) — nie dediziert
für `TARGET_3D` unter korrekter Methodik gemessen. Dieses Vorhaben holt das nach, jetzt wo das Embargo im
produktiven Code selbst existiert.

**Unterschied zum letzten Versuch:** letztes Mal war die Ergebnis-Übernahme explizit NICHT Teil des Vorhabens
("eigener Folge-Task"). Dieses Mal ist die Übernahme (falls ein Gewinner das Kriterium erfüllt) Teil des Plans —
User möchte den ganzen Zyklus (Suche → Entscheidung → Produktions-Code → PR → Backfill/Heavy-Lauf) in dieser
Session durchlaufen.

## Nicht-Ziele

- Keine Suche für den 1-Tages-Horizont (bereits abgeschlossen, 277 Konfigurationen, Embargo bei `horizon_days=1`
  ohnehin ein No-Op — nicht vom damaligen Leck betroffen).
- Kein neues Feature-Engineering — `FEATURES` bleibt unverändert, nur Hyperparameter der bestehenden Kandidaten
  (plus zwei neue, rein experimentelle Kandidaten-Familien, siehe unten).
- Keine dauerhafte neue Produktions-Dependency, außer eine der neuen Kandidaten-Familien gewinnt **klar** (siehe
  Kriterium unten) — der Normalfall bleibt reines sklearn.

## Architektur

**Kernentscheidung, die den letzten Versuch strukturell abgesichert hätte:** `_walk_forward_backtest()` bekommt
einen neuen optionalen Parameter `candidates: dict[str, object] | None = None` (Default: `None` → wie bisher
`_build_candidates(horizon_days)` intern aufrufen). Das Tuning-Skript ruft **dieselbe** Funktion mit einem
einzelnen Test-Kandidaten auf (`_walk_forward_backtest(history_df, target_col=TARGET_3D, horizon_days=3,
candidates={"Trial": trial_model})`) — keine zweite Kopie der Embargo-/Scoring-/NaN-Tail-Logik im Tuning-Skript,
strukturell unmöglich, das Leck von letztem Mal (Duplikat-Eval-Code im damaligen `experiment_target3d_tuning.py`)
erneut einzubauen. Diese Signatur-Erweiterung selbst ist der einzige Produktions-Code-Eingriff, der VOR der
eigentlichen Suche passiert (mit eigenem Test: bestehende Aufrufe ohne `candidates` verhalten sich unverändert,
ein expliziter `candidates`-Override wird tatsächlich verwendet).

**Suchraum:**
- RandomForest, HistGradientBoosting (sklearn, bereits Produktions-Dependency).
- LightGBM, XGBoost (neu, nur in einer separaten `.venv-tuning/` für die Dauer der Suche — analog zum letzten
  Versuch — nicht in `requirements.txt`, solange kein Gewinner feststeht).
- Randomisierte Ziehung aus sinnvollen, an sklearn-/lightgbm-/xgboost-Dokumentation orientierten Bereichen je
  Familie (Tiefe/Blattzahl, Lernrate, Anzahl Bäume/Iterationen, Regularisierung, `min_samples_leaf`/
  `min_child_samples`) — exakte Werte-Listen sind Implementierungsdetail des Plans, kein Grid (Suchraum zu groß
  für ein festes Budget).

**Eval-Methodik:**
- 30-Fold-Walk-Forward gegen `TARGET_3D`/`horizon_days=3` (gleiche Fold-Zahl wie der letzte Versuch — CLAUDE.md
  warnt explizit vor zu wenigen Folds als Quelle einer zu optimistischen Zahl).
- Baseline: die aktuelle, geteilte `_build_candidates()`-Config, embargo-korrekt über denselben Pfad neu
  gemessen (erste Zeilen des Laufs, bevor die eigentliche Suche beginnt — gleiches Muster wie letztes Mal).
- **Kriterium:** eine Konfiguration gilt als besser, wenn `Sign-Accuracy ≥ Baseline+1pt UND MAE ≤ Baseline`
  (identisch zum Kriterium der bereits erfolgreichen 1-Tages-Suche).
- **Tiebreaker:** erfüllen mehrere Konfigurationen das Kriterium, gewinnt die mit der besseren
  `reversal_sign_accuracy` (Trendwenden-Trefferquote, aus dieser Session neu eingeführt) — das ist der Fall, in
  dem das Modell nachweislich mehr leistet als die triviale Trägheits-Baseline (die insgesamt ~90% Richtung
  trifft, siehe `docs/superpowers/specs/2026-08-04-ml-baseline-honesty-design.md`).
- **Dependency-Schwelle:** LightGBM/XGBoost wird nur übernommen, wenn der beste Kandidat dieser Familien den
  besten qualifizierenden sklearn-Kandidaten um ≥5% relative MAE-Verbesserung **oder** ≥2pt Accuracy übertrifft.
  Reicht der Vorsprung nicht, gewinnt der beste sklearn-Kandidat trotzdem (Dependency-Kosten sind dauerhaft, ein
  knapper Vorsprung rechtfertigt sie nicht).

**Ausführung:**
- Neuer Branch/Worktree (analog zu den bisherigen ML-Sessions dieses Repos).
- `src/experiment_target3d_tuning.py` (Name/Muster wie beim letzten Versuch), `TUNING_BUDGET_HOURS=11`,
  randomisierte Ziehung bis Budget erschöpft, sauberer Abbruch wenn `letzte_Config_Laufzeit × 1.3 > Restbudget`
  (bewährtes Muster aus dem letzten Lauf).
- Läuft als Hintergrundprozess in der Sandbox; Fortschritt wird in großen Abständen (~45-60 Min) geprüft, kein
  Dauer-Polling.
- Rohes Log lokal (`tuning-results/`, gitignored). Ergebnis-Zusammenfassung wird unabhängig vom Ausgang als Doku
  committet (`docs/superpowers/plans/2026-08-04-ml-3d-tuning-results.md`, analog zum letzten Mal) — "kein
  Gewinner" ist ein valides, dokumentiertes Ergebnis.
- Skript wird nach Abschluss der Suche wieder per `git rm` entfernt (etabliertes Repo-Muster für
  `experiment_*.py`), unabhängig vom Ergebnis.

## Ergebnis-Übernahme (nur falls ein Gewinner das Kriterium erfüllt)

- `_build_candidates()` wird parametrisiert (`_build_candidates(horizon_days: int = 1)`), mit einem
  horizon-abhängigen Hyperparameter-Dict statt einer zweiten Funktion — alle drei Call-Sites
  (`_train_and_evaluate`, `_walk_forward_backtest`, `backfill_prediction_log`) reichen ihr bereits vorhandenes
  `horizon_days` einfach durch, keine Duplikation.
- Bestehender `BuildCandidatesTests`-Pinning-Test (`tests/test_market_predictor.py`) wird um einen 3T-Fall
  erweitert, der die neuen Werte fixiert.
- Falls die gewinnende Familie LightGBM/XGBoost ist: neue Dependency in `requirements.txt` exakt gepinnt, in
  beiden betroffenen Workflows (`dashboard-marktwerte.yml`, `dashboard.yml`) verdrahtet.
- Danach: normaler PR-Workflow (`gh pr create` + Auto-Merge), anschließend erneuter Backfill (beide Horizonte,
  Skript-Datei) + erzwungener Heavy-Lauf (neue Hyperparameter ändern historische Prognosen rückwirkend) — gleicher
  Ablauf wie nach dem Baseline-Honesty-Merge dieser Session, Ergebnis wieder ehrlich gegen die jetzige 3T-Zahl
  vergleichen und dem User mitteilen.
- Falls **kein** Gewinner das Kriterium erfüllt: keine Code-Änderung, nur Dokumentation (siehe oben) — die
  geteilte Config bleibt bestehen, jetzt mit echtem Beleg, dass sie auch für `TARGET_3D` ein guter Punkt ist.

## Verification / Nächste Schritte

- Test für die `_walk_forward_backtest(candidates=...)`-Erweiterung: ein expliziter Override wird tatsächlich
  verwendet (nicht die interne `_build_candidates()`-Default), UND bestehende Aufrufe ohne den Parameter bleiben
  unverändert grün (Regressionsschutz für die drei Produktions-Call-Sites).
- Das Tuning-Skript selbst hat keine automatisierten Tests (einmaliges Experiment, kein Produktionscode —
  etabliertes Muster, siehe alle vorherigen `experiment_*.py`).
- Manuelle Verifikation beim Ausführen: `BASELINE`-Zeilen vor Suchbeginn, laufende `ERGEBNIS`-Zeilen, sortierte
  `ENDERGEBNIS`-Bestenliste am Ende.
- Bei Übernahme eines Gewinners: siehe Testanforderungen im Abschnitt "Ergebnis-Übernahme" oben
  (`BuildCandidatesTests`-Erweiterung ist Pflicht, nicht optional).
