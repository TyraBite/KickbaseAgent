# Handoff: Firestore-Migration Phase 4-5 + Dashboard-Erweiterungen (Alle-Spieler/Wunschkader-Edit)

**Generated**: 2026-07-28 (Ende der Session, Phase 1-3 fertig)
**Branch**: main
**Status**: In Progress — Phase 1-3 done, Phase 4-5 noch zu planen/umzusetzen, danach zwei neue Feature-Requests (bereits geplant, noch nicht umgesetzt)

## Goal

Das Dashboard (`index.html`) von "1x/Tag generierte, self-contained
HTML-Datei" zu einem live-gehosteten, zugriffsgeschuetzten Web-App
umbauen (ersetzt den alten Discord-Daily-Report komplett). 5-Phasen-
Architektur, komplett spezifiziert in
`docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md`.
**Phase 1-3 sind fertig; Phase 4 (ML-Historie), Phase 5 (Mobile/UX)**
stehen noch aus. Danach zwei neue Dashboard-Features (Alle-Spieler-Tab +
editierbarer Wunschkader mit Firestore-Schreibzugriff aus dem Browser) —
**diese kommen NACH Phase 4-5 dran, nicht davor** (expliziter User-Wunsch,
siehe Resume Instructions).

## Completed (diese und letzte Session)

- [x] **Phase 1** (Firestore-Schreibpfad, commit `26546ee`): `src/firestore_db.py`
  spiegelt `src/db.py`s `replace_*`/`upsert_*`-Funktionen als batched
  Firestore-Writes, hinter `FIRESTORE_ENABLED`-Flag.
- [x] **Phase 2** (Firebase Auth + Live-Read, commit `401140f` + Fixes
  `a77387d`): `index.html` ist eine duenne Shell — Login per Firebase Auth
  (Email/Passwort), danach EINMALIGER `getDoc()` von
  `dashboard_snapshot/latest`. `firestore.rules` mit echter UID **deployed**
  (per `firebase-tools` CLI, nicht mehr Console-Copy-Paste — `firebase.json`/
  `.firebaserc` neu im Repo). **Login-Bug gefixt**: zweiter `<script>`-Block
  lief synchron VOR dem `type=module`-Block, der `window.__kickbaseAuth`
  setzt → `Cannot destructure ... undefined`. Fix: beide Blocks `type=module`
  (laufen dann korrekt in Dokument-Reihenfolge). **Voll im Browser
  verifiziert** (Login + Live-Read funktionieren).
- [x] **Firestore-Write in GitHub Action verdrahtet** (`dashboard.yml`):
  neues Secret `FIREBASE_SERVICE_ACCOUNT`, Step schreibt es in
  `$RUNNER_TEMP/firebase-service-account.json`, `FIRESTORE_ENABLED=1` +
  `GOOGLE_APPLICATION_CREDENTIALS` gesetzt. Live per `gh workflow run`
  getestet, `update_time` in Firestore matcht Action-Log-Timestamp exakt —
  bestaetigt echter End-to-End-Write aus der Action.
- [x] **Nicht-kategorisiert-Fallback entfernt** (`_split_eigenes_team`):
  Spieler, die nicht in `wunschkader.json`s `targets` stehen, landen jetzt
  direkt bei Verkaufskandidaten statt in einem separaten Bucket
  (User-Entscheidung, siehe Key Decisions).
- [x] **Phase 3** (Hosting/Deploy):
  - Repo `TyraBite/KickbaseAgent` ist **public** (Security-Audit vorher:
    komplette Git-History auf Secrets gescannt, nichts gefunden).
  - `index.html` (vorher `docs/dashboard.html`) an den Repo-Root verschoben
    — `docs/` ist jetzt ausschliesslich Dokumentation (User-Wunsch).
    GitHub Pages deployt vom Root, laeuft: https://tyrabite.github.io/KickbaseAgent/
  - `dashboard.yml`-Cron auf alle 2h umgestellt (`15 */2 * * *`).
  - `daily.yml` (alter Discord-Job) entfernt.
  - **Wichtiger Fund**: bestehendes Ruleset `NeverPushOnMain` (seit 25.07.,
    vorher auf privatem Repo nicht enforced) greift jetzt, da Repo public —
    direkter Push auf `main` braucht PR+Approval. Angepasst: Repo-Owner
    (`RepositoryRole` actor_id `5`) hat jetzt `bypass_mode: always`, kann per
    Merge-Button durchmergen. **Siehe Warnings fuer neuen Workflow.**
