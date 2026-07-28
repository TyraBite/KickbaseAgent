# Phase 6: Frontend-Rearchitektur — Roadmap + Sub-Projekt 1 (React/Vite/Tailwind-Pilot)

## Context

Das Dashboard ist seit Phase 1-5 auf eine handgepflegte `index.html`
(Vanilla JS/CSS, ~1470 Zeilen, kein Build-Schritt) gewachsen. User hat
angesichts wachsender Funktionalitaet/UI-Anspruch 4 Themen aufgeworfen und
per Interview geklaert:

1. Trivial: Zeilen-Zaehler neben Tab-Namen (`updateTabBadges()`) raus -
   "bringt keinen Mehrwert". In Sub-Projekt 1 miterledigt.
2. **Architektur**: echter Wechsel auf React + Vite + Tailwind CSS (gegen
   die urspruengliche "Vanilla aufraeumen"-Empfehlung entschieden).
3. **Visuell**: Karten/Dashboard-Stil statt Tabellen-Optik.
4. **Backend/API**: urspruenglich ueberlegt (duenne Firebase-Cloud-
   Functions-Schicht vor Firestore), dann vom User NOCHMAL verworfen -
   der 2h-Cron-Batch-Job + direktes Client-seitiges Firestore-Read/Write
   funktioniert gut, kein Grund das jetzt anzufassen. **Datenschicht
   bleibt zu 100% wie heute** (Python-Cron schreibt `dashboard_snapshot/
   latest`, Client liest/schreibt direkt per Firebase-Auth+Firestore-SDK,
   `firestore.rules` unveraendert) - dieser Umbau betrifft AUSSCHLIESSLICH
   die Rendering-Schicht (`index.html` → React-Komponenten).
5. **Quick/Detail-View**: EIN globaler Umschalter PRO TABELLE/Tab (nicht
   pro Zeile) - blendet Nebenfelder fuer alle Karten gleichzeitig ein/aus.
   NICHT jeder Tab braucht das zwingend (siehe Spekulation-Ergebnis unten -
   wenn nach dem Daten-Audit nur noch wenige Felder uebrig sind, koennen
   alle direkt sichtbar sein, ohne Umschalter).
6. **Daten-Audit**: gemeinsam Tab fuer Tab live besprochen - umfasst nicht
   nur WELCHE Felder bleiben, sondern auch deren REIHENFOLGE (Punkt 7).
7. **Feld-Reihenfolge**: die alte Tabellen-Spaltenreihenfolge wird NICHT
   einfach uebernommen - pro Tab wird per kurzem Dialog geklaert, was beim
   Ueberfliegen einer Karte zuerst/prominent stehen soll (Entscheidungs-
   relevanz statt historischer Spaltenreihenfolge). Gilt als generelles
   Prinzip fuer ALLE Tabs, nicht nur den Piloten.

**Weitere Entscheidungen aus dem Interview**:
- Hosting bleibt GitHub Pages (nicht auf Firebase Hosting umgezogen).
- Sandbox-Workflow: kein `npm install`/`npm run` in der KI-Sandbox (bekanntes
  Windows-DrvFs-Mount-Problem) - CI baut, lokale Vorschau macht der User
  selbst in Rider auf seinem echten Windows-Rechner.
- Rollout: Parallelbetrieb - die bestehende `index.html` bleibt live/
  unveraendert nutzbar, bis der neue Frontend fertig+freigegeben ist, dann
  bewusster Cutover (kein Big-Bang-Ersatz).

## Warum in Sub-Projekte zerlegt

Der komplette Umbau (7 Tabs migrieren + Daten-Audit pro Tab + Cutover) ist
zu gross fuer einen Plan/eine PR. Roadmap:

