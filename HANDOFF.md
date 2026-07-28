# Handoff: KickbaseAgent Dashboard — Phase 6 Sub-Projekt 1 (React-Pilot) committed, Build-Verifikation läuft

**Generated**: 2026-07-28 (Ende der Session, 2. Update)
**Branch**: main
**Status**: In Progress — Phase 1-5 fertig & live (Details: `git log -p --
HANDOFF.md` fuer die volle Vorgeschichte, oder frueherer Commit
`233fd4d^:HANDOFF.md` fuer den letzten Phase-5-Stand). Phase 6 begonnen —
Frontend-Rearchitektur-Entscheidung getroffen, Sub-Projekt 1 (React/Vite/
Tailwind-Pilot fuer den Spekulation-Tab) implementiert (`0ef19f0`), nach
erstem User-Feedback ueberarbeitet (Kickbase-angelehntes Theme, Detail-
Modal statt Tab-weitem Umschalter, 3-Monats-Hoch/Tief, deutsche Umlaute,
`e3e1a9c`). **Wichtiges Signal**: `frontend/node_modules` + `package-lock.json`
sind waehrend der Session real aufgetaucht (User hat vermutlich selbst
`npm install` auf seinem Windows-Rechner laufen lassen, geteilter DrvFs-
Mount) — `package.json`/`package-lock.json` stimmen exakt ueberein,
Dependency-Aufloesung war erfolgreich. Ein echter `npm run build`/`npm run
dev` ist aber noch nicht nachgewiesen (kein `dist/`-Ordner bisher).

## Goal

Phase 5 war reines CSS/JS-Polish der bestehenden `index.html`. User hat
danach 4 groessere Themen aufgeworfen: (1) wachsende Komplexitaet macht
die Vanilla-JS/CSS-Architektur unhandlich, (2) Frontend soll "schoener"
werden (Karten/Dashboard-Stil statt Tabellen-Optik), (3) "Datenmuell"
(ueberfluessige Spalten/Felder) soll raus, (4) ein Quick/Detail-View-
Konzept pro Tabelle. Nach ausfuehrlichem Interview (siehe Konversation):
kompletter Umbau auf React + Vite + Tailwind CSS, in Sub-Projekte
zerlegt. Voller Kontext + Roadmap:
`docs/superpowers/specs/2026-07-28-phase6-frontend-rearchitektur-sub1.md`.

## Completed (diese Session)

- [x] **Architektur-Interview** (mehrere Runden, siehe Konversation):
  - React + Vite + Tailwind CSS (User-Entscheidung, gegen meine initiale
    "Vanilla aufraeumen"-Empfehlung).
  - **Kein** Cloud-Functions-/Backend-API-Umbau — User hat das nach
    kurzer Ueberlegung WIEDER verworfen: 2h-Cron-Batch-Job + direktes
    Client-seitiges Firestore-Read/Write bleiben unveraendert, nur die
    Rendering-Schicht wird ersetzt.
  - Hosting bleibt GitHub Pages (nicht auf Firebase Hosting umgezogen).
  - Rollout: Parallelbetrieb — alte `index.html` bleibt live, neues
    Frontend erscheint separat unter `.../KickbaseAgent/preview/`, bis
    ein bewusster Cutover erfolgt.
  - Quick/Detail-View: EIN globaler Umschalter PRO Tabelle/Tab (nicht pro
    Zeile), aber nicht jeder Tab braucht ihn zwingend (siehe Spekulation).
  - **Neues generelles Prinzip fuer alle kuenftigen Tab-Migrationen**:
    Feld-REIHENFOLGE wird nicht von der alten Tabelle uebernommen, sondern
    per kurzem Dialog nach Entscheidungsrelevanz neu festgelegt.
- [x] **Daten-Audit + Reihenfolge fuer Spekulation-Tab** (live im Dialog):
  Position, Verein, Schnitt komplett gestrichen (9 -> 5 Felder + Name).
  Finale Reihenfolge: Spieler-Name, ML-Prognose, Rendite%, Preis,
  Trend 7T, Auktion-Status (Auktion-Status bewusst ganz hinten, weil die
  Karten-Liste ohnehin standardmaessig danach sortiert ist). Alle 5 Felder
  immer sichtbar, kein Quick/Detail-Umschalter fuer diesen Tab noetig.