- [x] **Kaderplanung (Torwart)**: Rönnow-Gebot verloren — an **Fassii**,
  fuer 7.900.558. **Zentner** (Mainz, Rang 1, 9.68M) als Plan-A. **Noch
  keine Kaufentscheidung final umgesetzt.**

## Not Yet Done

- [ ] **Phase 4** (ML-Historie nutzen): `ml_prediction_log`-Collection
  fuer Genauigkeits-Trend-Anzeige im Dashboard nutzen, perspektivisch
  datengetriebene Modell-/Hyperparameter-Wahl.
- [ ] **Phase 5** (Mobile/UI-UX): braucht laut Spec einen dedizierten
  User-Interview-Schritt VOR dem Design — noch nicht begonnen.
- [ ] **Feature-Request 1 — Alle-Spieler-Tab**: neuer Dashboard-Tab mit
  allen ~450 Liga-Spielern, filterbar. Plan fertig, siehe Files to Know.
- [ ] **Feature-Request 2 — Editierbarer Wunschkader**: Zielspieler direkt
  im Dashboard ersetzen/entfernen/hinzufuegen, echter Client-Firestore-
  Schreibpfad. Plan fertig, siehe Files to Know.
  **Explizite Reihenfolge-Vorgabe: erst NACH Phase 4-5.**
- [ ] **Torwart-Kaufentscheidung**: Zentner tatsaechlich bieten/kaufen,
  `data/wunschkader.json`s Rönnow-Eintrag (`targets[0]`) noch NICHT auf
  "verloren an Fassii" aktualisiert.

## Failed Approaches (Don't Repeat These)

