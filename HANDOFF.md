# Handoff: KickbaseAgent Dashboard — Players-Map-Redesign FERTIG (Worktree, nicht gemerged/gepusht)

**Generated**: 2026-07-29 (Ende der Session)
**Branch**: `worktree-smooth-inventing-popcorn` (Worktree unter `.claude/worktrees/smooth-inventing-popcorn`), ~26 Commits vor `origin/main` (Merge-Base `1923c05`)
**Status**: Code-komplett und durchgehend reviewt, aber **weder gemerged noch gepusht**. Das komplette players-Map-Redesign (21 Plan-Tasks) ist umgesetzt, per `subagent-driven-development` (ein Subagent pro Task + Review dazwischen) durchgeführt, plus 3 während der Umsetzung gefundene und gefixte Korrekturen an bereits abgenickten Tasks, plus eine finale Whole-Branch-Review mit einem Fix-Wave danach. Backend-Tests: 90/90 grün. Frontend `tsc`: exakt 1 Fehler (bekannt, vorbestehend, `ui.tsx`/`ImportMeta.env`). **Nächster Schritt liegt beim User**: Branch reviewen/mergen/pushen, danach die einmaligen Produktions-Migrationsschritte (Task 9) durchführen — das kann kein Agent für den User übernehmen (Push-Policy, Produktions-Firestore-Credentials).

## Goal

KickbaseAgent-Dashboard von 5 parallelen, namensverknüpften Firestore-Arrays auf eine einzige `players`-Map (`player_id -> Rohdaten`) plus dünne Referenzlisten umstellen, und alle ableitbaren Berechnungen (Signal/Fairwert/Status-Text/Trend/Budget/ROI/Hype-Gipfel/Auktions-Countdown) vom Backend ins Frontend verschieben (`frontend/src/lib/derive.ts`, neu). Ziel: kleineres Firestore-Dokument, `player_id` statt Name als einziger Join-Key, keine serverseitige Ableitungslogik mehr duplizieren.

## Completed

- [x] **Alle 21 Plan-Tasks umgesetzt** (`docs/superpowers/plans/2026-07-29-players-map-datenstruktur.md`), jeweils Implementer-Subagent + dedizierte Task-Review, mehrere mit Fix-Runden:
  - Backend (Tasks 1-9): `points_avg`→`average_points`-Umbenennung, `_build_players_map()`/`_build_transfermarkt_listings()`/`_build_wunschkader_targets()` neu, 14 tote Ableitungsfunktionen gelöscht, `export()` neu verdrahtet, `_resolve_is_light()` erkennt Alt-Schema-Snapshots als Cold-Start (Selbstheilung), `migrate_wunschkader_player_ids.py` (einmaliges Migrationsskript, **noch nicht gegen Produktion gelaufen**, siehe Not Yet Done).
  - Frontend Shared Lib (Tasks 10-14): `types.ts` neue Wire-Typen, `derive.ts` (Bewertung, DST-sicherer Auktions-Status, Builder-Funktionen, Budget-Plan), `wunschkaderResolve.ts` (geteilter `player_id`-Resolver).
  - Frontend Tab-Migrationen (Tasks 15-19): Alle 5 Tabs (Alle Spieler, Transfermarkt, Spekulation, Eigenes Team, Wunschkader) von altem Schema auf `players`-Map umgestellt, gemeinsamer Live-Ticker (`useNow`) in `App.tsx` konsolidiert.
  - Cleanup (Tasks 20-21): Alte optionale Typen aus `types.ts` entfernt, alte `index.html` + `/old/`-GitHub-Pages-Deploy retiriert.