- [x] **Sub-Projekt 1 implementiert** (Commit `0ef19f0`, lokal, NICHT
  gepusht): neues `frontend/`-Verzeichnis (React 18 + Vite + Tailwind,
  eigenes `package.json`, komplett getrennt vom Python-Root), EIN Tab
  migriert (`SpekulationTab.tsx` — Card-Grid, Sortier-Dropdown, Suchfeld,
  Signal-Badges), Firebase-Auth+Firestore-Read 1:1 uebernommen (kein
  Cloud-Function-Layer). Neuer CI-Workflow
  (`.github/workflows/frontend-pilot.yml`) baut `frontend/` und deployt
  es NEBEN der unveraenderten `index.html` unter einem `/preview/`-
  Unterpfad. Trivialer Nebenpunkt erledigt: Zeilen-Zaehler neben den
  Tab-Namen (`updateTabBadges()`) aus der alten `index.html` entfernt.
- [x] **Nacharbeit nach erstem Feedback** (Commit `e3e1a9c`, lokal, NICHT
  gepusht): Kickbase-angelehntes Theme (neue `brand`-Gruenskala in
  `tailwind.config.js`, `slate` statt `neutral`, kein offizieller Marken-
  Hex verifizierbar — `brand.kickbase.com` blockiert automatisierte
  Abrufe, bewusst als Annaeherung markiert). Sortier-Dropdown deckt jetzt
  alle 6 Datenfelder ab (vorher 3). Klick auf eine Kachel oeffnet ein
  Detail-Modal (ersetzt den urspruenglich geplanten globalen Quick/
  Detail-Umschalter fuer diesen Tab — User-Entscheidung nach dem ersten
  Blick auf den Piloten). Modal zeigt zusaetzlich 3-Monats-Tief/-Hoch
  (`market_value_low_92d`/`_high_92d`) — dafuer `_build_spekulation()` in
  `src/dashboard_export.py` erweitert (Felder existierten serverseitig
  schon, wurden nur nicht durchgereicht), neuer Unit-Test dafuer gruen
  (`python3 -m unittest tests.test_dashboard_export`). Verein-Suche
  entfernt (Verein/Position werden gar nicht mehr angezeigt). Deutsche
  Umlaute durchgaengig in allen `frontend/`-Dateien (UI-Texte + Kommentare).

## Not Yet Done

- [ ] **Sub-Projekt 1 ist immer noch nicht GEBAUT/im Browser getestet** —
  in dieser Sandbox gibt es kein `npm`/keinen Build (bewusst, siehe
  Warnings), also nur Code-Review + Klammer-Balance-Check + YAML-Syntax-
  Check gemacht. **Aber**: `frontend/node_modules`+`package-lock.json`
  sind waehrend der Session real entstanden (vermutlich User hat selbst
  `npm install` auf seinem Windows-Rechner laufen lassen, geteilter
  DrvFs-Mount) — `package.json` und `package-lock.json` stimmen exakt
  ueberein, Dependency-Aufloesung war also erfolgreich. Ein `npm run
  build`/`npm run dev` ist noch nicht nachgewiesen (kein `dist/`-Ordner
  bisher). Naechster Schritt siehe Resume Instructions.
- [ ] **GitHub-Pages-Source umstellen**: Repo-Settings -> Pages -> Source
  von "Deploy from a branch" auf "GitHub Actions" — einmaliger manueller
  Schritt, macht der User selbst im Browser (wie bei frueherem Pages-Setup
  ueblich).
- [ ] **Sub-Projekt 2** (Wunschkader-Migration) und **Sub-Projekt 3**
  (restliche 5 Tabs, je mit eigenem Daten-Audit-Dialog) stehen noch aus —
  jeweils eigener Plan/Spec, siehe Roadmap-Tabelle im Spec-Doc.
- [ ] **Sub-Projekt 4** (Cutover, alte `index.html` entfernen) — ganz am
  Ende, erst nach expliziter User-Freigabe.
- [ ] Aus Phase 4 weiterhin offen (unveraendert diese Session):
  Firestore-Read-Quota-Fix isoliert live nachverifizieren, ML-Accuracy-
  Backfill-Fortsetzung (~44 fehlende Tage). Siehe `git show
  233fd4d^:HANDOFF.md` fuer die vollen Befehle/Details.