- **Baumann (Fleischmanns' aktives Verkaufsangebot) als Torwart-Empfehlung
  vorgeschlagen**, bevor der User praezisierte: nur echte Free-Agents
  (bei KEINEM Manager im Kader) zaehlen.
- **Hein (Bremen) wirkte wie ein Steal** (Ø 164 Punkte) — war ein
  2-Spiele-Sample, Rauschen. Immer `points_avg` gegen `get_player_performance()`s
  echte Spielanzahl gegenchecken.
- **User erinnerte sich, Backhaus sei Bremens Torwart** — spielt inzwischen
  fuer Freiburg. Immer gegen Live-Daten pruefen statt alte Erinnerungen
  fortzuschreiben (siehe `feedback_verify_data_before_asserting`).
- **Plan-Mode-Subagent konnte Phase-2-Implementierung nicht ausfuehren**,
  weil er den Plan-Mode-Zustand der Hauptsession erbte. Fix: erst im
  Hauptthread `ExitPlanMode` aufrufen, DANACH Implementierungs-Agent dispatchen.
- **`gh api -X POST`/`gh pr merge --admin` werden vom Sandbox-Classifier
  geblockt** (GitHub Pages aktivieren, Ruleset-Bypass-Merge) — GET/Read
  geht durch, Write/riskante Actions nicht. Kein Workaround versuchen,
  User macht diese Schritte selbst im Browser.
- **Subagent-Dispatch fuer "Repo public machen" wurde ebenfalls geblockt**
  (Classifier stuft die Aktion selbst als zu riskant fuer autonomen
  Subagenten ein, auch mit expliziter User-Freigabe) — musste direkt in der
  Hauptsession ausgefuehrt werden statt per `subagent-driven-development`-
  Dispatch.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `dashboard_snapshot/latest` als EIN Firestore-Dokument statt Client liest rohe Collections | Vermeidet Duplizierung von Join-/ML-/Fairwert-Logik in Client-JS |
| Einmaliger Read (kein `onSnapshot`) | Passt zum 2h-Update-Takt, verhindert Reset von Filter/Sortierung |
| `index.html` (Repo-Root) statt `docs/dashboard.html` | User-Wunsch: `docs/` bleibt reine Dokumentation, GitHub Pages deployt vom Root |
| Firestore-Rules-Deploy per `firebase-tools` CLI statt Console-Copy-Paste | Automatisierbar, User wollte das nicht manuell wiederholen |
| Nicht-kategorisiert-Fallback entfernt, Default = Verkaufskandidaten | User-Entscheidung: jeder Spieler ausserhalb der Wunschkader-Targets ist automatisch Verkaufskandidat, kein separater Zwischenzustand mehr |
| Repo public + GitHub Pages vom Root | User-Freigabe nach Security-Audit (keine Secrets je in Git-History) |
| Ruleset-Bypass fuer Repo-Owner statt Ruleset deaktivieren | User wollte den Schutz behalten, nur sich selbst als Ausnahme |
| **Ab jetzt: Commits lokal lassen, NICHT pushen, keine Feature-Branches** | Expliziter User-Wunsch nach dem PR-Vorfall — nur User+Claude entwickeln hier, User pusht selbst (nutzt eigenen Ruleset-Bypass) |

## Current State

**Working**: Phase 1-3 komplett fertig und live verifiziert. Dashboard
laeuft unter https://tyrabite.github.io/KickbaseAgent/, Login+Live-Read
funktionieren, Firestore-Write laeuft automatisch alle 2h per GitHub
Action. Alle 33 Unit-Tests gruen.

**Offen**:
- `data/wunschkader.json`s Rönnow-Eintrag zeigt noch faelschlich "Gebot
  fuehrend" — noch nicht auf "verloren an Fassii" aktualisiert.
- Torwart-Kaufentscheidung (Zentner?) noch nicht final getroffen.

**Uncommitted lokal (Stand Session-Ende)**: Commit `f9ce868` (Cron 2h +
daily.yml-Entfernung) ist lokal committed, **noch nicht gepusht** — User
pusht das selbst (siehe Warnings).

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md` | Die volle 5-Phasen-Architektur — Phase 4/5 stehen dort nur als Kurzabsatz, brauchen jeweils eigenen Plan->Umsetzungs-Zyklus |
| `docs/superpowers/plans/2026-07-28-phase3-hosting-deploy.md` | Abgeschlossener Phase-3-Plan, als Referenz fuer Struktur/Vorgehen bei Phase 4/5 |
| `/home/node/.claude/plans/hol-dir-den-rest-indexed-clover.md` | **Der fertige, freigegebene Plan fuer die zwei Feature-Requests** — kommt erst nach Phase 4-5 dran |
| `index.html` | Handgepflegte Quelldatei (Repo-Root, nicht mehr `docs/`), NICHT generiert |
| `firestore.rules` / `firebase.json` / `.firebaserc` | Live deployed per `firebase-tools` CLI, echte UID drin |
| `data/wunschkader.json` | `targets[0]` (Rönnow) muss auf "verloren an Fassii, 7.900.558" aktualisiert werden |
| `.github/workflows/dashboard.yml` | Laeuft alle 2h, schreibt nach Firestore. `daily.yml` existiert nicht mehr |

## Resume Instructions

1. **Zuerst**: pruefen ob User Commit `f9ce868` schon gepusht hat
   (`git log origin/main` vs. lokal) — falls nicht, daran denken dass
   Push jetzt User-Sache ist, nicht automatisch machen.
2. **Phase 4** planen (ML-Historie/Genauigkeits-Trend im Dashboard,
   `ml_prediction_log`-Collection nutzen) — eigener Plan->Umsetzungs-Zyklus.
3. **Phase 5** danach (Mobile/UX, braucht User-Interview-Schritt zuerst).
4. **Erst danach** die zwei Feature-Requests aus
   `/home/node/.claude/plans/hol-dir-den-rest-indexed-clover.md` umsetzen.
5. Torwart-Entscheidung mit User abschliessen (Zentner bieten?),
   `data/wunschkader.json`s Rönnow-Eintrag korrigieren sobald final
   entschieden.

## Setup Required

Nichts Neues — Firebase-Projekt/Service-Account/Firestore/Pages/CI-Secret
alle vollstaendig eingerichtet und live verifiziert.

## Warnings

- **Git-Workflow geaendert (wichtig!)**: Ruleset `NeverPushOnMain` ist seit
  Public-Umstellung aktiv enforced (PR+Approval fuer `main`). User hat
  explizit gesagt: Commits ab jetzt LOKAL lassen, NICHT pushen, KEINE
  Feature-Branches anlegen — User pusht selbst (nutzt eigenen
  Ruleset-Bypass). Siehe [[project_kickbaseagent_git_workflow]]-Memory.
- **`firebase-service-account.json` niemals committen** — weiterhin
  gitignored.
- **`gh api -X POST` / `gh pr merge --admin` werden vom Sandbox-Classifier
  geblockt** — solche Schritte muss der User selbst im Browser machen,
  nicht versuchen zu umgehen.
- `MDs/*.md` und `data/kickbase.db` koennen als "modified" auftauchen —
  bekannte CRLF-Sache vom Windows-Tool auf dem geteilten DrvFs-Mount,
  kein inhaltlicher Unterschied.
