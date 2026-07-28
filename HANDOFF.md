# Handoff: KickbaseAgent Dashboard — Phase 6, Sub-Projekt 2 (Wunschkader-Migration) FERTIG, NICHT verifiziert/gepusht

**Generated**: 2026-07-28 (Ende der Session)
**Branch**: main
**Status**: Ready for Review — Sub-Projekt 1 (Spekulation-Tab, siehe `git show 82f0a5f^:HANDOFF.md` für den vollen Vorgeschichte-Stand) ist fertig & mit mehreren Nacharbeit-Runden poliert. **Sub-Projekt 2 (Wunschkader-Tab) ist in DIESER Session komplett fertig implementiert**: Brainstorming-Dialog → Spec → Plan → 6-Task subagent-driven-development-Durchlauf → finaler Whole-Branch-Review → 1 Fix-Wave → clean. Alles lokal committed, NICHT gepusht (Repo-Konvention, siehe Warnings).

## Goal

Wunschkader-Tab (Ziel-Kader-Planung: Formation, Startelf/Bank, Hinzufügen/Entfernen/Ersatzspieler-Suche, Speichern, Budget-Planung) von der alten Vanilla-JS `index.html` auf das neue React/Vite/Tailwind-Frontend (`frontend/`) migrieren — analog zu Sub-Projekt 1 (Spekulation), aber deutlich interaktiver (echtes Schreiben nach Firestore, nicht nur Lesen).

## Completed

