# Test-Coverage-Audit (2026-08-03) — Ergebnis + priorisierte Liste

Referenziert von `CLAUDE.md` ("Verbindliche Regel: Testabdeckung"). Durchgeführt per zwei parallelen Recherche-Agenten
(Frontend/Backend), Ergebnisse hier zusammengeführt. Grundlage: User-Auftrag 2026-08-03, "ermittle die
Testabdeckung und erstelle eine Prio-Liste damit wir die Testabdeckung erhöhen können."

**Backend-Suite zum Zeitpunkt des Audits**: 295 Tests, alle in komplett sauberer Umgebung (kein `.env`, keine
GCP-Credentials) unabhängig nachgestellt grün — bestätigt, dass `backend-tests.yml` wirklich alles gegen Mocks
laufen lässt, keine versteckte Abhängigkeit von lokalen Secrets.

**Frontend-Suite zum Zeitpunkt des Audits**: 59 Vitest-Tests, 4 Playwright-Component-Tests, 1 Playwright-E2E-Test.

## Legende

- **Quick Win**: eng abgegrenzter Test, keine Design-Entscheidung nötig, direkt umsetzbar.
- **Braucht Entscheidung**: unklarer Scope, braucht Mocking-/Fixture-Design oder eine Priorisierungsfrage — **nicht
  ohne User-Feedback umsetzen** (User-Vorgabe 2026-08-03).

## Backend — priorisierte Liste (aus dem vollständigen Bericht)

| # | Fund | Severity | Typ |
|---|---|---|---|
| 1 | `player_valuation.py::k_per_point()`/`signal()`/`fairwert()` — komplett ungetestete reine Funktionen, berechnen die Fairwert-Zahl für JEDEN Spieler im Live-Dashboard | Höchste | Quick Win |
| 2 | `player_valuation.py::calibrate()`/`build_reference_set()` — die K-Wert-Berechnung hinter jedem Fairwert, nur über gemockte Call-Sites erreichbar, nie real ausgeführt | Höchste | Braucht Entscheidung (Fixture-Design für Positions-Buckets/`MIN_POSITION_SAMPLE`) |
| 3 | `fetcher.py::_market_item_to_row()` — Funktion mit dokumentiertem echtem Live-Crash in der Vergangenheit ("unhashable type: dict"), null Tests heute | Hoch | Quick Win |
| 4 | `fetcher.py::_apply_market_value_history()` — berechnet `market_value_change_7d` (Geld-Feld auf jeder Karte), `len(entries)>=8`-Grenzfall ungetestet | Hoch | Quick Win (leichtes Mocking) |
| 5 | `player_valuation.py::resolve_ownership()` — dokumentierte vergangene Bug-Klasse (`'i'` vs `'pi'`-Feldverwechslung, jeder Spieler faelschlich "frei") ohne Regressionstest | Hoch | Braucht Entscheidung (kleiner API-Mock) |
| 6 | `firestore_db.py::_write_in_batches()` — >500-Dokument-Chunking-Pfad nie durchlaufen (alle Tests nutzen 1-2 Docs) | Mittel | Quick Win |
| 7 | `discord_notify.py::_post_with_retry()` — 429-Retry-Logik, KEIN Testfile existiert überhaupt | Mittel | Quick Win |
| 8 | `db.py`-Schreibfunktionen (`replace_market_listings`, `upsert_own_budget`, `upsert_season_context`, `replace_manager_budgets`) — kein Round-Trip-Test, laufen aber bei JEDEM Cron | Mittel | Quick Win |
| 9 | `dashboard_export.py::_build_recent_transfers()` — unbekannte `player_id` wird still verworfen, kein Test dafür | Niedrig-Mittel | Quick Win |
| 10 | `kickbase_client.py::_raise_for_status()`/`get_teams()`-Filterung — 401 vs. generischer Fehler, Dict-Comprehension-Filter ungetestet | Niedrig-Mittel | Quick Win |
| — | `market_predictor.py::_parse_minutes()` — Fallback bei kaputtem `"mp"`-String von der echten API ungetestet | Niedrig-Mittel | Quick Win |
| — | `main.py::_predict_market_values()` — Env-Var-Parsing ungetestet, aber bestätigt NICHT auf dem Live-Cron | Niedrig | Quick Win (geringe Prio) |
| — | `prompt_builder.py`/`discord_notify.py` (Rest) — alter Parallel-Pfad, `DISCORD_WEBHOOK_URL` steht noch live in `.env` | Mittel | Braucht Entscheidung (lohnt sich Investment in den Legacy-Pfad noch?) |
| — | `dashboard_export.py::export()` — `_build_ligaanalyse` bleibt in allen Integrationstests gestubbt | Niedrig | Braucht Entscheidung (redundant zu den 15 dedizierten Ligaanalyse-Tests?) |
| — | `_walk_forward_backtest()` fehlendes Embargo für 3-Tage-Horizont | Hoch (Impact), aber **kein frischer Fund** — bereits in HANDOFF.md dokumentiert, bewusst zurückgestellt | Design-Entscheidung, nicht Teil dieser Liste |