- [x] **3 Korrekturen an bereits abgenickten Tasks gefunden und gefixt** (Details siehe Failed Approaches — das ist der wichtigste Lern-Abschnitt dieser Session):
  1. **DST-Bug** in `nextUpdateCutoff()` (Auktions-Countdown-Cutoff): war bis zu 1h falsch in einem ~9h-Fenster/Jahr um die beiden Zeitumstellungen (inkl. Samstagabend-Prime-Time) — gefunden, gefixt (Zwei-Pass-Offset-Auflösung am Ziel-Zeitpunkt statt an `now`), verifiziert per erschöpfendem minütlichem Sweep gegen das originale Python-`zoneinfo`-Verhalten (30.965+ Stichproben, 0 Abweichungen).
  2. **Budget-Regression**: mehrere bereits abgenickte Tasks (4 Backend, 10/11/13 Frontend) hatten versehentlich die alte, in dieser Session bereits gefixte `actual_bid`+10%-Schätzungs-Logik wieder eingeführt, statt der echten Transfermarkt-Gebotsdaten. Betraf BEIDE Hälften des ursprünglichen Fixes (Commits `43c4854`/`fe40a39`): Eingeplanter-Preis UND Verkaufserlöse-Ableitung. Beide Hälften korrigiert, backend- und frontend-seitig, inkl. Test-Updates.
  3. **`position`-Feld-Lücke**: `RawWunschkaderTarget` verlor sein `position`-Feld im neuen Schema (Plan-Lücke), aber Wunschkader-UI brauchte es für Formations-Gruppierung — gelöst durch Live-Auflösung pro Spieler (`resolveTarget(...).position`) statt Speicherung auf dem Ziel-Objekt.
- [x] **Finale Whole-Branch-Review durchgeführt** (opus, über alle 26 Commits), Ergebnis "Ready to merge: With fixes" — ein Fix-Wave mit 5 Punkten umgesetzt und re-reviewt: Absturz-Guard in `App.tsx` gegen Alt-Schema-Snapshots (kein Error-Boundary vorhanden, hätte White-Screen verursacht), tote `PlayerRow`/`EigenesTeamRow`-Typ-Duplikate entfernt, `SpekulationTab` auf geteilten `auction_status` statt eigener Neuberechnung umgestellt, `SpekulationRow` um `player_id` ergänzt (React-Key-Kollisionsrisiko), `kForPosition` gegen fehlendes `position_k` abgesichert.
- [x] **Backend-Tests**: 90/90 grün (`python3 -m unittest discover -s tests`). **Frontend `tsc`**: exakt 1 Fehler, bekannt/vorbestehend (`ui.tsx`/`ImportMeta.env`, siehe Backlog).

## Not Yet Done

- [ ] **Task 9 — Produktions-Migration, MUSS nach Push durch den User laufen** (kein Agent kann das, siehe Warnings): (1) Branch reviewen und nach `main` mergen/pushen; (2) `gh workflow run dashboard-marktwerte.yml` einmal manuell anstoßen, damit `dashboard_snapshot/latest` sofort ins neue Schema kommt; (3) `gh run watch <run-id> --exit-status` abwarten; (4) `python -m src.migrate_wunschkader_player_ids` lokal gegen Produktions-Firestore ausführen (braucht `GOOGLE_APPLICATION_CREDENTIALS`/`FIRESTORE_ENABLED=1`), Warnungen (ungelöste Namen) prüfen und ggf. manuell in der Firebase-Konsole nachtragen; (5) `src/migrate_wunschkader_player_ids.py` + zugehörigen Test danach löschen (einmaliges Skript) und committen. **Bis dieser Schritt läuft**: Wunschkader-Ziele ohne `player_id` degradieren clientseitig sichtbar zu "Unbekannt (null)"-Kacheln, `handleSave()` blockiert das Speichern in diesem Zustand aktiv (Schutz vor Datenverlust) — kein Crash, aber Budget-Zahlen wären falsch, bis migriert ist.
- [ ] **Ligaanalyse-Detailansicht (Idee, NICHT urgent)** — jetzt entsperrt, da das players-Map-Redesign (Voraussetzung) fertig ist. Beim Klick auf einen Manager in der Ligaanalyse-Karte sollen Grundinfos + Kaderliste angezeigt werden (analog zu `EigenesTeamTab.tsx`s `PlayerDetailModal`). `get_manager_squad()` (`src/kickbase_client.py`) existiert schon, wird in `_build_ligaanalyse()` bereits pro Manager aufgerufen. **Vor Umsetzung: `superpowers:brainstorming` durchlaufen** (neue Feature-Idee) — dabei gegen die NEUE `players`-Map-Struktur planen.
- [ ] Aus der finalen Review zusätzlich vorgeschlagen, nicht umgesetzt (Empfehlungen, keine Blocker): ein Contract-Test für `export()`s Top-Level-Key-Set (würde künftiges Backend/Frontend-Feld-Drift als Testfehler statt stillem Live-Bug sichtbar machen — höchster Empfehlungswert laut Reviewer); die im Ledger als "outstanding" markierte Live-Differential-Prüfung für `auction_status` gegen echte Produktionsdaten (Task 16, DST-Mathematik ist bewiesen korrekt, aber End-to-End-Verdrahtung mit echten `listed_at`/`expires_at`-Werten nie gegen Produktion gelaufen).
- [ ] Bekannte kleine Rest-Punkte aus dem Backlog (unverändert seit früheren Sessions, nicht angefragt, nicht bearbeiten ohne Nachfrage): `frontend/src/vite-env.d.ts` fehlt (verursacht den bekannten `tsc`-Fehler), kein `"typecheck"`-Script in `frontend/package.json`, `prompt_builder.py`s `_cost_per_point()`-Bug, Gebot-Prediction-ML-Modell als perspektivische Idee. Zusätzlich aus der finalen Review als Minor notiert (bewusst nicht gefixt, siehe Ledger): README/Workflow-Kommentare erwähnen noch die entfernte `index.html`, ein paar ungenutzte Firestore-Felder (`total_points`, `pending_offers_count` u.a.) könnten aus dem Dokument entfernt werden (Größen-Optimierung, nicht dringend), `migrate_wunschkader_player_ids.py` hat zwei kleine Kanten-Fälle (harmlos für den einmaligen Hand-Lauf).

