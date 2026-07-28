# Handoff: Firestore-Migration Phase 4-5 + Dashboard-Erweiterungen (Alle-Spieler/Wunschkader-Edit)

**Generated**: 2026-07-28 (Ende der Session, Phase 1-3 + beide Feature-Requests fertig)
**Branch**: main
**Status**: In Progress — Phase 1-3 done, Alle-Spieler-Tab + editierbarer
Wunschkader done (Firestore-only), Phase 4-5 stehen als naechstes an

## Goal

Das Dashboard (`index.html`) von "1x/Tag generierte, self-contained
HTML-Datei" zu einem live-gehosteten, zugriffsgeschuetzten Web-App
umbauen (ersetzt den alten Discord-Daily-Report komplett). 5-Phasen-
Architektur, komplett spezifiziert in
`docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md`.
**Phase 1-3 sind fertig; Phase 4 (ML-Historie), Phase 5 (Mobile/UX)**
stehen noch aus. Die zwei Dashboard-Features (Alle-Spieler-Tab +
editierbarer Wunschkader mit Firestore-Schreibzugriff aus dem Browser)
wurden entgegen der urspruenglichen Reihenfolge-Vorgabe bereits VOR
Phase 4-5 umgesetzt und sind **fertig** — Details siehe Completed.

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
  Spieler, die nicht in den Wunschkader-`targets` stehen (damals noch
  `data/wunschkader.json`, heute Firestore `wunschkader/current` — siehe
  unten), landen jetzt direkt bei Verkaufskandidaten statt in einem
  separaten Bucket (User-Entscheidung, siehe Key Decisions).
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
- [x] **Feature-Request 1 — Alle-Spieler-Tab** (Plan
  `docs/superpowers/plans/2026-07-28-alle-spieler-wunschkader-firestore.md`,
  Tasks 1-6, alle committed, review clean): neuer Dashboard-Tab zeigt alle
  ~450 Liga-Spieler aus `DATA.alle_spieler`, filterbar (Position/Team/Owner/
  Name-Suche). `dashboard_export.py` liefert `alle_spieler` jetzt als Teil
  des Snapshots.
- [x] **Feature-Request 2 — Editierbarer Wunschkader** (selber Plan, Tasks
  1-6): kompletter Wunschkader-Datensatz (`targets`, `sell_list`,
  `markup_rules`, `login_bonus`, `formation`, `season_start`) ist aus
  `data/wunschkader.json` **komplett nach Firestore umgezogen**
  (`wunschkader/current`, EIN Dokument) — die lokale Datei existiert nicht
  mehr. `src/firestore_db.py` hat neue `get_wunschkader()`/
  `upsert_wunschkader()`; `dashboard_export.py` liest von dort und exportiert
  den vollen Rohinhalt zusaetzlich als `wunschkader_raw` im Snapshot, damit
  der Browser beim Speichern den unveraenderten Rest mitschreiben kann.
  `firestore.rules` erlaubt der einen autorisierten UID Schreibzugriff auf
  `wunschkader/current`. Im Wunschkader-Tab des Dashboards jetzt: Namen
  ersetzen, Eintraege entfernen, neue Targets hinzufuegen, "Wechsel"-Button
  mit Vorschlaegen (freie Spieler gleicher Position, Marktwert-/Punkte-Naehe),
  echtes Speichern per `setDoc` direkt aus dem Browser. Alle 39 Tests gruen,
  Migration und Rules-Deploy live gegen echtes Firestore-Projekt verifiziert
  (nicht nur Unit-Tests).

## Not Yet Done

- [ ] **Phase 4** (ML-Historie nutzen): `ml_prediction_log`-Collection
  fuer Genauigkeits-Trend-Anzeige im Dashboard nutzen, perspektivisch
  datengetriebene Modell-/Hyperparameter-Wahl.
- [ ] **Phase 5** (Mobile/UI-UX): braucht laut Spec einen dedizierten
  User-Interview-Schritt VOR dem Design — noch nicht begonnen.
