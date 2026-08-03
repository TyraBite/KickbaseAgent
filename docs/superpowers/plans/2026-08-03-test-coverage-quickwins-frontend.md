# Test-Coverage Quick Wins — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die "Quick Win"-Frontend-Funde aus `docs/superpowers/plans/2026-08-03-test-coverage-audit.md` schliessen — gezielte Vitest-Unit-Tests fuer bisher ungetestete reine Ableitungsfunktionen.

**Architecture:** Reines Test-Hinzufuegen in bestehenden `*.test.ts`-Dateien (TDD), kein Produktionscode wird geaendert ausser ein Test deckt einen echten Bug auf.

**Tech Stack:** Vitest, gleiche Konventionen wie die bestehenden 59 Tests in `derive.test.ts`/`format.test.ts`/etc.

## Global Constraints

- **Kein Produktionscode aendern**, ausser ein neuer Test deckt tatsaechlich einen echten Bug auf — dann TDD, im
  finalen Report explizit als "echten Bug gefunden" markieren.
- Alle Funktionen in diesem Batch sind reine Funktionen (`derive.ts`/`format.ts`/`formations.ts`/
  `wunschkaderResolve.ts`) — kein Mocking, kein React-Rendering noetig, reine Vitest-Unit-Tests.
- Fixtures nach bestehendem Muster in `derive.test.ts` bauen (siehe z.B. die `players`-Fixture bei
  `buildDashboardSellCandidates`-Tests weiter oben in derselben Datei fuer die minimal noetigen `PlayerRecord`-Felder).
- Push-Policy: **PR-Pflicht** (seit 2026-08-03) — `gh pr create` + `gh pr merge --auto --squash`, kein Direkt-Push.
- Vor Branch-Erstellung `git log origin/main --oneline -5` pruefen.
- Alle Tasks in EINEM PR buendeln, ein Commit pro Task.

---

## Task 1: `derive.ts::valuation()`/`signalFor()`

**Files:** Modify: `frontend/src/lib/derive.test.ts`

- [ ] Failing Tests: `valuation()` mit einem bekannten `market_value`/`average_points`/`position`/`calibration`-Quadrupel → erwartetes `fairwert`/`signal`; zusaetzlich der `!k || !marketValue || !averagePoints`-Null-Guard-Zweig (jeweils einen der drei Werte fehlend/0 durchspielen, `fairwert`/`signal` bleiben `null`).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: derive.valuation/signalFor (Kern-Fairwert-Rechnung, bisher ungetestet)"`.

## Task 2: `derive.ts::nextUpdateCutoff()` DST-Regressionstest

**Files:** Modify: `frontend/src/lib/derive.test.ts`

- [ ] Test fuer den in Commit `779b413` gefixten DST-Bug: ein `Date`-Wert kurz vor/nach der Sommer-/Winterzeit-Umstellung, `nextUpdateCutoff()` liefert den korrekten 22-Uhr-Berlin-Zeitpunkt (nicht um 1h daneben). Mindestens 2 Faelle (Fruehjahr- und Herbst-Umstellung), am besten das Datum aus dem urspruenglichen Fix-Commit/HANDOFF-Eintrag uebernehmen, falls dort konkret genannt.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: derive.nextUpdateCutoff DST-Regression (Commit 779b413 gegen erneutes Auftreten absichern)"`.

## Task 3: `derive.ts::buildBudgetPlan()` — restliche Felder

**Files:** Modify: `frontend/src/lib/derive.test.ts`

- [ ] Bestehenden Test (deckt nur `committed`) um Assertions fuer `sell_proceeds`, `pool`, `cash`, `remaining` erweitern oder als separate `it()`-Faelle in derselben `describe`-Gruppe ergaenzen — mit einer Fixture, die tatsaechlich Verkaufserloese UND ein laufendes Gebot enthaelt, damit alle vier Felder einen von 0 verschiedenen, pruefbaren Wert haben.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: derive.buildBudgetPlan sell_proceeds/pool/cash/remaining (bisher nur committed getestet)"`.

## Task 4: `derive.ts::suggestBid()` direkte Tests

**Files:** Modify: `frontend/src/lib/derive.test.ts`

- [ ] Failing Tests direkt gegen `suggestBid()` (nicht nur indirekt ueber `plannedPriceFor()`): Perzentil-Berechnung (p75) aus einer kleinen `bid_premium_history`-Fixture mit mehreren Eintraegen derselben Position, das `k=20`-Naehe-Fenster (nur die K naechstliegenden Spieler nach Marktwert/Punkteschnitt fliessen ein), und der Fall mit zu wenig Datenpunkten (`suggestionN` klein, "geringe Datenbasis"-Kennzeichnung).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: derive.suggestBid Perzentil-/Naehe-Fenster-Logik direkt (bisher nur indirekt ueber plannedPriceFor beruehrt)"`.

## Task 5: "Row-Builder"-Familie

**Files:** Modify: `frontend/src/lib/derive.test.ts`