| # | Sub-Projekt | Umfang | Status |
|---|---|---|---|
| 1 | **Scaffolding + Pilot** | Neues `frontend/`-Projekt (React+Vite+Tailwind), EIN Tab migriert (Spekulation, direkter Firestore-Read wie heute), CI baut+deployt parallel neben der alten `index.html` | **Umgesetzt** (dieser Spec) |
| 2 | Wunschkader-Migration | Interaktivster Tab (Wechsel-Suche, Speichern) - weiterhin direktes Client-seitiges `setDoc`, kein Cloud-Function-Umweg | Spaeter, eigener Plan |
| 3 | Restliche Tabs migrieren | Transfermarkt, Eigenes Team, Alle Spieler, Liga, ML-Genauigkeit - je eigener Daten-Audit-Dialog wie bei Spekulation | Spaeter, eigener Plan |
| 4 | Cutover + Decommission | Alte `index.html` durch neues Frontend ersetzen, alten Code entfernen | Spaeter, eigener Plan |

## Sub-Projekt 1: Daten-Audit + Feld-Reihenfolge Spekulation-Tab

Bisherige 9 Felder (`renderSpekulation()` in `index.html`): Spieler,
Position, Preis, Rendite%, Auktion-Status (Kern) + Verein, Trend 7T,
ML-Prognose, Schnitt (Detail). User-Entscheidung: **Position, Verein und
Schnitt komplett raus** (nicht mal als Detail).

Reihenfolge-Dialog (nicht die alte Spalten-Reihenfolge uebernommen):
Spieler-Name zuerst (Wiedererkennung), danach nach Entscheidungsrelevanz.
Ergebnis: **ML-Prognose ist dem User wichtiger als Rendite%** (anders als
die alte Spaltenreihenfolge nahelegte), Auktion-Status steht bewusst GANZ
HINTEN, weil die Karten-Liste ohnehin standardmaessig danach sortiert ist
(die Reihenfolge der Karten selbst transportiert die Dringlichkeit schon).

**Finale Feld-Reihenfolge, alle 5 Felder IMMER SICHTBAR** (kein Quick/
Detail-Umschalter fuer diesen Tab noetig):

1. Spieler (inkl. Hype-Gipfel/Boden-Schutz-Badges)
2. ML-Prognose
3. Rendite%
4. Preis
5. Trend 7T
6. Auktion-Status

## Architektur (umgesetzt)

- Neues Verzeichnis `frontend/` (React 18 + Vite + Tailwind CSS, eigenes
  `package.json` - komplett getrennt vom Python-Projekt-Root). `index.html`
  am Repo-Root bleibt unveraendert (Parallelbetrieb).
- `frontend/src/firebase.ts`: dieselbe Firebase-Config wie in der
  bestehenden `index.html` (apiKey etc. - nicht geheim, Zugriff regeln
  `firestore.rules` + Firebase Auth).
- **Kein Cloud Function/Backend-Umbau**: `frontend/src/App.tsx` liest
  `dashboard_snapshot/latest` genau wie die heutige `index.html` -
  einmaliger `getDoc()` direkt gegen Firestore nach Login (`onAuthStateChanged`),
  ueber dieselbe Firebase-Auth-Session, dieselben `firestore.rules`.
- Struktur: `App` (Auth-Gate: `frontend/src/components/Login.tsx` bis
  eingeloggt) → Layout (Header + Tab-Navigation, nur "Spekulation" aktiv,
  Rest zeigt "(bald)") → `frontend/src/components/SpekulationTab.tsx`:
  - Card-Grid (Tailwind Grid, 1/2/3 Spalten je nach Breite), Felder in der
    oben festgelegten Reihenfolge, alle 5 immer sichtbar.
  - Sortier-Dropdown ("Auktion (Standard)" / Rendite% / Preis) ersetzt die
    bisherige Klick-auf-Spaltenkopf-Sortierung.
  - Suchfeld (Name/Verein-Substring, wie bisher) bleibt erhalten.
  - Farbliche Signal-Badges (Hype-Gipfel/Boden-Schutz/Auktion-dringend)
    als Tailwind-Pills.
  - `frontend/src/format.ts`: `fmtNum`/`fmtSigned`/`trendClass` 1:1 aus
    `index.html` uebernommen (gleiche Rundung/Vorzeichen-Logik).
  - `frontend/src/types.ts`: `SpekulationRow`/`DashboardSnapshot` -
    weitere Snapshot-Felder werden erst bei ihrer Migration typisiert.