- [ ] **Torwart-Kaufentscheidung**: Zentner tatsaechlich bieten/kaufen,
  der Rönnow-Eintrag (`targets[0]`) in Firestore (`wunschkader/current`,
  ehemals `data/wunschkader.json`) noch NICHT auf "verloren an Fassii"
  aktualisiert.

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
| Kompletter Wunschkader-Datensatz (nicht nur `targets`) lebt komplett in Firestore (`wunschkader/current`), kein Git-Spiegel mehr | User-Entscheidung 2026-07-28: Historie ist nur fuer ML-Ergebnisse relevant, kommt separat in Phase 4 (`ml_prediction_log`) — `data/wunschkader.json` wurde bewusst geloescht statt weiter als Fallback/Backup mitgefuehrt |

## Current State

**Working**: Phase 1-3 komplett fertig und live verifiziert. Dashboard
laeuft unter https://tyrabite.github.io/KickbaseAgent/, Login+Live-Read
funktionieren, Firestore-Write laeuft automatisch alle 2h per GitHub
Action. Alle-Spieler-Tab und editierbarer Wunschkader-Tab sind fertig und
im Dashboard live (Ersetzen/Entfernen/Hinzufuegen/Wechsel/Speichern via
`setDoc`). Wunschkader lebt komplett in Firestore (`wunschkader/current`),
`data/wunschkader.json` existiert nicht mehr. Alle 39 Unit-Tests gruen.

**Offen**:
- Rönnow-Eintrag in Firestore (`wunschkader/current`, `targets[0]`) zeigt
  noch faelschlich "Gebot fuehrend" — noch nicht auf "verloren an Fassii"
  aktualisiert.
- Torwart-Kaufentscheidung (Zentner?) noch nicht final getroffen.

**Uncommitted lokal (Stand Session-Ende)**: Commit `f9ce868` (Cron 2h +
daily.yml-Entfernung) ist lokal committed, **noch nicht gepusht** — User
pusht das selbst (siehe Warnings).

## Files to Know

| File | Why It Matters |
|------|----------------|
| `docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md` | Die volle 5-Phasen-Architektur — Phase 4/5 stehen dort nur als Kurzabsatz, brauchen jeweils eigenen Plan->Umsetzungs-Zyklus |
| `docs/superpowers/plans/2026-07-28-phase3-hosting-deploy.md` | Abgeschlossener Phase-3-Plan, als Referenz fuer Struktur/Vorgehen bei Phase 4/5 |
| `docs/superpowers/plans/2026-07-28-alle-spieler-wunschkader-firestore.md` | Der umgesetzte Plan fuer Alle-Spieler-Tab + editierbaren Wunschkader (Tasks 1-6 fertig, Task 7 = dieser Handoff-Update) |
| `index.html` | Handgepflegte Quelldatei (Repo-Root, nicht mehr `docs/`), NICHT generiert |
| `firestore.rules` / `firebase.json` / `.firebaserc` | Live deployed per `firebase-tools` CLI, echte UID drin — `wunschkader/current` jetzt zusaetzlich fuer diese UID schreibbar |
| `src/firestore_db.py` | Neue `get_wunschkader()`/`upsert_wunschkader()` — Wunschkader-Collection, kein lokaler Fallback mehr |
| **`data/wunschkader.json` existiert nicht mehr** | Kompletter Inhalt lebt jetzt in Firestore-Collection `wunschkader/current` (`targets[0]`/Rönnow muss dort noch auf "verloren an Fassii, 7.900.558" aktualisiert werden) |
| `.github/workflows/dashboard.yml` | Laeuft alle 2h, schreibt nach Firestore. `daily.yml` existiert nicht mehr |

## Resume Instructions

Die zwei Feature-Requests (Alle-Spieler-Tab, editierbarer Wunschkader)
sind fertig — naechste Schritte sind wieder Phase 4/5 aus dem Haupt-Spec:

1. **Zuerst**: pruefen ob der User offene lokale Commits (siehe `git log
   origin/main` vs. lokal) schon gepusht hat — Push ist weiterhin
   User-Sache, nicht automatisch machen.
2. **Phase 4** planen (ML-Historie/Genauigkeits-Trend im Dashboard,
   `ml_prediction_log`-Collection nutzen) — eigener Plan->Umsetzungs-Zyklus.
3. **Phase 5** danach (Mobile/UX, braucht User-Interview-Schritt zuerst).
4. Torwart-Entscheidung mit User abschliessen (Zentner bieten?), Rönnow-
   Eintrag in Firestore (`wunschkader/current`) korrigieren sobald final
   entschieden — jetzt bequem direkt im Dashboard moeglich (editierbarer
   Wunschkader-Tab), kein manuelles JSON-Editieren mehr noetig.

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
