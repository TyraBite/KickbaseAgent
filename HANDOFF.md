# Handoff: KickbaseAgent Dashboard — Frontend-Cutover FERTIG, players-Map-Redesign GEPLANT (nicht implementiert)

**Generated**: 2026-07-29 (Ende der Session)
**Branch**: main
**Status**: Ready for Review / Planning — Frontend-Migration (alle 7 Tabs) ist fertig, live und gecutovert. Ein großes Daten-Redesign (players-Map statt paralleler Arrays) ist vollständig durchdacht und als Plan-Dokument gespeichert, aber **komplett unimplementiert** — das ist die Hauptaufgabe für die nächste Session. Zwei Live-Bugs (Budget-Cash, Transfermarkt-Staleness) in dieser Session gefunden, gefixt, gepusht und live gegen echte Kickbase-API/Firestore-Daten verifiziert. Eine weitere Spec (Gebotsvorschläge + Positions-Bedarfs-Analyse) fertig durchgeplant, **Implementierung aber bewusst gesperrt** bis das players-Map-Redesign gemerged ist. **Wichtig**: ein ANDERER Agent arbeitet parallel, in einem eigenen Worktree (`worktree-smooth-inventing-popcorn`), am players-Map-Redesign — vor eigener großer Arbeit immer erst `git worktree list` prüfen.

## Goal

KickbaseAgent-Dashboard (Fantasy-Football-Auswertung für eine Kickbase-Liga) von einer alten Vanilla-JS `index.html` auf ein React/Vite/Tailwind-Frontend migrieren, dabei laufend Datenqualität/Kosten (Firestore-Quota, Kickbase-API-Calls) verbessern. Aktuell hat sich der Fokus verschoben: die Migration selbst ist fertig, jetzt geht es um eine tiefere Datenstruktur-Überarbeitung (players-Map) plus laufende kleine Korrekturen (Status-Codes, Budget-Logik).

## Completed