## CI/Deploy (umgesetzt)

`.github/workflows/frontend-pilot.yml`: baut `frontend/` (`npm ci && npm
run build` - ausschliesslich in CI), kombiniert das Ergebnis mit der
bestehenden `index.html` zu einem gemeinsamen Pages-Artefakt
(`actions/upload-pages-artifact` + `actions/deploy-pages`): `index.html`
landet unveraendert im Artefakt-Root, `frontend/dist/` landet unter
`preview/`. Alte URL (`.../KickbaseAgent/`) bleibt exakt wie heute, neues
Frontend erscheint unter `.../KickbaseAgent/preview/`.

**Erfordert einen einmaligen manuellen Schritt**: Repo-Settings -> Pages ->
Source von "Deploy from a branch" auf "GitHub Actions" umstellen (macht der
User selbst im Browser, wie bei frueheren Phasen ueblich fuer Pages-Setup).

## Dateien

- `frontend/` (neu): `package.json`, `vite.config.ts` (`base:
  "/KickbaseAgent/preview/"`), `tailwind.config.js`, `postcss.config.js`,
  `tsconfig.json`, `.gitignore`, `index.html`, `src/main.tsx`,
  `src/App.tsx`, `src/firebase.ts`, `src/types.ts`, `src/format.ts`,
  `src/index.css`, `src/components/Login.tsx`,
  `src/components/SpekulationTab.tsx`.
- `.github/workflows/frontend-pilot.yml` (neu).
- `index.html`: `updateTabBadges()` + Aufruf + die vorbereitende
  `btn.dataset.label`-Zeile entfernt (Interview-Punkt 1).

## Verifikation

- `npm run build`/`npm install` laufen NUR in CI bzw. beim User lokal
  (Rider/Windows) - in der KI-Sandbox NICHT ausgefuehrt (bekanntes
  Windows-DrvFs-Mount-Problem aus einem anderen Projekt).
- Durchgefuehrt: manueller Code-Review aller neuen Dateien, Klammer-/
  Klammer-Balance-Check, YAML-Syntax-Check des neuen Workflows
  (`python3 -c "import yaml; yaml.safe_load(...)"`), `node --check` auf
  die beiden bestehenden `<script type="module">`-Bloecke in `index.html`
  nach Entfernen von `updateTabBadges()`.
- **Noch offen (braucht User)**: GitHub-Pages-Source auf "GitHub Actions"
  umstellen, Workflow einmal laufen lassen/pushen, `.../KickbaseAgent/preview/`
  im Browser pruefen (Login, Karten-Layout, Daten stimmen mit dem alten
  Dashboard ueberein, Sortierung + Suche funktionieren, alte URL
  unveraendert erreichbar), danach `npm install`/`npm run dev` einmal
  lokal in Rider fuer die Entwickler-Vorschau.

## Out of Scope (bewusst nicht in diesem Sub-Projekt)

- Wunschkader-Migration - Sub-Projekt 2.
- Die restlichen 5 Tabs + deren Daten-Audit - Sub-Projekt 3.
- Cutover/Entfernen der alten `index.html` - Sub-Projekt 4, erst nach
  User-Freigabe.
- Umzug von Hosting auf Firebase Hosting (bewusst abgelehnt im Interview).
- Jeglicher Cloud-Functions-/Backend-API-Umbau (bewusst verworfen - der
  2h-Cron + direktes Firestore-Read/Write bleibt die Datenschicht,
  unbefristet, nicht nur fuer dieses Sub-Projekt).