## Frontend — priorisierte Liste (aus dem vollständigen Bericht)

| # | Fund | Severity | Typ |
|---|---|---|---|
| 1 | `derive.ts::valuation()`/`signalFor()` — Fairwert/Signal-Kernrechnung, auf 6+ Tabs gerendert, null Tests | Hoch | Quick Win |
| 2 | `derive.ts::nextUpdateCutoff()` — dokumentierter, bereits gefixter DST-Bug (Commit `779b413`), kein Regressionstest | Hoch | Quick Win |
| 3 | `derive.ts::buildBudgetPlan()` — nur `committed` getestet, `sell_proceeds`/`pool`/`remaining`/`cash` (echtes Budget-Geld) ungetestet | Hoch | Quick Win |
| 4 | `derive.ts::suggestBid()` — treibt echte Euro-Gebotsempfehlungen, nur indirekt über `plannedPriceFor()` beruehrt | Hoch | Quick Win |
| 5 | Wunschkader-Planungsmodus (`WunschkaderTab.tsx`) — bewusst ohne Tests ausgeliefert, unterdrückt echte Firestore-Writes | Hoch | Braucht Entscheidung (CT-Infra existiert schon, leichtes Scoping) |
| 6 | "Row-Builder"-Familie (`buildPlayerRow`, `buildTransfermarktRows`, `buildSpekulationRows`, `buildEigenesTeamSplit`, `buildAlleSpielerRows`, `ownerFor`) — Grundlage für jeden Tab, null Tests | Hoch | Quick Win |
| 7 | `ui.tsx::SignalBadge`-Schwellenwert-Grenzfall — einzige Render-Stelle des Signal-Werts app-weit | Mittel-Hoch | Quick Win |
| 8 | `table.tsx::SortableTable` Sortier-Toggle + Null-Handling — geteilt über ~5 Tabs | Mittel-Hoch | Quick Win |
| 9 | `DashboardTab.tsx` — Kaderlimit-Reihenfolge + Klick-auf-richtiges-Modal | Hoch | Braucht Entscheidung (leichtes Scoping) |
| 10 | `AlleSpielerTab.tsx` kombinierte Filter | Mittel-Hoch | Braucht Entscheidung (welche Kombinationen zählen?) |
| 11 | `App.tsx` "Swipe blockiert bei offenem Modal" | Mittel-Hoch | Braucht Entscheidung (Scoping) |
| 12 | `formations.ts::canAddStarter()`/`matchedFormation()` | Mittel | Quick Win |
| 13 | `wunschkaderResolve.ts::resolveTarget()` (5 Status-Zweige) | Mittel | Quick Win |
| 14 | `FeedbackTab.tsx` nebenläufigkeitssicherer Save-Pfad | Mittel | Braucht Entscheidung (Mocking) |
| 15 | `PlayerCompareModal.tsx` Gewinner-Hervorhebung | Mittel | Braucht Entscheidung (Scoping) |
| — | `format.ts` Rest (`fmtNum`/`fmtSigned`/`fmtPct`/`trendClass`/`formatDurationMs`/`trendArrow`) | Mittel | Quick Win |
| — | `EigenesTeamTab.tsx`, `SpekulationTab.tsx`/`TransfermarktTab.tsx` `sortRows()`, `Login.tsx`, `MlGenauigkeitTab.tsx` (Rest) | Mittel | Braucht Entscheidung |

## Was jetzt direkt umgesetzt wird (Quick Wins, User-Freigabe erteilt)

Alle mit "Quick Win" markierten Punkte — Backend-Batch + Frontend-Batch, je ein eigener Implementierungsplan
(`docs/superpowers/plans/2026-08-03-test-coverage-quickwins-backend.md` /
`docs/superpowers/plans/2026-08-03-test-coverage-quickwins-frontend.md`), je ein PR über den neuen Pflicht-Workflow.

## Was auf User-Feedback wartet (bewusst NICHT umgesetzt)

Alle mit "Braucht Entscheidung" markierten Punkte — nicht ohne Rückmeldung angefangen (explizite User-Vorgabe
2026-08-03).
