# HANDOFF: KickbaseAgent Dashboard

Offene Aufgaben und Themen, die noch geplant oder umgesetzt werden müssen. Kein Änderungsprotokoll vergangener
Arbeit — das steht in der Git-Historie (`git log`). Wie in diesem Repo gearbeitet wird: `CLAUDE.md`.

## In Arbeit — Session-Übergabe (2026-08-04, Pause während Umsetzung)

**ML-Prognose Baseline-Ehrlichkeit + Embargo-/Clip-Fix**, subagent-driven-development, 7-Task-Plan. Spec:
`docs/superpowers/specs/2026-08-04-ml-baseline-honesty-design.md`. Plan: `docs/superpowers/plans/2026-08-04-ml-baseline-honesty.md`.

**Wo:** Worktree `/workspace/work/.claude/worktrees/feedback-type-removal` (Name ist historisch, gehört zu einem
älteren, längst gemergten Task — für DIESEN Plan trotzdem weiterverwendet), Branch `worktree-ml-baseline-honesty`
(von `origin/main` abgezweigt, noch **nicht** gepusht/PR erstellt). Ledger:
`.superpowers/sdd/2026-08-04-ml-baseline-honesty/progress.md` (im Worktree, git-ignored) — dort steht der
verbindliche Stand pro Task, hier nur die Kurzfassung.

**Stand:** Tasks 1-6 von 7 committed + Review clean (Task 1 und 5 brauchten je 1 Fix-Round, dokumentiert im Ledger).
Task 7 (letzter Task: `MlGenauigkeitTab.tsx`-Anzeige + neuer Playwright-CT-Test) war beim Pausieren als
Hintergrund-Agent gestartet — **Status beim Wiedereinstieg zuerst per `git log` im Worktree prüfen**, nicht
davon ausgehen, dass der Agent-Task diese Session überlebt hat:
- Kein neuer Commit seit `49b72c7` → Task 7 nie fertig geworden, per `task-brief`-Skript + Task-7-Dispatch-Prompt
  aus dem Plan neu starten (Skript: `subagent-driven-development`-Skill, `scripts/task-brief`).
- Ein neuer Commit vorhanden, aber noch kein Review dazu im Ledger → Review-Package erzeugen (`scripts/review-package`)
  und Task-Reviewer dispatchen, dann normal im Fix-Loop weiter.
- Ledger zeigt "Task 7: complete" → direkt zum finalen Whole-Branch-Review übergehen (`superpowers:requesting-code-review`,
  stärkstes verfügbares Modell), danach `superpowers:finishing-a-development-branch` (PR + Auto-Merge, `main` ist
  geschützt).

**Nach Merge nicht vergessen** (steht auch am Ende des Plan-Dokuments): Heavy-Lauf erzwingen
(`gh workflow run dashboard-marktwerte.yml`), `backfill_prediction_log(days=90)` für beide Horizonte einmalig manuell
laufen lassen (Skript-Datei, kein inline `python3 -c`), alte vs. neue 3T-Genauigkeit vergleichen und dem User ehrlich
mitteilen falls sie schlechter aussieht (CLAUDE.md-Pflicht — alte Zahlen sind aus `ml_accuracy_trend_3d`/`ml_metrics_3d`
bereits in der Session bekannt, vor Beginn der Umsetzung notiert), danach den Embargo-Bug-Eintrag unten unter
„Technische Schulden" entfernen.

**Baseline vor dieser Session** (zum Vergleich, falls die Zahlen ohne Zugriff auf die alte Konversation gebraucht
werden): `python -m pytest tests/` 348 grün, Frontend `npm run typecheck && npm run build && npx vitest run` clean,
114 Vitest-Tests, vor Task 7 auch Playwright-CT komplett grün (Chromium-Sandbox-Workaround: `LD_LIBRARY_PATH` auf
`/tmp/chromedeps/root/...` setzen, Setup-Skript bei Bedarf aus `docs/superpowers/plans/2026-08-03-playwright-regression-coverage.md`
neu aufbauen, `/tmp` ist nicht persistent über Sessions).

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

- **`market_predictor.py::_walk_forward_backtest()` hat kein Embargo für Mehrtage-Horizonte** — verzerrt vermutlich
  die live gezeigte 3-Tage-Genauigkeit (`ml_metrics_3d`) leicht optimistisch. **Nicht nebenbei fixen** — würde
  bereits live gemeldete Genauigkeits-Zahlen rückwirkend verändern, verdient eine eigene, bewusste Session (Embargo
  einbauen, echte Zahlen neu ansehen, User informieren falls die bisher gezeigte 3T-Genauigkeit etwas geschönt
  war). Details: `docs/superpowers/plans/2026-08-01-ml-3d-tuning-results.md`.
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
  Cold-Start-Platzhalter, eine erneute Hyperparameter-Suche lohnt erst danach. User-Idee, kein aktueller Auftrag.
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