## Failed Approaches (Don't Repeat These)

- **Automatisierter Build/Test von `frontend/` in dieser Sandbox
  versucht** (`npm --version`, `node -e "require('jsdom')"` etc. in
  frueheren Sessions bereits gescheitert/bewusst unterlassen): kein
  `npm install` hier ausgefuehrt (Windows-DrvFs-Mount-Problem, siehe
  Warnings) — stattdessen nur Code-Review + `python3 -c "import yaml"`
  fuer den Workflow + Klammer-Balance-Check als Ersatz-Verifikation.
- Weitere fruehere Failed Approaches (Baumann/Hein/Backhaus-Verwechslungen,
  Plan-Mode-Subagent-Problem, `gh api -X POST`-Sandbox-Block) weiterhin
  gueltig — siehe `git show 233fd4d^:HANDOFF.md`.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| React + Vite + Tailwind statt "Vanilla aufraeumen" | Explizite User-Entscheidung gegen meine Empfehlung — User will jetzt einen echten Komponenten-/Design-System-Ansatz fuer den Karten-Stil |
| Kein Cloud-Functions-/Backend-Umbau | User hat das nach kurzer Ueberlegung selbst wieder verworfen — 2h-Cron + direktes Firestore-Read/Write funktioniert gut, kein Grund es anzufassen |
| Parallelbetrieb (altes Dashboard bleibt live) statt Big-Bang-Ersatz | User nutzt das Dashboard taeglich, soll waehrend des Umbaus nicht kaputt sein |
| GitHub Pages bleibt (nicht Firebase Hosting) | User-Entscheidung — ein System (GH Pages) statt zwei parallelen Hosting-Systemen zu pflegen war NICHT der Wunsch, aber Firebase Hosting haette Cloud-Functions-Naehe gebraucht, die inzwischen entfaellt |
| Sub-Projekt-Zerlegung (Pilot -> Wunschkader -> Rest -> Cutover) statt ein grosser Plan | Kompletter Umbau ist zu gross fuer einen Plan/eine PR (siehe `superpowers:brainstorming`-Dekompositions-Regel) |
| Feld-Reihenfolge neu nach Entscheidungsrelevanz statt alte Spaltenordnung | User-Wunsch, explizit als generelles Prinzip fuer ALLE kuenftigen Tab-Migrationen festgehalten, nicht nur Spekulation |
| Kein `npm install` in dieser Sandbox | Bekanntes Problem aus einem anderen Projekt auf demselben Windows-DrvFs-Mount (Unix-Bin-Shims statt `.cmd`, bricht dann auf Windows/Rider) — CI baut, User testet lokal selbst |

## Current State

**Working**: Phase 1-5 unveraendert live (`index.html` unter
https://tyrabite.github.io/KickbaseAgent/, inkl. aller Phase-5-Mobile-Fixes
+ Wechsel-Freitextsuche). NEU: `frontend/`-Verzeichnis mit komplettem
React/Vite/Tailwind-Setup fuer den Spekulation-Piloten existiert im Repo,
ist aber noch NIE gebaut/deployt worden.

**Ungetestet/Unverifiziert**:
- Ob `frontend/` ueberhaupt fehlerfrei baut (`npm install && npm run
  build`) — nur Code-Review, kein echter TypeScript-Compile passiert.
- Ob der neue CI-Workflow nach Pages-Source-Umstellung tatsaechlich
  erfolgreich deployt.
- Ob der Spekulation-Pilot im Browser wie gedacht aussieht/funktioniert.

