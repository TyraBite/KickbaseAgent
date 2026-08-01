# 3-Tage-Modell: eigene Hyperparameter-Suche — Design

## Context

Das "ML-Horizonte"-Feature (2026-07-31) fügte ein zweites Trainingsziel `TARGET_3D`/`mv_target_3d_clipped` hinzu — eine 3-Tage-Marktwertprognose neben der bestehenden 1-Tages-Prognose. `_build_candidates()` (`src/market_predictor.py`) baut für BEIDE Ziele dieselben zwei Modell-Kandidaten (RandomForest, HistGradientBoosting) mit denselben Hyperparametern. Diese Hyperparameter stammen aus einer groß angelegten randomisierten Suche ("Nacht-Runde", 277 Konfigurationen, 9h, 30-Fold-Walk-Forward) — aber diese Suche lief ausschließlich gegen das 1-Tages-Ziel (`TARGET`). Ob das 3-Tages-Ziel mit denselben Parametern optimal bedient ist, wurde nie separat gemessen.

User-Vermutung: das 3-Tages-Modell könnte andere Hyperparameter brauchen (andere Zielverteilung/Rauschcharakteristik über einen längeren Horizont). Ziel dieses Vorhabens: das ermitteln, per Experiment-Skript, das eine spätere Session (oder der User selbst, lokal) tatsächlich ausführt — dieses Vorhaben selbst liefert nur das fertige, dokumentierte Skript + eine erste, echte 3-Tage-Baseline-Messung, keine abschließende "Parameter X ist besser"-Aussage.

## Nicht-Ziele

- Keine Änderung an `_build_candidates()`/`_walk_forward_backtest()`/der Live-Prognose in diesem Vorhaben — das wäre ein bedingter Folge-Schritt, NUR falls die Suche tatsächlich eine bessere Konfiguration findet (siehe Verification/Nächste Schritte).
- Keine Suche für das 1-Tages-Ziel (bereits abgeschlossen, siehe HANDOFF.md).
- Keine neue Produktions-Dependency — LightGBM/XGBoost bleiben rein experimentell (eigenes `.venv-tuning/`, wie beim letzten Mal), Produktions-`requirements.txt` unverändert.

## Architektur

**Ein Skript, zwei Nutzungsarten.** `src/experiment_target3d_tuning.py` (einmaliges Experiment-Skript, nach Gebrauch wieder zu löschen — etabliertes Muster dieses Repos, siehe `git log` für `experiment_deep_tuning.py`/`experiment_hgb_tuning.py`/etc.). Budget per `TUNING_BUDGET_HOURS`-Env-Var — `1.5` für einen kurzen Check (Minuten bis ~1-2h), `9` für einen der "Nacht-Runde" vergleichbaren tiefen Lauf. Kein separates zweites Skript nötig — dieselbe zeitbudget-gesteuerte Zufallssuche liefert bei kleinem Budget automatisch weniger, bei großem Budget mehr getestete Konfigurationen.

**Direkte Portierung von `experiment_deep_tuning.py`** (letzter Stand vor dessen Löschung, per `git show e530b2b:src/experiment_deep_tuning.py` vollständig eingesehen), mit drei notwendigen Anpassungen:
1. Alle Ziel-Bezüge (`TARGET`/`"mv_target"`) werden `target_col`/`unclipped_col`-parametrisiert (`target_col="mv_target_3d_clipped"`, `unclipped_col="mv_target_3d"`) statt hartkodiert.
2. **NaN-Tail-Schutz für `TARGET_3D` ergänzt** (im alten Skript für `TARGET` ein No-Op, für `TARGET_3D` aber notwendig — dieselbe Lücke, die in `_walk_forward_backtest()`s Produktionscode bereits einmal gefunden und gefixt wurde, siehe dessen Docstring): `train.dropna(subset=[target_col])` und `test.dropna(subset=[unclipped_col])` vor jedem Fold-Fit, sonst kippt eine einzelne NaN-Zeile den gesamten MAE einer Konfiguration auf NaN.
3. **`_build_corpus()`-Aufruf aktualisiert** — das alte Skript rief `_build_corpus(token, league_id, competition_id)` (3 Argumente); die Funktion braucht inzwischen zusätzlich `fitness_events_by_player` (4. Argument, aus `_load_fitness_events_by_player()`, Teil des seit dem alten Skript hinzugekommenen Fitness-Historie-Features).

