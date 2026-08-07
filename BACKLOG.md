# BACKLOG: KickbaseAgent Dashboard

Offene Aufgaben, Ideen und technische Schulden ohne aktuellen Auftrag. Vor
jeder neuen Session lesen, aber anders als `HANDOFF.md` nicht bei jedem
Commit zwingend aktuell gehalten. Abgeschlossene Punkte werden entfernt,
nicht angehäuft. Für den Stand der letzten Session: `HANDOFF.md`. Wie in
diesem Repo gearbeitet wird: `CLAUDE.md`.

## Offen aus `feedback/current` (Firestore)

- **Sentiment-Analyse für Marktwert-Turning-Points** (`6b08e2cf`) — technisch umgesetzt (`news_sentiment.py`,
  `avg_sentiment_7d`/`news_volume_7d` in `market_predictor.py::FEATURES`), bewusst NICHT auf `status:"done"`
  gesetzt. Live geprüft am 2026-08-04 (`player_news_log`: 9 Tage Historie, 2246 Artikel, Median 2/Spieler) und
  erneut am 2026-08-06 (3.276 Artikel, 333 Spieler, 11 Tage Historie) — Cold-Start bestätigt, noch nicht die im
  Design-Spec geforderten "Wochen/Monate". Zwei live verifizierte Technische Schulden (Negations-Bug bei
  Ausschluss-/Dementi-Meldungen, nur Argmax-Konfidenz statt voller 3-Klassen-Verteilung) sind mit PR #15
  (2026-08-06) behoben, siehe `docs/superpowers/plans/2026-08-06-news-sentiment-negation-signed-score-fix.md`.
  **Weiterhin unbehoben, unabhängig von Cold-Start**: strukturelle Blindstelle bei ruhigen "Spieler
  bleibt/verkündet Verbleib"-Meldungen ohne explizites Reizwort (~99% Neutral-Konfidenz, echtes Modellverhalten,
  kein Rundungsartefakt der Pipeline) und bei Spielern ohne aktuelle Presseberichterstattung (Le Joncour: 35
  historische RSS-Treffer vorhanden, aber keiner im aktuellen 7-Tage-Fenster — kein Scraping-Bug, echtes
  Presse-Coverage-Loch bei Bankspielern). Heißt: selbst nach genug Historie wird das Feature nur einen Teil der
  Turning-Points fangen, nicht alle wie ursprünglich erhofft. Bei Gelegenheit auf Cold-Start prüfen, aber
  Erwartungshaltung an die Abdeckung entsprechend dämpfen, bevor auf `status:"done"` gesetzt wird.
- **Public-Domain-Marktwert-Datenbank "KickbaseMarketPredictor"** (`f686c8db`) — Idee, alle Marktwert-Prognosen als
  öffentliche Datenbank für andere Kickbase-User anzubieten, komplett getrennt vom persönlichen Agent. Offene
  Fragen: rechtlich zulässig? Monetarisierung? Domain-Kosten? Skalierbare Infrastruktur? Noch nicht gescoped, kein
  Plan.
- **Achievements/Login-Boni anderer Manager** (`84ad6dff`) — Achievement-Teil UMGESETZT (PR #19 + Follow-up PR #20,
  2026-08-07, beide gemergt): exakte Schwellenprüfung statt Punkte-Verhältnis-Skalierung für 5 live verifizierte
  Achievement-Ids, siehe `docs/superpowers/plans/2026-08-07-manager-budgets-exact-achievements.md`. Noch NICHT auf
  `status:"done"` gesetzt, da zwei Teile der ursprünglichen Idee bewusst nicht umgesetzt wurden:
  - **Login-Bonus per erkannter Aktivität** (statt Gleichverteilung auf alle Manager) zurückgestellt — Login-Bonus
    ist live als Streak bestätigt (10k/20k/…/gedeckelt bei 100k ab Tag 10, vermutlich Reset bei Lücke), aber pro Tag
    nicht zuverlässig als aktiv/inaktiv belegbar (Aufstellungsänderung anderer Manager wird zwar pro Lauf abgerufen,
    aber nicht cross-run persistiert — `data/kickbase.db` ist pro CI-Lauf frisch). User-Entscheidung 2026-08-07:
    vorerst weiter "jeder Manager loggt sich jeden Tag ein" annehmen, keine Aktivitätserkennung bauen.
  - **"Jackpot"-Idee (Achievements anderer Manager direkt/season-weit auslesen)** live getestet und verworfen:
    `/user/achievements/{id}` ignoriert einen `managerId`-Query-Param stillschweigend (liefert weiter nur eigene
    Daten), `/managers/{id}/achievements` → 404. Kein Hinweis auf einen Manager-scoped Achievement-Endpoint ohne
    tiefere Reverse-Engineering-Arbeit, die bewusst nicht verfolgt wird.
