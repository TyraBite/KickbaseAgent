# HANDOFF: KickbaseAgent Dashboard

Offene Aufgaben und Themen, die noch geplant oder umgesetzt werden müssen. Kein Änderungsprotokoll vergangener
Arbeit — das steht in der Git-Historie (`git log`). Wie in diesem Repo gearbeitet wird: `CLAUDE.md`.

## Offen aus `feedback/current` (Firestore)

- **Sentiment-Analyse für Marktwert-Turning-Points** (`6b08e2cf`) — technisch umgesetzt (`news_sentiment.py`,
  `avg_sentiment_7d`/`news_volume_7d` in `market_predictor.py::FEATURES`), bewusst NICHT auf `status:"done"`
  gesetzt: alle Features liefern noch Cold-Start-Platzhalter, ein echter Nutzennachweis (Korrelation mit
  tatsächlichen Marktwert-Turning-Points wie Amiri/Le Joncur) braucht erst Wochen/Monate echte Historie. Bei
  Gelegenheit prüfen und dann als erledigt markieren.
- **ML-Charts mobil kaum lesbar** (`5a182f9d`) — Tooltip-Position/Punktdichte/Zeitraum, braucht Entscheidungen zu
  Mobile-Breakpoints/Sampling.

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