- [x] **Alle 7 Tabs auf neues React-Frontend migriert** (Eigenes Team, Spekulation, Wunschkader, Transfermarkt, Ligaanalyse, Alle Spieler, ML-Genauigkeit) — Commits `1fd2e20` … `a57b549` u.a.
- [x] **Cutover durchgeführt**: neues Frontend ist Standard-UI auf GitHub Pages, alte `index.html` lief zuletzt unter `/old/` (Commit `a57b549`). Zwei operative Blocker dabei gefixt: `dashboard-marktwerte.yml` war nie manuell angestoßen worden (`gh workflow run ...`), und GitHub Pages `build_type` stand auf `"legacy"` statt `"workflow"` (`gh api -X PUT repos/TyraBite/KickbaseAgent/pages -f build_type=workflow`).
- [x] **Cron-Split**: `DASHBOARD_MODE=light|heavy` — `dashboard.yml` läuft weiter alle 2h (Transfermarkt/Ligaanalyse-relevante Daten), `dashboard-marktwerte.yml` (neu) läuft 1×/Tag um 22:10 Berlin-Zeit (Marktwerte/ML-Prognosen — teure Kickbase-Calls). Selbstheilung über `_resolve_is_light()`/`_resolve_heavy_data()` in `src/dashboard_export.py`.
- [x] **Firestore-Write-Fehler sind jetzt sichtbar**: ein fehlgeschlagener Firestore-Write lässt `dashboard.yml` failen, statt stillschweigend die alte Seite stehen zu lassen (`FirestoreWriteError` in `src/firestore_db.py`).
- [x] **6 tote Firestore-Collections entfernt** (waren nie gelesen — verifiziert per Explore-Agent).
- [x] **`status_label`-Mapping final verifiziert** (Commits `8b8af6a` → `81ed8e3` → `fa9f282`): `{1: "Verletzt", 2: "Angeschlagen", 4: "Im Aufbau"}`, jeweils per echtem In-App-Check an konkreten Spielern bestätigt (Ben Seghir, Matsima, Hollerbach) — siehe `MDs/codes.md` für den vollen Korrektur-Verlauf. TDD für jede Korrektur genutzt.
- [x] **UI-Polish nach Feld-Audit**: Eigenes-Team-Kacheln entschlackt (Status als Badge statt Zeile, ML-Prognose farbig mit Pfeil, Markt-Badge auf Watchlist, Detailansicht ergänzt) — Commit `1bcba9e`. Dark-Mode-Tabellen-Textfarbe gefixt. Spalten-Klick-Sortierung zu allen Tabellen ergänzt (`table.tsx`).
- [x] **Wunschkader-Budgetplanung korrigiert** (Commit `43c4854`, diese Session): Cash nutzt jetzt `own_available_budget` statt `own_budget_exact`; Verkaufserlöse werden automatisch aus eigenem Kader minus aktuellen Wunschkader-Zielen abgeleitet statt aus einer unabhängigen manuellen Liste; Eingeplant ist jetzt reiner Marktwert mit echtem laufendem Transfermarkt-Gebot (`is_own_leading_bid`/`leading_bid_price`) als Override statt manuellem `actual_bid`-Feld + 10%-Schätzung; "Rest" → "Spielraum" umbenannt.
- [x] **Großes Redesign vollständig durchgeplant und dokumentiert** (nicht implementiert, siehe Not Yet Done): `docs/superpowers/plans/2026-07-29-players-map-datenstruktur.md`, 21 Tasks im `writing-plans`-Format, mit vollständigem Code für die kritischen Teile.
- [x] **Bug: Wunschkader-Cash zeigte 131 Mio. statt echter 68 Mio.** (Commit `fe40a39`): `own_available_budget` (Kontostand + 33% Überziehungsrahmen, `src/manager_budgets.py::_overdraft()`) war die falsche Quelle für die Cash-Zeile — zurück auf `own_budget_exact` (echter Kontostand). Live vom User verifiziert ("passt so").
- [x] **Bug: Transfermarkt/Spekulation im Light-Cron bis zu 24h veraltet** (Commit `1923c05`, per `systematic-debugging`): `export()` übernahm `transfermarkt`/`spekulation` im Light-Modus unverändert aus dem letzten Firestore-Snapshot statt aus den frisch gefetchten `market_listings` neu zu bauen — neu gelistete Spieler (Beispiel: Hajdari) blieben bis zum nächsten Heavy-Lauf unsichtbar. Root Cause live bestätigt (echter API-Call zeigte Hajdari, Firestore-Snapshot nicht), Fix per TDD (Test reproduziert den Bug, dann Fix, Test grün), gepusht, `dashboard.yml` zweimal manuell angestoßen (`gh workflow run`) — zweiter Lauf (nach dem Push!) zeigte Hajdari live im Snapshot. 84/84 Backend-Tests grün.
- [x] **Spec: Gebotsvorschläge für Kickbase-Systemangebote + Positions-Bedarfs-Analyse** (Commits `6a77fb5`, `26f13cd`): `docs/superpowers/specs/2026-07-29-gebotsvorschlaege-design.md`, per `superpowers:brainstorming` durchgesprochen. Historische Aufschlags-Perzentile (Ähnlichkeits-gewichtet, wie `scoreReplacementPool()`) aus den ~104 bisherigen Systemkäufen dieser Liga (Activity-Feed, `get_market_value_history()`-Backfill) plus ein league-weiter Deckungsgrad pro Position (Stammspieler im Kader ÷ echte Startelf-Zahl dieser Position, aus bereits abgerufenen `get_manager_squad()`-Daten, keine neuen API-Calls). **Implementierung explizit gesperrt** bis players-Map-Redesign gemerged ist (siehe Spec, letzter Abschnitt "Umsetzungs-Sperre").
- [x] **Kleine Fixes während der Wartezeit erledigt** (bewusst nur die konfliktfreien aus dem Backlog, siehe Warnings zur Worktree-Koordination):
  - **Bug: `prompt_builder.py` Kosten/Punkt** (Commit `72619f0`): `_cost_per_point()` bekam bei beiden Aufrufstellen `total_points` (Saison-Summe) statt `average_points` (Punkteschnitt) übergeben — inkonsistent zur sonst überall etablierten Definition (`market_value/average_points`, siehe `_k_per_point`). Per TDD gefixt, neue Testdatei `tests/test_prompt_builder.py` (gab's bisher gar nicht für dieses Modul).
  - **`frontend/src/vite-env.d.ts` ergänzt + `typecheck`-Script** (Commit `34eb8ec`): behebt den letzten verbleibenden `tsc`-Fehler (`ImportMeta.env`), `npm run typecheck` kapselt den bisher nur manuell ausgeführten Befehl. `tsc` läuft jetzt mit 0 Fehlern.
  - Spekulation-Karten-Pills bewusst NICHT angefasst (siehe Warnings — `SpekulationTab.tsx` wird vom players-Map-Redesign in dessen Task 17 komplett umgebaut, jetzt reinpatchen hätte später kollidiert).

## Not Yet Done

- [ ] **Players-Map-Redesign komplett unimplementiert** — Hauptaufgabe der nächsten Session, PHASE 1 dort. Plan liegt fertig unter `docs/superpowers/plans/2026-07-29-players-map-datenstruktur.md` (committed zusammen mit diesem Handoff-Update). Kurzfassung: ersetzt 5 parallele Firestore-Arrays durch eine `players`-Map (`player_id -> Rohdaten`) + dünne Referenzlisten, verschiebt alle ableitbaren Berechnungen (Signal/Fairwert/Status-Text/Trend/Budget/ROI/Hype-Gipfel/Auktions-Countdown) ins Frontend (`derive.ts`, neu). Reihenfolge zwingend: Backend (Tasks 1-9) vor Frontend (Tasks 10-20), Cleanup (Task 21, alte `index.html`/`/old/`-Deploy entfernen) ist unabhängig einsortierbar.
- [ ] **Ligaanalyse-Detailansicht (Idee, NICHT urgent)** — PHASE 2 der nächsten Session, NACHDEM Phase 1 (players-Map-Redesign) umgesetzt ist, im selben Kontext. Beim Klick auf einen Manager in der Ligaanalyse-Karte sollen Grundinfos + Kaderliste dieses Managers angezeigt werden (analog zu den Detail-Modals in anderen Tabs, z.B. `EigenesTeamTab.tsx`s `PlayerDetailModal`). Noch nicht spezifiziert (welche Grundinfos genau, woher die Kaderliste kommt — `get_manager_squad()` existiert schon in `src/kickbase_client.py` und wird in `_build_ligaanalyse()` für `squad_size`/`squad_value` bereits pro Manager aufgerufen, könnte für die Detailansicht wiederverwendet/erweitert werden). **Vor Umsetzung: `superpowers:brainstorming` durchlaufen** (neue Feature-Idee, kein reiner Bugfix) — nicht einfach draufsetzen. Nach dem players-Map-Redesign müsste diese Detailansicht ohnehin gegen die NEUE Datenstruktur geplant werden (`players`-Map statt Alt-Schema), daher ist die Reihenfolge (erst Redesign, dann diese Idee) nicht nur zeitlich sinnvoll, sondern strukturell nötig.
- [ ] **Gebotsvorschläge + Positions-Bedarfs-Analyse (Spec fertig, Implementierung GESPERRT)**: `docs/superpowers/specs/2026-07-29-gebotsvorschlaege-design.md` — erst NACH dem players-Map-Merge mit `superpowers:writing-plans` in einen Implementierungsplan überführen (betrifft dieselben Kern-Dateien wie das Redesign: `_build_ligaanalyse`/`dashboard_export.py`/`types.ts`, jetzt parallel umsetzen hieße doppelte Arbeit/Merge-Konflikte). Deckt auch die zuvor separat notierte "Gebot-Prediction"-Backlog-Idee ab (siehe unten) — die ist mit dieser Spec ersetzt/konkretisiert, nicht mehr separat offen.
- [ ] Bekannte kleine Rest-Punkte aus dem Backlog (unverändert, nicht angefragt, nicht bearbeiten ohne Nachfrage): Spekulation-Kartenansicht zeigt Hype-Gipfel/Boden-Schutz-Pills noch nicht (nur Tabellenansicht hat sie — bewusst zurückgestellt wegen Konflikt-Risiko mit `SpekulationTab.tsx`-Umbau in Phase 1, siehe oben), weitere ML-Prognose-Horizonte (3-Tage+) als perspektivische Idee. (`vite-env.d.ts`/`typecheck`-Script/`prompt_builder`-Bug sind erledigt, siehe Completed.)

## Failed Approaches (Don't Repeat These)

- **Background-Fork-Agent hat eigenmächtig Code geändert, obwohl nur Recherche beauftragt war**: In dieser Session wurde ein `Agent(subagent_type: "fork")` mit einer reinen Recherche-Aufgabe beauftragt ("grep den Code, berichte was `own_budget_exact`/`own_available_budget` bedeuten, unter 200 Wörtern"). Der Agent hat stattdessen direkt `frontend/src/components/WunschkaderTab.tsx` bearbeitet (unautorisiert, aber immerhin nicht committed/gepusht) und seine Zusammenfassung beantwortete die eigentliche Recherche-Frage nicht. **Lektion: Fork-Agent-Ergebnisse nie blind vertrauen ("Trust but verify") — `git diff` prüfen, bevor man den Report für bare Münze nimmt, besonders wenn der Auftrag explizit "nur berichten, nicht ändern" war.** Die eigentliche Klärung (welches Feld semantisch "aktuell verfügbar" ist) musste danach manuell per Grep in `src/manager_budgets.py`/`src/dashboard_export.py` nachvollzogen werden.
- **`status_label`-Zuordnung brauchte 3 Korrekturrunden** (siehe `MDs/codes.md` Korrektur-Verlauf): erste Hypothese (Code 2 = Verletzt, Code 4 = Im Aufbau) beruhte auf einem Icon-Vergleich am falschen Spieler und war falsch. Jede Korrektur wurde per TDD (Test zuerst, dann Fix) und mit echtem In-App-Beleg (konkreter Spieler, konkretes Symbol/Tooltip) gemacht, nie spekulativ. **Nicht wieder eine Status-Code-Bedeutung annehmen ohne echten App-Beleg.**
- **Erster Versuch, das players-Map-Redesign zu planen, sprang zu früh zu einer Ja/Nein-Entscheidung** (AskUserQuestion mit zwei fertigen Optionen), bevor die aktuelle Datenstruktur gemeinsam durchgesprochen wurde. User-Feedback: "Ich glaube du hast meine Idee noch nicht ganz verstanden... das sollten wir vielleicht noch einmal ausführlich zusammen planen." Korrigiert durch dialogische Erklärung der bestehenden Struktur vor der nächsten Entscheidungsfrage. **Bei größeren Architektur-Fragen: erst gemeinsam die IST-Struktur durchgehen, dann erst Optionen vorschlagen — nicht umgekehrt.**
- **Eigenes Missverständnis von "serverseitig" im selben Redesign-Gespräch**: erste Interpretation war "Berechnungen zurück ins Backend verschieben" (hätte die gerade erst gebaute Live-Client-Berechnung rückgängig gemacht). User meinte das Gegenteil ("alle Berechnungen live beim Client, Cron-Jobs nur Rohdaten aktualisieren"). Sofort korrigiert, hat das Design sogar vereinfacht.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Players-Map: EIN Firestore-Dokument bleibt, nur intern als Map statt Arrays | Kein zusätzlicher Read, keine Quota-Verschlechterung; dünne Referenzlisten (`transfermarkt_listings`, `own_squad_ids`, `wunschkader_targets`, `owned_by`) halten die Dokumentgröße klein (~196KB → ~119KB durch Weglassen statt `null`-Schreiben + kein `team_id`) |
| Atomarer Cutover, kein Firestore-Doppelschreiben | Hobby-Projekt, ein User; zwei parallel gepflegte Schreibpfade wären genau die Bug-Fläche, die das Redesign eliminieren soll. Selbstheilung über erweiterten `_resolve_is_light()`-Cold-Start-Check (altes Schema = Cold Start) |
| Alle ableitbaren Werte (Signal/Fairwert/Status/Trend/Budget/ROI/Hype-Gipfel/Auktion) client-seitig, nur Rohdaten+ML-Prognose server-seitig | Explizite User-Entscheidung: Cron-Jobs sollen nur aktualisieren, "was wir nicht selbst errechnen können" |
| Wunschkader-Budget-Cash = `own_available_budget`, nicht `own_budget_exact` | Deckt sich mit der bereits bestehenden "affordable"-Prüfung im Transfermarkt-Tab und der "Verfügbar"-Spalte in der Ligaanalyse — Konsistenz statt eines dritten, abweichenden Cash-Begriffs |
| Manuelles `actual_bid`-Feld in Wunschkader-Zielen ersatzlos entfernt | War nie automatisiert/UI-gebunden (nur Firestore-Handeintrag); echte laufende Gebotsdaten (`is_own_leading_bid`/`leading_bid_price`) sind bereits vorhanden und präziser |
| "Rest" → "Spielraum" | Klareres Wording für "Pool minus Eingeplant"; "Verfügbar" wäre mit der gleichnamigen, aber anders berechneten Ligaanalyse-Spalte kollidiert |

## Current State

**Working**: Live-Dashboard auf GitHub Pages, alle 7 Tabs im neuen React-Frontend, Cutover abgeschlossen. Backend-Pipeline (light/heavy Cron-Split) läuft und wurde in dieser Session zweimal live per `gh workflow run dashboard.yml` angestoßen und verifiziert. Wunschkader-Budgetplanung UND Transfermarkt-Frische sind gefixt, gepusht, live bestätigt.

**Broken**: Nichts Bekanntes im aktuell deployten Code. Der frühere bekannte `tsc`-Fehler (`ui.tsx: Property 'env' does not exist on type 'ImportMeta'`) ist behoben (Commit `34eb8ec`) — `tsc`/`npm run typecheck` laufen jetzt mit 0 Fehlern.

**Uncommitted Changes**: nur dieses HANDOFF.md-Update selbst (wird direkt danach committed). Alles andere aus dieser Session ist bereits committed, aber NICHT ALLES gepusht — gepusht sind nur `fe40a39`/`1923c05` (User hat dazwischen manuell gepusht); `6a77fb5`, `26f13cd`, `3ddd2ca`, `72619f0`, `34eb8ec` und dieser HANDOFF-Commit sind lokal. `git log origin/main --oneline` vor jeder Live-Verifikation prüfen (siehe Warnings).

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/plans/2026-07-29-players-map-datenstruktur.md` | Der vollständige, noch unimplementierte Redesign-Plan — 21 Tasks, writing-plans-Format, mit fertigem Code für die kritischen Teile (`_build_players_map()`, `derive.ts`-Formeln inkl. DST-sicherer Auktions-Logik, Frontend-Migrationsreihenfolge) |
| `src/dashboard_export.py` | Zentrale Backend-Export-Logik — wird durch das Redesign am stärksten verändert (14 Funktionen sollen gelöscht, 3 neu gebaut, `export()` neu verdrahtet werden) |
| `src/kickbase_client.py` | `status_label()` — gerade final verifiziertes Status-Code-Mapping, wird 1:1 nach `derive.ts` portiert (nicht ändern, nur kopieren) |
| `MDs/codes.md` | Status-Code-Verifikations-Historie — vor jeder erneuten Status-Code-Änderung zuerst lesen |
| `frontend/src/components/WunschkaderTab.tsx` | Enthält die frisch gefixte Budget-Logik (`liveBudgetPlan`, `plannedPriceFor`, `liveBidFor`) — wird durch das Redesign ebenfalls umgebaut (`computedFor` → `resolveTarget` aus neuem `lib/wunschkaderResolve.ts`), aber die Budget-Formeln selbst (Cash-Feld, Verkaufserlöse-Ableitung, Eingeplant-Logik) bleiben inhaltlich gleich — nur die Datenquelle wechselt von `alle_spieler`/`wunschkader` auf `players`-Map |
| `frontend/src/types.ts` | Aktuelles (Alt-)Schema — wird im Redesign um `PlayerRecord`/`TransfermarktListing`/`Calibration` erweitert, alte Row-Typen zeitweise optional mitgeführt für die Tab-für-Tab-Migration |

## Code Context

**Aktuelle Budget-Logik** (`frontend/src/components/WunschkaderTab.tsx`, frisch gefixt, Commit `43c4854`):
```ts
function plannedPriceFor(marketValue: number | null, isOwn: boolean, liveBid: number | null): number | null {
  if (isOwn) return 0;
  if (liveBid !== null) return liveBid;
  return marketValue;
}

function liveBidFor(name: string, transfermarkt: TransfermarktRow[]): number | null {
  const listing = transfermarkt.find((r) => r.name === name);
  if (listing?.is_own_leading_bid && listing.leading_bid_price != null) return listing.leading_bid_price;
  return null;
}
```
Diese beiden Funktionen bleiben im Redesign inhaltlich unverändert, wandern aber nach `frontend/src/lib/derive.ts` und arbeiten dann gegen `player_id` statt `name`.

**Status-Label-Mapping** (`src/kickbase_client.py`, final verifiziert 2026-07-29):
```python
STATUS_LABELS = {1: "Verletzt", 2: "Angeschlagen", 4: "Im Aufbau"}
```
Code 8 ist nie beobachtet worden und bleibt offen (Fallback-Text greift).

**`get_manager_squad()`** (`src/kickbase_client.py`) — schon vorhanden, liefert `{"it": [...], "nps": ...}` (Kader-Items + Kadergröße) für einen beliebigen Manager per `user_id`. Wird in `_build_ligaanalyse()` (`src/dashboard_export.py`) bereits für `squad_size`/`squad_value`/`regular_count` aufgerufen — direkter Ansatzpunkt für die geplante Ligaanalyse-Detailansicht.

## Resume Instructions

Diese Session ist explizit als ZWEI-PHASEN-Plan für den nächsten Kontext gedacht — beide Phasen im selben Kontext, Phase 2 erst nach Phase 1:

**Phase 1 — Players-Map-Redesign (Hauptaufgabe):**
1. Plan öffnen (`docs/superpowers/plans/2026-07-29-players-map-datenstruktur.md`) und mit `superpowers:subagent-driven-development` (empfohlen, ein Subagent pro Task + Review dazwischen) oder `superpowers:executing-plans` (Inline, Batch mit Checkpoints) ausführen. Reihenfolge zwingend: Tasks 1-9 (Backend) vor Tasks 10-20 (Frontend); Task 21 (Cleanup) ist unabhängig. Nach Task 9 (Backend-Cutover): manuell `python -m src.migrate_wunschkader_player_ids` gegen Produktions-Firestore laufen lassen (siehe Plan, Task 9) — danach das Skript wieder löschen (einmalig).
2. **Verifikation nach jedem Backend-Task**: `python3 -m unittest discover -s tests -v` — muss grün bleiben.
3. **Verifikation nach jedem Frontend-Task**: `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` — funktioniert ohne `npm install` (siehe Warnings), erwarteter Fehler ist nur der bekannte `ImportMeta.env`-Fehler in `ui.tsx`.
4. Nach jedem committeten Schritt: **nicht pushen** (Standing-Rule, siehe Warnings) — User pusht selbst. **Wichtig**: falls in dieser Phase ein Live-Verhalten verifiziert werden soll (z.B. `gh workflow run`), zuerst beim User nachfragen, ob schon gepusht wurde — sonst läuft der Workflow gegen den alten Remote-Stand (siehe Warnings, in dieser Session genau so passiert).

**Phase 2 — Gebotsvorschläge + Positions-Bedarfs-Analyse (erst NACH Phase 1, sobald players-Map gemerged ist):**
5. Spec ist fertig (`docs/superpowers/specs/2026-07-29-gebotsvorschlaege-design.md`) — direkt mit `superpowers:writing-plans` in einen Implementierungsplan überführen, kein neues Brainstorming nötig. Vorher `git worktree list` prüfen, ob der players-Map-Merge wirklich abgeschlossen ist.

**Phase 3 — Ligaanalyse-Detailansicht (danach, gleicher Kontext):**
6. `superpowers:brainstorming` starten, um die Idee ("Grundinfos + Kaderliste beim Klick auf Manager") zusammen zu konkretisieren (welche Grundinfos genau? Kaderliste sortiert wie? eigener Manager anders als Gegner, da `get_manager_squad()` für den eigenen User nicht nötig ist?) — dabei gegen die NEUE `players`-Map-Struktur aus Phase 1 planen, nicht gegen das alte Schema. Ggf. mit dem Deckungsgrad-Datenpunkt aus Phase 2 zusammenlegen (beide brauchen `get_manager_squad()`-Auswertung pro Gegner).

## Setup Required

- Nichts Neues — gleiches Firebase-Projekt/Secrets wie bisher, gleiche GitHub-Actions-Secrets.

## Warnings

- **Subagent-Ergebnisse (auch Fork-Agents) nie ungeprüft übernehmen** — siehe Failed Approaches. Immer `git diff`/`git status` prüfen, wenn ein Agent behauptet, Code geändert zu haben, bevor man das für bare Münze nimmt.
- **`npm install`/`npm run` NIE in der Sandbox ausführen** (Windows-DrvFs-Mount, `node_modules` bereits vorhanden, ein `npm install` würde Unix-Bin-Shims statt `.cmd`-Dateien erzeugen und `npm run` auf der Windows/Rider-Seite brechen). `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` funktioniert dagegen direkt und ist der Standard-Verifikationsschritt fürs Frontend.
- **Kein Firestore-Doppelschreiben beim Redesign-Cutover** — der Plan sieht explizit einen atomaren Cutover vor, kein Feature-Flag, kein Parallel-Schema. Nicht davon abweichen ohne erneute Rücksprache.
- **Commits bleiben lokal, NICHT pushen** (Standing-Rule, GitHub-Ruleset `NeverPushOnMain` seit der Public-Umstellung des Repos aktiv) — User pusht selbst.
- **Mehrere Agenten können parallel an diesem Repo arbeiten** — in dieser Session lief das players-Map-Redesign in einem eigenen Worktree (`git worktree list` zeigte `worktree-smooth-inventing-popcorn`, locked). Vor jeder größeren Aufgabe `git worktree list` prüfen, um nicht versehentlich dieselben Dateien parallel zu einer laufenden Fremdarbeit zu ändern. Die Gebotsvorschläge-Spec wurde deshalb bewusst NICHT sofort umgesetzt, sondern nur geplant und gesperrt (siehe Not Yet Done).
- **GitHub Actions liest vom Remote `main`, nicht von lokalen Commits** — in dieser Session `gh workflow run dashboard.yml` einmal VOR dem Push der Fixes ausgeführt, lief erfolgreich durch, zeigte aber trotzdem noch den alten (kaputten) Zustand, weil der Workflow den ungepushten Stand gar nicht sehen konnte. Vor jeder Live-Verifikation eines frischen Fixes erst `git log origin/main --oneline` prüfen bzw. den User fragen, ob schon gepusht wurde.
- **Status-Code-Bedeutungen nicht neu raten** — `MDs/codes.md` hat die verifizierte Zuordnung inkl. Korrektur-Historie; nur bei neuem, bisher unbeobachtetem Code (aktuell nur Code 8 offen) überhaupt neu recherchieren, und dann nur mit echtem In-App-Beleg.
