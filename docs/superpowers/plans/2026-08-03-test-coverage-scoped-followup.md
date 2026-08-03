# Test-Coverage: gescoptes Follow-up (5 freigegebene Punkte) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die 5 "braucht Entscheidung"-Punkte aus `docs/superpowers/plans/2026-08-03-test-coverage-audit.md`, für die der User im Chat den Scope festgelegt hat, jetzt umsetzen. Die Punkte, die Mocking/Fixture-Design brauchen (FeedbackTab-Nebenläufigkeit, `calibrate()`, `resolve_ownership()`) UND der Legacy-Pfad (`prompt_builder.py`/`discord_notify.py`) sind explizit NICHT Teil dieses Plans (User-Entscheidung: erst wenn produktiv etwas auffällt bzw. gar nicht).

**Architecture:** Alles Playwright (Component Tests + ein E2E-Test), keine neuen Vitest-Unit-Tests in diesem Batch — alle 5 Punkte betreffen Komponenten-Interaktion, keine reinen Ableitungsfunktionen.

**Tech Stack:** Playwright CT (`frontend/tests-ct/`), Playwright E2E (`frontend/tests-e2e/`). Für Firestore-Mocking im Wunschkader-Test das bestehende Muster aus `WunschkaderTabAutoSave.ct.tsx` wiederverwenden (existiert bereits, kein neues Mock-Framework).

## Global Constraints

- Scope pro Punkt ist im Chat (2026-08-03) explizit festgelegt worden — NICHT erweitern:
  - Wunschkader-Planungsmodus: die 3 Szenarien aus dem urspruenglichen Feature-Design (kein Write waehrend Planung, Verwerfen stellt Baseline wieder her, Speichern loest genau einen Write aus).
  - AlleSpielerTab: "ein paar stichprobenartig", NICHT alle Filterkombinationen — 2-3 realistische Kombinationen reichen.
  - DashboardTab: NUR Sektionsreihenfolge (kaderlimit-abhaengig) + richtiges Modal bei Kartenklick — keine tiefere Sektionsdetail-Pruefung.
  - App.tsx Swipe-vs-Modal: EIN Modal-Beispiel reicht, keine Matrix ueber alle Modal-Typen.
  - PlayerCompareModal: ALLE 7 Vergleichszeilen (`ml_prediction`, `ml_prediction_3d`, `signal`, `market_value` [niedriger=besser], `starting_rank` [niedriger=besser], `status_label`/Fitness, `average_points`).