- [x] **Brainstorming + Daten-Audit-Dialog** (siehe Konversation): Feld-Liste auf 6 gekürzt (Position-Kürzel, Spieler, Marktwert, Startelf-Rang, Schnitt, Signal — Reihenfolge User-vorgegeben), Rolle/Status/Notiz/ML-Prognose/Geplant-Preis-Spalte komplett raus. Neue Idee des Users mitten im Gespräch: Karten nach Formation gruppieren (Startelf pro Position + Bank, max. Kadergröße 17) — Layout-Optionen als Mockup-Dialog erwogen (visueller Begleiter war in dieser Sandbox NICHT erreichbar, siehe Failed Approaches), stattdessen rein textuell entschieden: Option B (gruppierte Listen nach Position, kein Spielfeld-Grafik-Pitch).
- [x] **Design-Spec geschrieben + committed**: `docs/superpowers/specs/2026-07-28-phase6-sub2-wunschkader-design.md`. Enthält eine wichtige Korrektur mitten im Brainstorming: erste Idee war ein neues Backend-Feld `is_bench`, dann verworfen zugunsten der Wiederverwendung des bestehenden `role`-Strings (`"Bank/Backup-Option"`) — weil die ALTE `index.html` (Wunschkader-Tab + Eigenes-Team-Watchlist) dieselbe Firestore-Daten/Python-Funktion `_build_wunschkader()` liest und sonst gebrochen wäre.
- [x] **Implementation-Plan geschrieben + committed**: `docs/superpowers/plans/2026-07-28-phase6-sub2-wunschkader.md`, 6 Tasks.
- [x] **Alle 6 Tasks per subagent-driven-development implementiert + task-reviewt** (alle "Approved", 1 echter Bug in Task 4 gefunden+gefixt, siehe Failed Approaches):
  1. Backend: `_estimate_price()` auf pauschalen 10%-Aufschlag vereinfacht (ersetzt 2-Stufen-Topspieler-System), `_project_login_bonus()` komplett entfernt, `_build_budget_plan()` verliert die Login-Prämien-Projektion aus dem Pool. 5 neue Unit-Tests.
  2. Frontend-Grundlagen: `frontend/src/types.ts` erweitert (`WunschkaderRow`, `RawWunschkaderTarget`, `BudgetPlan`, `AlleSpielerRow`, `SignalThresholds`), neues `frontend/src/lib/formations.ts` (Formations-Slot-Logik), neues `frontend/src/components/ui.tsx` (Row/Badge/TeamCrest/SignalBadge aus `SpekulationTab.tsx` extrahiert, `Badge` um `"warn"`-Ton erweitert).
  3. `frontend/src/components/WunschkaderTab.tsx` (neu) — read-only Grundgerüst: Formation-Dropdown, 4 Positions-Gruppen mit Slot-Zählern, Bank-Sektion, Budget-Plan-Kachel (ohne Hinweistext), Detail-Modal.
  4. Detail-Modal-Aktionen: Bank/Startelf-Toggle, Entfernen, Wechsel-Suche (Vorschläge + Freitextsuche, 1:1 aus `index.html` portiert).
  5. Hinzufügen: leerer Positions-Slot (Position vorbelegt, nur Name nötig) + genereller Bank-Button (Name + Position).
  6. Speichern (`setDoc` nach `wunschkader/current`, `{targets, formation, updated_at}`, `merge: true`) + zweiter aktiver Tab in `App.tsx` (echtes Tab-Switching eingeführt, vorher gab's das gar nicht).
- [x] **Finaler Whole-Branch-Review (opus)**: fand 3 weitere Important-Bugs, die erst im Zusammenspiel aller 6 Tasks sichtbar wurden (siehe Failed Approaches). Alle in EINER Fix-Wave behoben + re-reviewt: **clean, "Ready to merge: With fixes" → Fixes angewendet.**
- [x] **Echter TypeScript-Compile-Check lief tatsächlich** (wichtige Sandbox-Erkenntnis!): `cd frontend && node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` funktioniert OHNE `npm install`, weil `node_modules/` schon auf dem Windows-Mount liegt. Ergebnis: **0 neue Fehler**, nur 1 vorbestehender, unrelated Fehler (`ui.tsx: Property 'env' does not exist on type 'ImportMeta'` — fehlendes `frontend/src/vite-env.d.ts`, siehe Not Yet Done).
- [x] **Voller Python-Testlauf grün**: `python3 -m unittest discover -s tests -v` → 67/67 (nicht nur `test_dashboard_export`, auch `test_manager_budgets`/`test_market_predictor` unberührt/grün).

## Not Yet Done

- [ ] **Echter Browser-Test fehlt komplett** — `npm run dev` wurde in dieser Session nie ausgeführt (Sandbox-Konvention). Muss der User selbst machen (siehe Resume Instructions).
- [ ] **Live-Datenrisiko ungeprüft** (wichtigster offener Punkt!): `isBench()` in `WunschkaderTab.tsx` erkennt Bank-Ziele nur an `role === "Bank/Backup-Option"` (exakter String, den die alte `index.html`s Hinzufügen-Formular NIE erzeugt — dessen `<select>` bietet nur `"Starter"`/`"Bank"`/`"Backup"`, siehe `index.html` Zeile ~841). Ob die ECHTEN Firestore-Daten (`wunschkader/current`) `"Bank/Backup-Option"` oder `"Bank"`/`"Backup"` verwenden, konnte ich aus der Sandbox NICHT prüfen (kein Firestore-Zugriff). Wenn die echten Daten `"Bank"`/`"Backup"` sind, zeigt der neue Bank-Bereich leer/falsch — **erster Check beim Browser-Test**.
- [ ] `frontend/src/vite-env.d.ts` fehlt (`/// <reference types="vite/client" />`) — würde den einen verbleibenden `tsc`-Fehler beheben. Kein Blocker, aber jetzt bekannt und leicht behebbar.
- [ ] Kein `"typecheck": "tsc --noEmit"`-Script in `frontend/package.json` — wäre sinnvoll für Sub-Projekt 3, da der finale Reviewer entdeckt hat, dass `tsc` in dieser Sandbox tatsächlich läuft (siehe Warnings).
- [ ] Sub-Projekt 3 (restliche 5 Tabs) und Sub-Projekt 4 (Cutover) — unverändert spätere Schritte, siehe `docs/superpowers/specs/2026-07-28-phase6-frontend-rearchitektur-sub1.md` Roadmap.
- [ ] GitHub-Pages-Source-Umstellung — falls noch nicht gemacht (siehe frühere Handoff-Version).

## Failed Approaches (Don't Repeat These)

- **Visueller Begleiter (Browser-Mockup-Tool) für die Formation-Layout-Frage versucht, gescheitert**: `superpowers:brainstorming`s Mockup-Server gestartet (`start-server.sh --project-dir /workspace/work --open`), User konnte `http://localhost:<port>/?key=...` nicht erreichen (`ERR_CONNECTION_REFUSED`) — auch nach Rebind auf `--host 0.0.0.0`. Diese Sandbox-Umgebung exponiert offenbar keine lokalen Ports zum Browser des Users, obwohl das Dateisystem ein Windows-Mount ist (WSL2-typisches Verhalten greift hier nicht). Fallback: Layout-Optionen rein textuell im Chat beschrieben, User hat direkt entschieden (Option B). **Für künftige Sessions: visuellen Begleiter in dieser Sandbox erst gar nicht anbieten, oder gleich vorwarnen dass es wahrscheinlich nicht erreichbar ist.**
- **Erster `role`/Bank-Zuordnungs-Ansatz (neues `is_bench`-Backend-Feld) verworfen**: siehe Design-Spec — hätte die alte `index.html` gebrochen (liest dieselbe Firestore-Struktur). Stattdessen: reine Wiederverwendung des bestehenden `role`-Strings, kein Backend-Schema-Change.
- **Task-4-Fix-Runde 1 hat einen ECHTEN Bug im Plan selbst aufgedeckt**: mein eigener Plan-Code für `replaceTarget()` hatte `{ name: replacement.name, position: replacement.position, role: t.role }` — kein Spread, verliert `_uid` (React-Key-Kollision nach mehreren Ersetzungen) und `note`/`actual_bid`. Gefixt auf `{ ...t, name: ..., position: ... }`, PLAN-DATEI selbst korrigiert (Commit `43f0c31`), damit ein künftiger Re-Run des Plans den Bug nicht wiederholt.
- **Finaler Whole-Branch-Review fand 2 weitere, subtilere Bugs, die kein Einzel-Task-Review sehen konnte** (erst im Zusammenspiel aller 6 Tasks sichtbar):
  1. Der GEFIXTE `replaceTarget` aus Task 4 hatte einen NEUEN Fehler: der Spread `{ ...t, ... }` übernahm jetzt zwar `_uid`/`role` korrekt, aber auch `note`/`actual_bid` des ALTEN (ersetzten) Spielers auf den NEUEN Spieler — hätte z.B. ein echtes 16,2-Mio.-Gebot (Stage) auf einen frisch eingewechselten Spieler übertragen und die Budget-Planung verfälscht. Fix: `note`/`actual_bid` gezielt aus dem Spread ausschließen.
  2. `App.tsx`s bedingtes Rendering (`{condition && <Component/>}`) unmountet die inaktive Komponente komplett beim Tab-Wechsel — erst reproduzierbar, seit es überhaupt 2 klickbare Tabs gibt (Task 6). Hätte unsaved Wunschkader-Edits beim Tab-Wechsel stillschweigend gelöscht. Fix: beide Tabs bleiben immer gemountet, nur `hidden`-Klasse togglet Sichtbarkeit.
  3. (Kleiner) Beide neuen Modals (Detail/Hinzufügen) hatten kein Escape-Handling, obwohl der Spekulation-Tab das schon hat — nachgezogen für Konsistenz.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `role`-String wiederverwenden statt neues Backend-Feld | Alte `index.html` liest dieselbe Firestore-Struktur/Python-Funktion, Backend-Schema-Änderung hätte sie gebrochen |
| Formation-Gruppierung: Option B (gruppierte Listen) statt Pitch-Grafik oder flaches Grid | User-Wunsch nach Sichtbarkeit von "wie viele Slots pro Position noch offen" bei überschaubarem Bau-Aufwand |
| Pauschale 10%-Budget-Schätzung statt 2-Stufen-Markup | User-Wunsch: "schnell im Kopf nachrechenbar" statt Präzision — Live-Beobachtung des Liga-Bietverhaltens als spätere Idee notiert, nicht Teil dieser Runde |
| Login-Prämie komplett aus Budget-Rechnung raus | Expliziter User-Wunsch, auch aus der Berechnung (nicht nur Anzeige) |
| Beide Tabs bleiben gemountet (CSS `hidden` statt Conditional Rendering) | Verhindert Datenverlust bei Tab-Wechsel — vom finalen Review gefunden, nicht ursprünglich geplant |
| Kein zweiter Fix-Wave nach dem finalen Review | Skill-Konvention: genau EIN Fix-Wave + EIN scoped Re-Review nach dem finalen Review, danach Eskalation an User statt Endlos-Loop — Re-Review kam clean zurück, also nicht nötig |

## Current State

**Working**: Phase 1-5 (`index.html`) unverändert live. Spekulation-Tab (Sub-Projekt 1) fertig poliert. **Wunschkader-Tab (Sub-Projekt 2) ist jetzt vollständig im Code fertig** — Formation-Auswahl, gruppierte Karten, Bank-Sektion, Hinzufügen/Entfernen/Bank-Toggle/Wechsel, Speichern, Budget-Plan-Kachel.

**Ungetestet**: Kompletter Wunschkader-Tab wurde noch NIE im echten Browser gesehen — nur Code-Review + echter `tsc`-Typecheck (0 Fehler) + Python-Unit-Tests (67/67 grün). Kein `npm run dev`, kein echter Login-Test, kein echter Firestore-Write-Test.

**Uncommitted Changes**: Keine — `git status` ist clean, working tree sauber.

**Commits dieser Session** (alle lokal, NICHT gepusht): `47b9ca0` (Spec) bis `c21de9e` (finaler Fix), 10 Commits total für Sub-Projekt 2, plus die bereits vorher vorhandenen Sub-Projekt-1-Nacharbeit-Commits.

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/specs/2026-07-28-phase6-sub2-wunschkader-design.md` | Volle Design-Entscheidungen inkl. der `role`-vs-`is_bench`-Korrektur |
| `docs/superpowers/plans/2026-07-28-phase6-sub2-wunschkader.md` | 6-Task-Plan, jetzt mit der `replaceTarget`-Korrektur aktuell gehalten |
| `frontend/src/components/WunschkaderTab.tsx` | Die komplette neue Komponente (~500 Zeilen) — Formation-Logik, Karten, Modals, Speichern |
| `frontend/src/components/ui.tsx` | Gemeinsame Primitive (Row/Badge/TeamCrest/SignalBadge), von `SpekulationTab.tsx` UND `WunschkaderTab.tsx` genutzt |
| `frontend/src/lib/formations.ts` | Formation→Slot-Zahl-Mapping (3-4-3/4-3-3/3-5-2/4-4-2) |
| `src/dashboard_export.py` | `_estimate_price()`/`_build_budget_plan()` vereinfacht — betrifft AUCH die alte `index.html` (gewollt) |
| `index.html` | Bleibt produktiv, nur eine trivial-Änderung (Login-Prämie-Zeile in `renderBudgetPlan()` entfernt, sonst nichts angefasst) |

## Code Context

**`WunschkaderTab` Haupt-Signatur** (unverändert seit Task 3, alle späteren Tasks bauen intern darauf auf):
```tsx
export type EditTarget = RawWunschkaderTarget & { _uid: number };
export default function WunschkaderTab({ data }: { data: DashboardSnapshot }): JSX.Element
```

**Bank-Erkennung** (der Punkt aus "Not Yet Done" — live gegenchecken):
```ts
function isBench(target: RawWunschkaderTarget): boolean {
  return target.role === "Bank/Backup-Option";
}
```

**Speichern-Payload** (nach Firestore `wunschkader/current`, `merge: true`):
```ts
const targets = editState.map(({ _uid, ...rest }) => ({ ...rest, role: rest.role ?? "Starter" }));
await setDoc(doc(db, "wunschkader", "current"), { targets, formation, updated_at: updatedAt }, { merge: true });
```

**Wichtige Invariante** (mehrfach im Review geprüft, gilt für JEDEN Codepfad der Ziele schreibt): jedes Ziel-Objekt MUSS ein `role`-Feld mit exakt `"Starter"` oder `"Bank/Backup-Option"` haben — `src/dashboard_export.py`s `_build_wunschkader()` greift per `target["role"]` (kein `.get()`) zu und crasht sonst die noch-live Produktionsseite.

## Resume Instructions

1. **User testet lokal** (`cd frontend && npm run dev`, Windows/Rider): einloggen, Wunschkader-Tab öffnen.
   - **Erster Check**: zeigt der Bank-Bereich die erwarteten Ziele (z.B. Tella/Scherhant aus `MDs/kaderplan.md`)? Falls leer/falsch → `role`-String-Mismatch (siehe Not Yet Done), dann `isBench()` in `WunschkaderTab.tsx` erweitern auf `role === "Bank/Backup-Option" || role === "Bank" || role === "Backup"`.
   - Formation wechseln → Slot-Zähler pro Position aktualisieren sich sofort.
   - Leeren Slot anklicken → Hinzufügen-Dialog mit vorbelegter Position, nur Name eingeben, Enter/Hinzufügen.
   - Kachel anklicken → Detail-Modal, "Wechsel" → Vorschläge + Freitextsuche, Ersatzspieler auswählen → Name/Position tauschen, Rest bleibt (insbesondere `role`).
   - Auf Bank/Startelf umschalten → Kachel wandert in den richtigen Bereich.
   - Tab zu Spekulation und zurück wechseln → **Edits müssen erhalten bleiben** (war der 2. gefundene Bug, jetzt gefixt).
   - Speichern klicken → Statusmeldung "Gespeichert...", danach in Firestore-Konsole prüfen: `wunschkader/current` hat `targets`+`formation`+`updated_at` aktualisiert.
   - Alte `index.html` parallel öffnen → Wunschkader-Tab UND Eigenes-Team-Watchlist dort müssen weiterhin korrekt anzeigen (Kompatibilitäts-Check).
2. **Falls alles grün**: Push (`git push`, Standing-Rule `NeverPushOnMain` — User macht das selbst).
3. **Danach**: Sub-Projekt 3 (restliche Tabs) planen — eigener `superpowers:brainstorming`-Zyklus pro Tab.

## Setup Required

- Nichts Neues — gleiches Firebase-Projekt/Secrets wie bisher.

## Warnings

- **`npm install`/`npm run` NIE in dieser Sandbox** (Windows-DrvFs-Mount-Problem, unverändert) — ABER: `node node_modules/typescript/bin/tsc -p tsconfig.json --noEmit` funktioniert direkt (kein npm, kein Netzwerk nötig, `node_modules` liegt schon da) und wurde in dieser Session erfolgreich als echter Typecheck genutzt. Für Sub-Projekt 3: diesen Befehl von Anfang an als Verifikations-Schritt einplanen statt nur Klammer-Balance-Zählung.
- **Visueller Begleiter (Browser-Mockup) funktioniert in dieser Sandbox nicht** — Port nicht vom Nutzer-Browser erreichbar, auch nicht nach `--host 0.0.0.0`-Rebind. Nicht nochmal versuchen ohne Vorwarnung.
- **`role`-Invariante ist scharf**: jeder Codepfad der ein Ziel-Objekt nach Firestore schreibt MUSS `role` setzen (siehe Code Context) — sonst crasht die alte `index.html`-Seite beim nächsten Pipeline-Lauf.
- Commits bleiben lokal, NICHT pushen (Standing-Rule, `NeverPushOnMain`-Ruleset, User pusht selbst).