**Commits**: alle Commits dieser Session sind lokal, NICHT gepusht
(Standing-Rule seit Phase 3, siehe Warnings).

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/specs/2026-07-28-phase6-frontend-rearchitektur-sub1.md` | Volle Architektur-Doku + Roadmap fuer Phase 6, inkl. aller Interview-Entscheidungen |
| `/home/node/.claude/plans/ich-bin-kein-frontendler-async-koala.md` | Der in Plan Mode genehmigte Plan fuer Sub-Projekt 1 (Referenz, gleicher Inhalt wie das Spec-Doc) |
| `frontend/` (neu) | Komplettes neues React/Vite/Tailwind-Projekt, eigenes `package.json` — NICHT `npm install` in dieser Sandbox ausfuehren |
| `frontend/src/components/SpekulationTab.tsx` | Die eigentliche Piloten-Komponente — Card-Grid, Sortierung, Suche, Feld-Reihenfolge |
| `frontend/vite.config.ts` | `base: "/KickbaseAgent/preview/"` — muss zum GH-Pages-Unterpfad passen |
| `.github/workflows/frontend-pilot.yml` (neu) | Baut `frontend/`, kombiniert mit `index.html` zu einem Pages-Artefakt |
| `index.html` (Repo-Root) | Bleibt die produktive Seite waehrend des gesamten Parallelbetriebs — NICHT anfassen ausser fuer triviale Sachen wie den entfernten Tab-Zaehler |

## Resume Instructions

1. **Sofort: GitHub-Pages-Source umstellen** (User macht das selbst im
   Browser): Repo-Settings -> Pages -> Source von "Deploy from a branch"
   auf "GitHub Actions".
2. **Danach: `frontend-pilot.yml` einmal laufen lassen** (automatisch bei
   Push auf `main` mit Aenderungen in `frontend/`/`index.html`, oder
   manuell per `workflow_dispatch`/`gh workflow run frontend-pilot.yml`
   nach dem Push).
   - Erwartet: Workflow gruen, `.../KickbaseAgent/preview/` zeigt die neue
     React-App.
   - Falls `npm ci`/`npm run build` in CI fehlschlaegt: das ist der ERSTE
     echte Build-Versuch ueberhaupt (in der Sandbox nie getestet) - Fehler
     im CI-Log gegenlesen, sehr wahrscheinlich kleine Konfigurationsfehler
     in `frontend/package.json`/`vite.config.ts`/`tsconfig.json`.
3. **User testet lokal** (optional, aber empfohlen vor dem CI-Push): in
   Rider auf dem echten Windows-Rechner `cd frontend && npm install &&
   npm run dev` - zeigt sofort ob TypeScript/Vite-Setup grundsaetzlich
   funktioniert, bevor CI es merged.
4. **Im Browser pruefen** (nach Login): Spekulation-Tab im Card-Layout,
   Reihenfolge Name/ML-Prognose/Rendite%/Preis/Trend-7T/Auktion-Status,
   Sortier-Dropdown + Suchfeld funktionieren, Daten stimmen mit dem alten
   Dashboard (`.../KickbaseAgent/`, weiterhin unveraendert erreichbar)
   ueberein. Andere Tabs zeigen "(bald)" und sind nicht anklickbar.
5. **Danach**: Sub-Projekt 2 (Wunschkader-Migration) planen — eigener
   `superpowers:brainstorming`-Zyklus mit Daten-Audit-Dialog fuer diesen
   Tab, wie bei Spekulation.

## Setup Required

- GitHub-Pages-Source-Umstellung (siehe Resume Instructions Punkt 1) —
  noch nicht gemacht.
- Sonst nichts Neues — Firebase-Projekt/Service-Account/Firestore/CI-
  Secrets alle unveraendert vom Vorher-Stand.

## Warnings

- **`npm install`/`npm run` NIE in dieser Sandbox ausfuehren** fuer
  `frontend/` — bekanntes Problem auf dem Windows-DrvFs-Mount (erzeugt
  Unix-Bin-Shims statt `.cmd`, bricht dann auf echtem Windows/Rider, siehe
  `feedback_no_npm_install_in_sandbox_for_windows_projects`-Memory). CI
  (GitHub Actions, sauberer Linux-Runner) baut, User testet lokal auf
  seinem echten Windows-Rechner.
- **Commits bleiben lokal, NICHT pushen** — Ruleset `NeverPushOnMain`
  aktiv, User pusht selbst (siehe `project_kickbaseagent_git_workflow`-
  Memory).
- **`frontend/` ist komplett ungetestet** — erster echter Build passiert
  entweder in CI oder beim User lokal, nicht in dieser Sandbox. Kleinere
  Config-Fehler (Vite/Tailwind/TS-Versionen) sind moeglich, siehe Resume
  Instructions Punkt 2 fuer den Umgang damit.
- `MDs/*.md` und `data/kickbase.db` koennen als "modified" auftauchen —
  bekannte CRLF-Sache vom Windows-Tool auf dem geteilten DrvFs-Mount,
  kein inhaltlicher Unterschied.
