# HANDOFF: KickbaseAgent Dashboard

Offene Aufgaben und Themen, die noch geplant oder umgesetzt werden müssen. Kein Änderungsprotokoll vergangener
Arbeit — das steht in der Git-Historie (`git log`). Wie in diesem Repo gearbeitet wird: `CLAUDE.md`.

## In Arbeit — PR #13 wartet auf Merge

`ML: embargo-korrekte 3T-Hyperparameter-Suche (kein Gewinner)` — PR #13 erstellt, Auto-Merge (Squash)
aktiv, Checks liefen beim Session-Ende noch. Falls beim Wiedereinstieg noch offen: `gh pr view 13`
prüfen, ggf. `gh api -X PUT repos/TyraBite/KickbaseAgent/pulls/13/update-branch` falls `mergeStateStatus`
`BEHIND`/`BLOCKED` zeigt (Ruleset erzwingt aktuelle Basis für die 4 Required Checks). Enthält nur eine
generisch nützliche Erweiterung von `_walk_forward_backtest()` (`candidates=`/`n_folds=`-Overrides) plus
Doku — **kein** Hyperparameter-Wechsel, deshalb nach dem Merge **kein** Backfill/Heavy-Lauf nötig (anders
als beim vorherigen Baseline-Honesty-Merge).

## Offen aus `feedback/current` (Firestore)

- **Sentiment-Analyse für Marktwert-Turning-Points** (`6b08e2cf`) — technisch umgesetzt (`news_sentiment.py`,
  `avg_sentiment_7d`/`news_volume_7d` in `market_predictor.py::FEATURES`), bewusst NICHT auf `status:"done"`
  gesetzt. Live geprüft am 2026-08-04 (`player_news_log`: 9 Tage Historie, 2246 Artikel, Median 2/Spieler) —
  Cold-Start bestätigt, noch nicht die im Design-Spec geforderten "Wochen/Monate". **Zusätzlich, unabhängig von
  Cold-Start**: echtes germansentiment-Modell live gegen Amiri/Le-Joncour-Artikel laufen lassen (volle 3-Klassen-
  Wahrscheinlichkeiten inspiziert, nicht nur den gespeicherten Argmax-Score) — Modell funktioniert grundsätzlich
  (Verletzungsmeldungen/Transfer-Dramen korrekt stark negativ/positiv erkannt), hat aber eine strukturelle
  Blindstelle bei ruhigen "Spieler bleibt/verkündet Verbleib"-Meldungen (~99% Neutral-Konfidenz, echtes
  Modellverhalten, kein Rundungsartefakt der Pipeline) und bei Spielern ohne aktuelle Presseberichterstattung
  (Le Joncour: 35 historische RSS-Treffer vorhanden, aber keiner im aktuellen 7-Tage-Fenster — kein Scraping-Bug,
  echtes Presse-Coverage-Loch bei Bankspielern). Heißt: selbst nach genug Historie wird das Feature nur einen Teil
  der Turning-Points fangen, nicht alle wie ursprünglich erhofft. Details + ein konkreter Negations-Bug: siehe
  Technische Schulden unten. Bei Gelegenheit auf Cold-Start prüfen, aber Erwartungshaltung an die Abdeckung
  entsprechend dämpfen, bevor auf `status:"done"` gesetzt wird.
- **Public-Domain-Marktwert-Datenbank "KickbaseMarketPredictor"** (`f686c8db`) — Idee, alle Marktwert-Prognosen als
  öffentliche Datenbank für andere Kickbase-User anzubieten, komplett getrennt vom persönlichen Agent. Offene
  Fragen: rechtlich zulässig? Monetarisierung? Domain-Kosten? Skalierbare Infrastruktur? Noch nicht gescoped, kein
  Plan.

## Technische Schulden

- **CI-Hardening, bewusst zurückgestellt** (Minor, kein akuter Bedarf): `integration_id`-Pinning auf den 4 Required
  Checks, `concurrency`-Gruppen + `timeout-minutes` auf `backend-tests.yml`/`frontend-tests.yml`/
  `frontend-playwright-tests.yml`, `pyproject.toml` mit `pythonpath = ["."]`.
- **`KICKBASE_LEAGUE_START_BUDGET` steht als Klartext-Wert in beiden Workflow-YAMLs** statt über das gleichnamige
  Secret referenziert zu werden — funktioniert, ist aber nicht best practice.