**Baseline zuerst.** Vor der eigentlichen Zufallssuche wertet das Skript `_build_candidates()`s AKTUELLE zwei Kandidaten (die für `TARGET_3D` bisher nie separat gemessene, geteilte Config) über dieselbe 30-Fold-Methodik aus und druckt sie als `BASELINE`-Zeilen — das ist die Zahl, gegen die jede gefundene Konfiguration verglichen wird (gleiches Kriterium wie beim 1-Tages-Erfolg: Sign-Accuracy ≥ Baseline+1pt UND MAE ≤ Baseline).

**Setup identisch zum letzten Mal**: `.venv-tuning/` (schon in `.gitignore`) mit `pip install lightgbm xgboost` zusätzlich zu den Projekt-Requirements, `tuning-results/` (schon in `.gitignore`) für optionale Log-Umleitung.

## Nebenprodukt: 3T-Trend-Pfeil-Schwellen fürs Frontend

Unabhängig davon, ob die Hyperparameter-Suche einen Gewinner findet: die parallel entstandene Frontend-Spec
`docs/superpowers/specs/2026-08-01-ml-horizonte-frontend-anzeige-design.md` (Prognose 1T/3T sichtbar machen) zeigt
die 3-Tages-Prognose vorerst OHNE Trend-Pfeil-Einfärbung, weil dafür kalibrierte Schwellenwerte fehlen — die
bestehende `ML_PREDICTION_THRESHOLDS`-Konstante (`{flat: 20_000, strong: 100_000}`) ist aus der 1-Tages-Verteilung
abgelesen (`kickbase.db`/`ml_prediction_log.jsonl`, siehe Commit `d888431`) und für die strukturell größeren
3-Tages-Werte nicht direkt übertragbar.

**Direkt nach dem "Kurzen Check"** (siehe Plan, unabhängig vom Tuning-Ergebnis) wird deshalb zusätzlich die reale
Verteilung der bereits geloggten `ml_prediction_3d`/`horizon_days:3`-Werte gesichtet (Datenbasis: der bereits
gelaufene 90-Tage-Backfill in der `ml_prediction_log`-Collection, siehe HANDOFF.md, 176 Tages-Aggregate, plus was
der tägliche Heavy-Cron seither ergänzt hat) und daraus eine `ML_PREDICTION_3D_THRESHOLDS`-Konstante (`flat`/
`strong`, gerundet, analog zur bestehenden Vorgehensweise) abgeleitet. Kein neues Skript nötig — ein kurzer,
einmaliger Pandas-Quantile-Schnipsel reicht, kein Teil von `experiment_target3d_tuning.py` selbst (andere
Datenquelle: geloggte Live-Prognosen statt Trainings-Historie).

Sobald die Werte feststehen, ist das Nachziehen im Frontend ein kleiner, eigenständiger Folge-Schritt (Konstante
ergänzen, `trendArrow`/`trendClass` für Prognose 3T aktivieren) — nicht Teil dieses Vorhabens, aber hier vermerkt,
damit es nicht zwischen den beiden Specs verloren geht.

## Verification / Nächste Schritte

- Das Skript selbst hat keine automatisierten Tests (einmaliges Experiment, kein Produktionscode — etabliertes Muster, siehe alle vorherigen `experiment_*.py`).
- Manuelle Verifikation beim Ausführen: `BASELINE`-Zeilen müssen erscheinen, bevor die Suche beginnt; `ERGEBNIS`-Zeilen laufend während der Suche; `ENDERGEBNIS`-Bestenliste am Ende, nach MAE sortiert.
- **Falls ein Gewinner gefunden wird** (schlägt die 3-Tage-Baseline nach obigem Kriterium): eigener Folge-Task, NICHT Teil dieses Plans — `_build_candidates()` bekäme eine horizon-abhängige Signatur (z.B. `target_col`-Parameter, der die HistGradientBoosting-Parameter umschaltet), inkl. Anpassung von `_walk_forward_backtest()`/`_train_and_evaluate()`-Aufrufstellen und Tests.
- **Falls kein Gewinner gefunden wird**: Ergebnis dokumentieren (HANDOFF.md, analog zu den bisherigen "Failed Approaches"-Einträgen) — die geteilte Config bleibt bestehen, mit jetzt echtem Beleg, dass sie auch für `TARGET_3D` ein guter Punkt ist.
- 3T-Trend-Pfeil-Schwellen (siehe oben) unabhängig vom Tuning-Ausgang ableiten und in die Frontend-Spec einpflegen.
- Skript nach dem Lauf wieder löschen (etabliertes Muster).