## Failed Approaches (Don't Repeat These)

- **Plan-Code kann bereits abgenickte Tasks später als falsch entlarven — cross-task-Konsistenz nicht blind vertrauen.** Der `actual_bid`-Bug (siehe Completed, Korrektur 2) steckte in VIER bereits einzeln reviewten Tasks (4, 10, 11, 13), weil jede Task-Review nur gegen ihre eigene, vom Plan gegebene Referenz (u.a. bereits veraltete Python-Quelle) geprüft hatte, nicht gegen das tatsächlich aktuell schon gefixte Live-Verhalten in `WunschkaderTab.tsx`. **Lektion: bei einem Redesign, das bestehende, bereits gefixte Logik "nur portieren" soll, immer die aktuell laufende Implementierung als Ground Truth nehmen, nicht die vom Plan mitgelieferte Quelle — die kann selbst schon veraltet sein.** Wurde erst beim Cross-Check vor Task 19 (letzter, komplexester Tab) entdeckt, weil dort zum ersten Mal alle Puzzleteile zusammenkamen.
- **Ein Plan-Code-Block kann seinem eigenen Kommentar widersprechen ("1:1 Port") — im Zweifel dem erklärten Ziel folgen, nicht dem Wortlaut.** `derive.ts`s `valuation()` (Task 11) rundete `fairwert` nicht, obwohl der Kommentar "1:1 Port von `_valuation()`" versprach und das Python-Original rundete. Gleiches Muster beim DST-Cutoff (Kommentar "DST-sicher", Code war es in einem Randfall nicht). **Bei solchen Widersprüchen: die Diskrepanz dem Implementer/Reviewer explizit benennen und unabhängig verifizieren lassen, nicht den Code kommentarlos für bare Münze nehmen.**
- **API-Überlastung (529 Overloaded) während der Session** (kurzer, ca. 1h Ausfall laut status.claude.com, betraf alle Modelle) — mehrere Subagent-Dispatches schlugen fehl. **Reaktion, die funktioniert hat**: sofortiger Retry zuerst versucht, danach alle 15 Minuten per `ScheduleWakeup` erneut versucht (User-Vorgabe), bis ein Retry durchging — kein Datenverlust, da fehlgeschlagene Agent-Dispatches nie committet hatten (SDD-Ledger macht genau diese Wiederaufnahme robust, siehe unten).
- (Aus früheren Sessions, weiterhin gültig) **Subagent-Ergebnisse nie ungeprüft übernehmen** — `git diff`/`git status` prüfen, bevor ein Agent-Report für bare Münze genommen wird.
- (Aus früheren Sessions, weiterhin gültig) **Status-Code-Bedeutungen nicht neu raten** — `MDs/codes.md` hat die verifizierte Zuordnung; nur bei neuem, unbeobachtetem Code (Code 8 offen) neu recherchieren, nur mit echtem In-App-Beleg.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Players-Map: EIN Firestore-Dokument bleibt, nur intern als Map statt Arrays | Kein zusätzlicher Read, keine Quota-Verschlechterung; dünne Referenzlisten halten die Dokumentgröße klein |
| Atomarer Cutover, kein Firestore-Doppelschreiben | Hobby-Projekt, ein User; Selbstheilung über erweiterten `_resolve_is_light()`-Cold-Start-Check (altes Schema = Cold Start) |
| Alle ableitbaren Werte client-seitig, nur Rohdaten+ML-Prognose server-seitig | Explizite User-Entscheidung: Cron-Jobs sollen nur aktualisieren, "was wir nicht selbst errechnen können" |
| `actual_bid`-Feld + 10%-Schätzung ersatzlos entfernt (in dieser Session zweimal bestätigt — einmal vor, einmal während des Redesigns) | Manuelles Feld überflüssig, sobald echte Gebotsdaten (`is_own_leading_bid`/`leading_bid_price`) vorliegen |
| `position` nicht mehr auf Wunschkader-Zielen gespeichert, sondern live pro `player_id` aufgelöst | Vermeidet, dass ein gespeichertes Ziel eine andere Position zeigt als der tatsächliche Spieler — strukturell robuster als der alte Zustand |
| Finale Whole-Branch-Review vor Abschluss, mit einem gebündelten Fix-Wave statt Einzel-Fixes | SDD-Skill-Konvention: ein Fix-Dispatch für alle Findings, eine Re-Review, keine zweite Fix-Runde — hat hier 5 Findings sauber in einem Rutsch behoben |