- **Workflows über einen Raspberry Pi laufen lassen** (`306066b2`) — Light/Heavy-Workflows statt/zusätzlich über
  einen Pi mit Internet-Zugang statt (nur) GitHub Actions, würde Cron-Timing-Drift fixen und wäre robust gegen
  GH-Actions-Ausfälle (wie am 2026-08-06 erlebt). Offene Fragen: wie kommen die Workflows auf den Pi, wie wird das
  gemaintaint? User wollte das als Nächstes im Dialog planen — noch keine Antwort zu Hardware/OS/Docker-Status
  erhalten, noch nicht begonnen.

## Technische Schulden

- **CI-Hardening, bewusst zurückgestellt** (Minor, kein akuter Bedarf): `integration_id`-Pinning auf den 4 Required
  Checks, `concurrency`-Gruppen + `timeout-minutes` auf `backend-tests.yml`/`frontend-tests.yml`/
  `frontend-playwright-tests.yml`, `pyproject.toml` mit `pythonpath = ["."]`.
- **`KICKBASE_LEAGUE_START_BUDGET` steht als Klartext-Wert in beiden Workflow-YAMLs** statt über das gleichnamige
  Secret referenziert zu werden — funktioniert, ist aber nicht best practice.
- **Wunschkader-Drag-and-Drop (PR #16, 2026-08-06), kleine offene Politur, keine Bugs**: Drag-Handle ist
  `tabIndex={-1}` ohne `aria-hidden` (AT-Nutzer finden per Tab-Reihenfolge zwar keinen, aber per Screenreader-
  Elementliste einen Button ohne Wirkung — Funktionalität ist über den Button im Detail-Modal vollständig
  vorhanden). Kartenkörper hat kein `select-none` mehr (Long-Press zeigt jetzt das native Text-Auswahl-Menü). Kein
  Auto-Scroll während des Ziehens — bei weit auseinanderliegenden Zielen auf einem vollen, gescrollten Kader (z.B.
  Torwart↔Bank bei 17 Spielern auf dem Handy) bleibt der Klick-Button im Detail-Modal der verlässliche Weg.
- **`WunschkaderDragAndDrop.spec.ts`, vermutlich flaky (beobachtet 2026-08-07, PR #17 und PR #20)**: die
  `maxScroll`-Sanity-Checks ("ohne echten Scroll-Spielraum würde dieser Test nichts beweisen") in den Tests "Drag
  funktioniert korrekt, wenn die Seite gescrollt ist" und "Vertikales Wischen auf dem Kartenkörper scrollt
  weiterhin die Seite" schlugen über drei aufeinanderfolgende CI-Läufe auf PR #17 je unterschiedlich fehl — auch
  auf Commits ohne jede Code-Änderung an Wunschkader. Deutet auf eine Timing-/Render-Race in der mobilen
  Viewport-Emulation, nicht auf einen echten Drag-Bug. Zweiter, unabhängiger Beleg auf PR #20 (2026-08-07, reiner
  Backend-Diff ohne jede Frontend-Änderung, per Job-Log bestätigt unrelated, nach Rerun grün) — Flake tritt also
  auch unabhängig von einem größeren GitHub-Actions-Ausfall auf, die Ausfall-Theorie von PR #17 ist damit allein
  nicht hinreichend. Noch nicht root-caused, kein aktueller Auftrag.

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

- **`FeedbackTab` verliert Entwurfstext beim Tab-Wechsel** — seit dem Frontend-Motion-Pilot (PR #14) verlieren alle
  Tabs außer Wunschkader ihren React-State beim Wegwechseln (bewusste Konsequenz aus "nur Wunschkader bleibt
  dauerhaft gemountet"). Bei `FeedbackTab` betrifft das auch einen halbgetippten, noch nicht gespeicherten
  Text-Entwurf — einziger Ort in der App mit unautosavtem Freitext. Offene Scope-Entscheidung: `FeedbackTab` nach
  demselben Muster wie Wunschkader dauerhaft mounten, oder anders lösen? Noch nicht begonnen.
- **`LigaanalyseTab.tsx`/`TransfermarktTab.tsx` registrieren kein `useModalOpenTracking()`** — ihr Detailmodal hat
  zwar einen Escape-Listener, aber ein Swipe über dem offenen Modal wechselt trotzdem den Hintergrund-Tab.
  Vorbestehender Bug, bei der Motion-Pilot-Review (PR #14) als Nebenfund entdeckt, nicht dadurch verursacht. Noch
  offen.
- **Motion-Pilot Folge-Arbeit, Phase-2-Rollout** (bewusst zurückgestellt, kein aktueller Auftrag): Motion für
  Transfermarkt-/Alle-Spieler-Kartenlisten und Sortier-Tabellen-Row-Reorder in `components/table.tsx`. (Drag-and-Drop
  für Wunschkader-Karten selbst ist seit PR #16, 2026-08-06, umgesetzt.)
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