- Kein Produktionscode aendern, ausser ein Test deckt einen echten Bug auf (TDD, im Report klar benennen).
- `SignalBadge`s/`PlayerCompareModal`s Vergleichslogik (`better()`/`betterFitness()`) bleibt unexportiert/inline (Projekt-Konvention gegen Test-Only-Extraktion) — echte Playwright-CT-Tests gegen die gemountete Komponente, keine Unit-Tests auf extrahierte Helper.
- Push-Policy: **PR-Pflicht** — `gh pr create` + `gh pr merge --auto --squash`, kein Direkt-Push.
- Vor Branch-Erstellung `git log origin/main --oneline -5` pruefen.
- Alle 5 Tasks in EINEM PR buendeln, ein Commit pro Task.
- **Lektion aus dem letzten Batch (PR #7)**: `mount()` serialisiert Funktions-Props (`onSelect`, `render`, etc.) NICHT synchron nutzbar an den Browser — sie werden zu Promise-basierten Remote-Stubs. Komponenten, die eine Callback-Prop SYNCHRON aufrufen (wie `SortableTable`s `sortValue` im Sort-Comparator), brechen dadurch. Wo eine CT-Testkomponente Closures/Callbacks braucht, das offizielle Playwright-"Story"-Pattern nutzen (Fixture-Daten + Closures leben in einer `*.story.tsx`-Datei, die komplett im Browser-Bundle liegt, NICHT als `mount()`-Props vom Test-Runner-Prozess uebergeben) — siehe `frontend/tests-ct/SortableTable.story.tsx`/`SignalBadge.story.tsx` als bereits funktionierende Vorlage.

---

## Task 1: Wunschkader-Planungsmodus CT-Test

**Files:** Create: `frontend/tests-ct/WunschkaderTabPlanungsmodus.ct.tsx`

**Kontext:** `docs/superpowers/plans/2026-08-03-wunschkader-simulationsmodus.md` (Design + Implementierung), Feature bereits live in `WunschkaderTab.tsx` (`simulationMode`/`enterSimulationMode`/`commitSimulation`/`discardSimulation`).

- [ ] Firestore-Mock nach dem Muster von `WunschkaderTabAutoSave.ct.tsx` wiederverwenden/anpassen (gleiche Alias-Technik).
- [ ] Test 1: "Planungsmodus starten" klicken, ein Ziel hinzufuegen → **kein** `setDoc`-Aufruf gegen den Mock (Assertion auf Call-Count 0).
- [ ] Test 2: im Planungsmodus eine Notiz aendern, >800ms warten (Debounce-Fenster) → weiterhin **kein** `setDoc`-Aufruf (deckt explizit den debounced Pfad ab, nicht nur den Sofort-Pfad).
- [ ] Test 3: im Planungsmodus ein Ziel hinzufuegen, "Verwerfen" klicken → Zielliste entspricht wieder exakt dem Stand vor dem Eintritt in den Modus.
- [ ] Test 4: im Planungsmodus ein Ziel hinzufuegen, "Speichern" klicken → **genau ein** `setDoc`-Aufruf, mit dem korrekten Endzustand (inkl. des neuen Ziels) als Payload.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "CT-Test: Wunschkader-Planungsmodus (kein Write waehrend Planung, Verwerfen/Speichern-Verhalten)"`.

## Task 2: AlleSpielerTab — stichprobenartige Filterkombinationen

**Files:** Create oder erweitern: `frontend/tests-ct/AlleSpielerTab.ct.tsx` (falls noch keine existiert, sonst bestehende erweitern — der Audit fand bereits einen schmalen CT-Test fuer den Cursor-Bug, `MarketValueInput`, ggf. in derselben Datei).

- [ ] 2-3 realistische Kombinationen (nicht erschoepfend), z.B.: (a) Position="Sturm" + Verfuegbarkeit="Frei" zusammen; (b) Marktwert-Bereich + Namenssuche zusammen; (c) ein Rang-Checkbox + Position zusammen. Pro Kombination: Fixture mit mind. 4-5 Spielern, von denen nur eine Teilmenge beide Filter erfuellt, Assertion auf genau diese Teilmenge.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "CT-Test: AlleSpielerTab stichprobenartige Filterkombinationen (Position+Verfuegbarkeit, Marktwert+Suche, Rang+Position)"`.

## Task 3: DashboardTab — Sektionsreihenfolge + richtiges Modal

**Files:** Create: `frontend/tests-ct/DashboardTab.ct.tsx`

- [ ] Test 1: Fixture mit `own_squad_ids.length === 17` → "Verkaufen"-Sektion erscheint im DOM VOR "Kaufen" (Reihenfolge pruefen, z.B. per `boundingBox().y`-Vergleich oder DOM-Reihenfolge-Query).
- [ ] Test 2: Fixture mit `own_squad_ids.length < 17` → "Kaufen" erscheint vor "Verkaufen".
- [ ] Test 3: eine Verkaufen-Karte (`PlayerCard`) anklicken → `PlayerDetailModal` oeffnet (NICHT `TransfermarktDetailModal`).
- [ ] Test 4: eine Kaufen-Karte (`TransfermarktCard`) anklicken → `TransfermarktDetailModal` oeffnet (NICHT `PlayerDetailModal`).
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "CT-Test: DashboardTab Sektionsreihenfolge (Kaderlimit-abhaengig) + korrektes Detail-Modal je Kartentyp"`.

## Task 4: App.tsx — Swipe blockiert bei offenem Modal (E2E)

**Files:** Modify: `frontend/tests-e2e/TouchScrubVsSwipe.spec.ts` (neuen Testfall ergaenzen) ODER neue Datei `frontend/tests-e2e/SwipeBlockedByModal.spec.ts`, je nachdem was beim Lesen der bestehenden Datei sinnvoller anschliesst.

- [ ] Ein Modal oeffnen (z.B. ein Wunschkader-Detail-Modal oder EigenesTeam-Detail-Modal — eines reicht, wie im Chat entschieden), denselben Touch-Drag ausfuehren, der ausserhalb eines Modals den Tab wechselt, Assertion: Tab wechselt NICHT waehrend das Modal offen ist.
- [ ] Positiv-Kontrolle (bereits etabliertes Testmuster dieses Projekts, siehe HANDOFF/`ML-Charts Mobile`-Touch-Test): derselbe Touch-Drag nach dem Schliessen des Modals wechselt den Tab tatsaechlich — bestaetigt, dass der Test ueberhaupt etwas prueft.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "E2E-Test: Swipe-Tab-Wechsel bei offenem Modal blockiert (modalOpenTracker-Pfad, bisher nie end-to-end geprueft)"`.

## Task 5: PlayerCompareModal — alle 7 Vergleichszeilen

**Files:** Create: `frontend/tests-ct/PlayerCompareModal.ct.tsx`

- [ ] Zwei Spieler-Fixtures mit bewusst unterschiedlichen Werten in ALLEN 7 Dimensionen: `ml_prediction`, `ml_prediction_3d`, `signal` (hoeher=besser), `market_value` (NIEDRIGER=besser), `starting_rank` (NIEDRIGER=besser), `status_label` (Fitness — `null`/leer=fit gewinnt gegen einen gesetzten Status), `average_points` (hoeher=besser).
- [ ] Fuer jede der 7 Zeilen: Assertion, dass die Seite mit dem "besseren" Wert die hervorgehobene (`font-semibold text-brand-*`) Seite ist — je einmal auch den "keiner gewinnt"-Fall (`null`/gleich) fuer mindestens eine der numerischen Zeilen.
- [ ] Tests laufen lassen, bestehen.
- [ ] Commit: `git commit -m "CT-Test: PlayerCompareModal Gewinner-Hervorhebung, alle 7 Vergleichszeilen inkl. Fitness-Sonderfall"`.

## Finale Verifikation + PR

- [ ] `npm run typecheck && npm run test -- --run && npm run build` — alles gruen.
- [ ] Falls Playwright-Browser in dieser Sandbox erst neu eingerichtet werden muessen: bekannter Workaround aus `HANDOFF.md`/frueheren Sessions (`apt-get download` + `dpkg-deb -x` fuer die Chromium-Systembibliotheken, kein Root noetig) — bereits mehrfach in dieser Session erfolgreich genutzt, `~/.cache/ms-playwright`/`/tmp/chromedeps` koennten schon von einer frueheren Session gecacht sein.
- [ ] Branch erstellen, alle Commits pushen: `git push -u origin test-coverage-scoped-followup`.
- [ ] `gh pr create --title "Test-Coverage Follow-up: Planungsmodus/AlleSpieler/Dashboard/Swipe/Compare" --body "Siehe docs/superpowers/plans/2026-08-03-test-coverage-scoped-followup.md"`.
- [ ] `gh pr merge --auto --squash`, auf die 4 Required Checks warten, Merge bestaetigen. **Falls ein Check fehlschlaegt** (wie beim letzten Batch mit den Funktions-Props-ueber-mount()-Problem): tatsaechlich die CI-Logs lesen und den echten Fehler beheben, nicht raten — siehe Global Constraints, Lektion aus PR #7.