## Current State

**Working**: Backend-Tests 90/90 grün. Frontend `tsc` exakt 1 Fehler (bekannt, vorbestehend). Alle 5 Tabs auf `players`-Map umgestellt, DST-sicherer Auktions-Countdown verifiziert, Budget-Logik konsistent (ein einziger `liveBidFor()`, kein Duplikat mehr). Finale Review + Fix-Wave abgeschlossen und re-reviewt — sauber.

**Broken**: Nichts Bekanntes im Branch-Code selbst. **Aber**: der Branch ist noch NICHT gemerged/gepusht — der live deployte Produktions-Zustand (GitHub Pages, Firestore) läuft weiterhin auf dem ALTEN Schema, bis dieser Branch integriert wird.

**Uncommitted Changes**: Keine — Working Tree ist clean, dieses HANDOFF.md-Update ist der letzte Commit.

**Nicht gemerged/gepusht**: Der komplette Branch (~26 Commits ab Merge-Base `1923c05`) liegt in der Worktree `.claude/worktrees/smooth-inventing-popcorn` auf Branch `worktree-smooth-inventing-popcorn`. Push/Merge nach `main` ist bewusst NICHT durch den Agenten erfolgt (Repo-Policy, siehe Warnings) — das ist der nächste Schritt für den User.

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/plans/2026-07-29-players-map-datenstruktur.md` | Der vollständig umgesetzte Plan — 21 Tasks, alle committed. Bei Bedarf zum Nachvollziehen der ursprünglichen Absicht lesen, aber Vorsicht: mind. 2 Stellen darin sind durch die Korrekturen inzwischen veraltet (siehe Failed Approaches) |
| `.superpowers/sdd/2026-07-29-players-map-datenstruktur/progress.md` | SDD-Ledger dieser Session — jede Task-Review, jeder Fix-Round, alle geparkten/deferred Minor-Findings. Wird typischerweise nach Abschluss gelöscht (Git-History ist jetzt der Record), ist aber bis zum finalen Merge noch da |
| `src/dashboard_export.py` | Zentrale Backend-Export-Logik, komplett neu verdrahtet: `_build_players_map()`/`_build_transfermarkt_listings()`/`_build_wunschkader_targets()`, `_resolve_is_light()`/`_resolve_heavy_data()` |
| `src/migrate_wunschkader_player_ids.py` | Einmaliges Migrationsskript, **noch nicht gegen Produktion gelaufen** — siehe Not Yet Done, Reihenfolge ist wichtig (nach Push, vor oder nach dem ersten Heavy-Lauf, siehe Skript-Docstring) |
| `frontend/src/lib/derive.ts` | Neue geteilte Bibliothek — alle Bewertungs-/Auktions-/Budget-Formeln, inkl. des DST-Fixes und des `liveBidFor()`-Zusammenführungs-Fixes |
| `frontend/src/lib/wunschkaderResolve.ts` | Geteilter `player_id`-Resolver für Wunschkader + Eigenes-Team-Watchlist |
| `frontend/src/App.tsx` | Enthält jetzt den Alt-Schema-Crash-Guard (aus der finalen Review) — zeigt eine Hinweis-Meldung statt abzustürzen, wenn `data.players` fehlt |
| `frontend/src/types.ts` | Neues, bereinigtes Schema — alle Alt-Felder/-Typen entfernt (Task 20 + finale Review) |

## Resume Instructions

1. **Branch reviewen und mergen/pushen.** Diff: `git log --oneline 1923c05..worktree-smooth-inventing-popcorn` (oder direkt in der Worktree unter `.claude/worktrees/smooth-inventing-popcorn`). Push-Entscheidung liegt beim User (siehe Warnings).
2. **Nach dem Push, Task 9 durchführen** (siehe Not Yet Done — Reihenfolge ist wichtig): `dashboard-marktwerte.yml` manuell anstoßen, dann `migrate_wunschkader_player_ids.py` gegen Produktions-Firestore laufen lassen, dann das Skript löschen.
3. **Danach live verifizieren**: neues Dashboard auf GitHub Pages öffnen, alle 5 Tabs durchklicken, insbesondere Wunschkader-Budgetplanung (Cash/Verkaufserlöse/Eingeplant/Spielraum) und Transfermarkt-Auktions-Countdown gegenchecken.
4. **Danach, im selben oder neuen Kontext**: Ligaanalyse-Detailansicht (Phase 2, siehe Not Yet Done) — `superpowers:brainstorming` zuerst.

## Setup Required

- Nichts Neues — gleiches Firebase-Projekt/Secrets wie bisher, gleiche GitHub-Actions-Secrets. Für Task 9's Migrationsskript: `GOOGLE_APPLICATION_CREDENTIALS`/`FIRESTORE_ENABLED=1` lokal gesetzt haben.

## Warnings

- **Dieser Branch ist NICHT gepusht/gemerged** — Repo-Ruleset `NeverPushOnMain` seit der Public-Umstellung aktiv, Agenten pushen grundsätzlich nicht auf `main`. Der User muss den Branch selbst reviewen, mergen und pushen.
- **Task 9 (Produktions-Migration) kann kein Agent für den User übernehmen** — braucht Produktions-Firestore-Credentials und muss nach dem Push laufen (GitHub Actions liest vom Remote, nicht von lokalen/Worktree-Commits).
- **`npm install`/`npm run` NIE in der Haupt-Sandbox-Checkout ausführen** (Windows-DrvFs-Mount-Risiko für die geteilten `node_modules`) — in isolierten Worktrees (wie dieser Session) ist ein lokales `npm install` dagegen unproblematisch, da die Worktree ihre eigene, vom Haupt-Checkout getrennte `node_modules`-Kopie bekommt (bestätigt diese Session). `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` ist weiterhin der Standard-Verifikationsschritt.
- **Kein Firestore-Doppelschreiben** — der atomare Cutover ist jetzt umgesetzt; nicht nachträglich einen Parallel-Schreibpfad einbauen.
- **Plan-Dokumente können durch spätere Korrekturen veraltet werden** (siehe Failed Approaches) — bei zukünftiger Arbeit an diesem Redesign immer den aktuellen Code, nicht den ursprünglichen Plantext, als Quelle nehmen.
- **Status-Code-Bedeutungen nicht neu raten** — `MDs/codes.md` hat die verifizierte Zuordnung.