- **`news_sentiment.py::classify_sentiment()` echter Negations-Bug** — live verifiziert 2026-08-04 anhand
  Headline "Amiri, Sano, Nebel weg aus Mainz? Für Heidel 'definitiv ausgeschlossen'" (Wechsel wird
  ausgeschlossen = gute Nachricht) wird mit `sentiment_label="negative"`, Score 0.92 klassifiziert (germansentiment
  reagiert auf "weg"/"ausgeschlossen", ohne die Verneinung/den Kontext zu invertieren). Kein Fix ohne echten
  Nutzennachweis des Gesamtfeatures anfangen (siehe `6b08e2cf` oben) — hier nur dokumentiert, damit der Fund nicht
  verloren geht.
- **`news_sentiment.py` speichert nur die Argmax-Klassen-Konfidenz** (`sentiment_score` = Wahrscheinlichkeit des
  vorhergesagten Labels), nicht die volle 3-Klassen-Verteilung. Ein kontinuierlicher signierter Score
  (`p(positive) - p(negative)`) statt/neben dem diskreten Label würde etwas mehr Gradient erhalten (live
  verifiziert: in der Amiri-Gerüchtephase vor der Verbleib-Verkündung liegt der signierte Score klar negativer als
  danach, auch wenn beide Phasen als `"neutral"` gelabelt sind) — behebt aber NICHT die strukturelle Blindstelle
  bei "Spieler bleibt"-Meldungen oben, nur ein kleiner, potenziell lohnender Zusatz-Fix, keine Lösung des
  Kernproblems.

## Test-Coverage (Audit 2026-08-03)

Vollständige Prio-Liste: `docs/superpowers/plans/2026-08-03-test-coverage-audit.md`. Quick Wins umgesetzt (Backend/
Frontend/gescoptes Follow-up, siehe zugehörige Pläne im selben Ordner). Bewusst zurückgestellt (User-Entscheidung
2026-08-03, nicht ohne Rückmeldung anfangen):

- `player_valuation.py::calibrate()`/`build_reference_set()`, `resolve_ownership()` — brauchen
  Fixture-/Mock-Design, erst wenn produktiv etwas auffällt.
- `FeedbackTab.tsx` Nebenläufigkeits-Test (konkurrierender Status-Change zwischen Lesen und Schreiben) — braucht
  Mocking-Design, erst wenn produktiv etwas auffällt.
- Legacy-Pfad `prompt_builder.py`/`discord_notify.py` — bewusst NICHT abgedeckt, aktiver Nutzen unklar.

## Ideen ohne aktuellen Auftrag (nicht von selbst anfangen)

- **Modelle nochmal tunen, sobald genug echte Daten da sind** — Fitness-/Startelf-/Sentiment-Features liefern noch
  Cold-Start-Platzhalter, eine erneute Hyperparameter-Suche lohnt erst danach. 1-Tages-Horizont bereits getunt
  (277 Configs, 2026-07-31); 3-Tages-Horizont jetzt ebenfalls embargo-korrekt getestet (324 Configs,
  2026-08-04, RandomForest/HistGradientBoosting/LightGBM/XGBoost) — **kein Gewinner**, bestehende Config
  bestätigt (Details: `docs/superpowers/plans/2026-08-04-ml-3d-tuning-results.md`). Für `_walk_forward_backtest()`
  existiert jetzt ein `candidates=`/`n_folds=`-Override eigens für zukünftige Suchen (kein neues
  Experiment-Skript mit eigener Embargo-Logik mehr nötig). User-Idee, kein aktueller Auftrag, bis Cold-Start
  vorbei ist.
- **Externe Signale** (Transfermarkt.de-Wechselgerüchte) — "noch komplexer, später", explizit zurückgestellt.
- **Autopilot-Idee** (schreibende Kickbase-API-Calls, z.B. automatische Gebote) — reine Neugier-Frage, technisch
  plausibel, aber explizit NICHT für die aktuelle Liga gedacht (anderes Risikoprofil: ToS-Bann-Risiko, echtes
  In-Game-Budget statt nur falscher Zahlen). Erster Schritt bei Interesse: Network-Capture aus der echten App
  während eines Gebots.
- **Cron-Minuten-Verschiebung beobachten** (`:17`/`:07` statt `:00`/`:05`) — war ein früherer mehrstündiger Ausfall
  ein Einzelfall oder ein wiederkehrendes Muster? Gelegentlich `gh run list --workflow=dashboard.yml --limit 30
  --json createdAt,event` prüfen.

## Setup Required (manueller Schritt)

- Firebase Console: Auth Email/Passwort-Provider-Einstellung — letzter offene manuelle Schritt aus dem App-weiten
  Security-Audit (der Firestore-Rules-Abgleich läuft inzwischen automatisiert über `firestore-rules-deploy.yml`).