- [ ] Je ein Test fuer `buildPlayerRow`, `buildTransfermarktRows`, `buildSpekulationRows`, `buildEigenesTeamSplit`, `buildAlleSpielerRows`, `ownerFor` — jeweils ein minimaler, aber realistischer Fixture-Fall pro Funktion (2-3 Spieler reichen), der die zentrale Transformation prueft (z.B. `buildSpekulationRows` filtert auf positive `ml_prediction`, `ownerFor` liefert die korrekte von 4 moeglichen Eigentuemer-Kategorien).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: Row-Builder-Familie (buildPlayerRow/buildTransfermarktRows/buildSpekulationRows/buildEigenesTeamSplit/buildAlleSpielerRows/ownerFor)"`.

## Task 6: `ui.tsx::SignalBadge` Schwellenwert-Grenzfall

**Files:** Create/Modify: `frontend/src/components/ui.test.ts` (neu, falls noch keine Testdatei fuer `ui.tsx` existiert)

- [ ] Falls `SignalBadge` eine reine Ableitungsfunktion fuer die Tone-Wahl intern nutzt (im Quellcode pruefen) — diese direkt testen bei genau `thresholds.good`, `thresholds.critical`, und einem Wert dazwischen. Falls die Logik nur inline in der Komponente steckt (kein extrahierbarer Helper, konsistent mit der "keine Test-Only-Extraktion"-Regel dieses Projekts) — dann stattdessen einen minimalen Playwright-CT-Smoke-Test in `frontend/tests-ct/` ergaenzen, der `SignalBadge` mit den drei Werten mountet und die gerenderte Tone-Klasse/den Text prueft. Im Report festhalten, welchen der beiden Wege der Implementierer gewaehlt hat und warum.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: SignalBadge Schwellenwert-Grenzfaelle (good/critical/dazwischen)"`.

## Task 7: `table.tsx::SortableTable` Sortier-Toggle + Null-Handling

**Files:** Create: `frontend/tests-ct/SortableTable.ct.tsx` (Playwright Component Test, da echtes DOM-Klick-Verhalten getestet wird)

- [ ] Component mounten mit einer kleinen Fixture (3-4 Zeilen, eine mit `null`-Wert in der sortierten Spalte). Spaltenkopf einmal klicken (aufsteigend), pruefen dass die `null`-Zeile ans Ende sortiert; nochmal klicken (absteigend), `null`-Zeile bleibt weiterhin am Ende (nicht am Anfang); auf eine ANDERE Spalte klicken, pruefen dass die neue Spalte wieder mit aufsteigend startet (Sortierrichtung resettet pro Spaltenwechsel).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "CT-Test: SortableTable Sortier-Toggle + Null-immer-zuletzt (geteilt ueber ~5 Tabs)"`.

## Task 8: `formations.ts::canAddStarter()`/`matchedFormation()`

**Files:** Modify: `frontend/src/lib/formations.test.ts` (neu, falls noch keine Testdatei existiert)

- [ ] `canAddStarter()`: ein `PositionCounts`-Objekt, das fuer 2-3 der 10 erlaubten Formationen noch genau einen Starter pro Position braucht → `true`; ein Objekt, das KEINE der 10 Formationen mehr erreichen kann (z.B. 2 Torwaerter) → `false`.
- [ ] `matchedFormation()`: ein exaktes Match gegen eine der 10 Formationen; ein Fall mit 11 Feldspielern, der KEINE der 10 Formationen matcht (ungueltige Aufstellung, z.B. 2 Torwaerter).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: formations.canAddStarter/matchedFormation (bisher ungetestet, gate't Wunschkader-Slot-UI)"`.

## Task 9: `wunschkaderResolve.ts::resolveTarget()`

**Files:** Modify: `frontend/src/lib/wunschkaderResolve.test.ts` (neu, falls noch keine Testdatei existiert)

- [ ] Je ein Testfall fuer alle 5 Status-Zweige (`Eigener Kader`, `Markt (...)`, `Bei X`, `Frei`, `Nicht gefunden`) mit einer kleinen players/listings/ownedBy-Fixture pro Fall.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: wunschkaderResolve.resolveTarget alle 5 Status-Zweige"`.

## Task 10: `format.ts` restliche Funktionen

**Files:** Modify: `frontend/src/format.test.ts`

- [ ] Je 2-3 Faelle fuer `fmtNum`, `fmtSigned`, `fmtPct`, `trendClass` (falls nicht schon zufaellig durch `budgetTone`-Tests indirekt abgedeckt — im Quellcode/Testfile pruefen, keine Duplikate anlegen), `formatDurationMs`, `trendArrow` (5 Zustaende um die `flat`/`strong`-Schwellenwerte, inkl. `0`/`null`/`undefined`).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "Test: format.ts restliche Funktionen (fmtNum/fmtSigned/fmtPct/trendClass/formatDurationMs/trendArrow)"`.

## Finale Verifikation + PR

- [ ] `npm run typecheck && npm run test -- --run && npm run build` — alles gruen.
- [ ] Branch erstellen, alle Commits pushen: `git push -u origin test-coverage-quickwins-frontend`.
- [ ] `gh pr create --title "Test-Coverage Quick Wins: Frontend" --body "Siehe docs/superpowers/plans/2026-08-03-test-coverage-quickwins-frontend.md"`.
- [ ] `gh pr merge --auto --squash`, auf die 4 Required Checks warten, Merge bestaetigen.
