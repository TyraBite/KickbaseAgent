# Handoff: Firestore-Migration Phase 5 + ML-Backfill-Fortsetzung

**Generated**: 2026-07-28 (Ende der Session)
**Branch**: main
**Status**: In Progress — Phase 1-4 done + Firestore-Read-Quota-Fix
(code-fertig, nur Mock-verifiziert), Phase 4s Backfill nur teilweise
(46/90 Tage), Phase 5 (Mobile/UX) steht als naechstes an. **Naechste
Session: ZUERST Quota-Fix live verifizieren, DANN Backfill fortsetzen.**

## Goal

Das Dashboard (`index.html`) von "1x/Tag generierte, self-contained
HTML-Datei" zu einem live-gehosteten, zugriffsgeschuetzten Web-App
umbauen (ersetzt den alten Discord-Daily-Report komplett). 5-Phasen-
Architektur, komplett spezifiziert in
`docs/superpowers/specs/2026-07-27-kickbase-firestore-dashboard-design.md`.
**Phase 1-4 sind fertig (Phase 4s Backfill braucht noch eine Fortsetzung,
siehe unten); nur noch Phase 5 (Mobile/UX) steht aus.**

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
- [x] **Dashboard-Nacharbeit nach erstem Nutzungsfeedback** (Plan
  `docs/superpowers/plans/fuzzy-seeking-raccoon.md`-Inhalt, direkt umgesetzt,
  kein Subagent-Plan-File): Wechsel-/Entfernen-Buttons im Wunschkader-Tab
  waren nicht auffindbar (13-Spalten-Tabelle, Buttons sassen ganz rechts
  ausserhalb des sichtbaren Bereichs) — Spaltenreihenfolge geaendert,
  Buttons jetzt direkt neben dem Namen. Alle-Spieler-Tab: Startelfrang-
  Filter (Dropdown mit Checkboxen, Mehrfachauswahl) + Marktwert-Range-
  Filter (zwei Zahlenfelder, Min 500k/Max = teuerster Spieler aktuell)
  ergaenzt.
- [x] **Phase 4** (ML-Genauigkeit tracken + datengetriebene Modellwahl,
  Plan `docs/superpowers/plans/2026-07-28-ml-accuracy-tracking.md`, Tasks
  1-8 alle committed, review clean inkl. 2 Fix-Runden): siehe eigener
  Abschnitt unten — Code/Tests sind fertig, der einmalige 90-Tage-Backfill
  ist nur zu ~halb (46/90 Tage) durchgelaufen (Firestore-Quota), Rest folgt.
- [x] **Firestore-Read-Quota-Fix** (Plan
  `docs/superpowers/plans/2026-07-28-ml-accuracy-quota-fix.md`, Tasks 1-5
  alle committed, review Approved): der Phase-4-Ansatz (komplette
  `ml_prediction_log`-Collection bei JEDEM der 12 taeglichen Laeufe lesen)
  haette in Produktion ~832% der Firestore-Read-Quota verbraucht (selbst
  nach Fix eines Doppel-Call-Bugs noch ~416%) — komplett auf Tages-
  Aggregat-Dokumente umgebaut, siehe eigener Abschnitt unten. **NUR per
  Unit-Tests (Mocks) verifiziert, KEIN echter Firestore-Call** (User-
  Vorgabe nach dem Quota-Vorfall) — echte Live-Verifikation ist der
  ALLERERSTE Schritt fuer morgen, siehe Resume Instructions.

## Phase 4 im Detail — ML-Genauigkeit tracken + datengetriebene Modellwahl

**Kompletter Code fertig, reviewed, getestet (51 Tests gruen).** Was sich
geaendert hat:

- **Schema-Bruch bei `ml_prediction_log`**: Doc-Id von `{date}_{player_id}`
  auf `{date}_{player_id}_{model_type}` — seit Phase 4 werden **beide**
  Modell-Kandidaten (RandomForest, HistGradientBoosting) taeglich geloggt,
  nicht nur der Tagessieger. `firestore_db.get_prediction_log_entries()`
  (neu, Lesefunktion fehlte bisher komplett) + `upsert_prediction_log_entries()`
  (Doc-Id-Schema angepasst, `.get("model_type")` statt direkter Indexierung
  — Alt-Eintraege ohne dieses Feld duerfen den Batch-Write nicht crashen).
- **Wichtiger Fix**: `market_predictor._load_prediction_log()` las bisher
  NUR aus der lokalen `data/ml_prediction_log.jsonl` — die persistiert seit
  dem `dashboard.yml`-Fix dieser Session (kein Git-Commit/Push von
  `kickbase.db` mehr, siehe Phase 3) NICHT mehr zwischen CI-Laeufen. Liest
  jetzt bei `FIRESTORE_ENABLED` aus Firestore, faellt bei Lesefehler auf
  die lokale Datei zurueck.
- **Live-Modellwahl**: `_select_live_model()` nimmt das Modell mit
  besserer echter Trailing-30d-`sign_accuracy` sobald BEIDE Modelle
  mindestens `MIN_REALIZED_SAMPLES_FOR_SELECTION = 14` auswertbare Tage
  haben, sonst Fallback auf den heutigen synthetischen 75/25-Split
  (bisheriges Verhalten). `metrics["selection_reason"]` zeigt welcher Pfad
  gewaehlt wurde.
- **Backfill-Utility** `market_predictor.backfill_prediction_log(days=90)`
  (dauerhaft im Code, `python -m src.market_predictor --backfill N`):
  trainiert komplett lokal gegen den einmal geladenen Kickbase-Corpus
  (KEINE Firestore-Reads waehrend des Trainings), schreibt am Ende EINEN
  Batch-Write. **Wichtig geworden**: `days=90` erzeugt ~90 × 2 × ~450 ≈
  81.000 Dokumente — das sprengt Firestores Spark-Free-Tier-Tageslimit
  (~20.000 Writes/Tag) unabhaengig vom Batching. Firestore-Write ist jetzt
  in try/except gewrapt (crashte vorher unschoen bei Quota-Fehlern).
- **Neuer Dashboard-Tab "ML-Genauigkeit"**: Kopf-an-Kopf-Karte (aktuelles
  Live-Modell + Grund, Trailing-30d-Werte beider Modelle nebeneinander,
  `null`/zu-wenig-Daten explizit als Hinweistext statt falscher Zahl) +
  Trend-Chart (Inline-SVG, kein Framework, `dataviz`-Skill-Palette
  verifiziert per `validate_palette.js`). Ein SVG-Skalierungsbug (Hover/
  Tooltip zeigte auf breiten Bildschirmen falsches Datum, weil `height`-
  Attribut + `preserveAspectRatio` zu Letterboxing fuehrte) wurde in einer
  Fix-Runde behoben (`style="width:100%;height:auto"` statt fixem `height`).

**Offen — Backfill nur teilweise durchgelaufen**: `--backfill 90` hat die
Firestore-Schreib-Quota gesprengt (81k Dokumente auf einmal). **17.340
Eintraege / 46 distinkte Tage** kamen durch, bevor `RESOURCE_EXHAUSTED`
kam — das liegt schon deutlich ueber der `MIN_REALIZED_SAMPLES_FOR_SELECTION
= 14`-Schwelle, die Live-Auswahl kann also schon arbeiten. Quota hat sich
nach wenigen Minuten von selbst erholt (Read UND Write gingen danach
wieder) — war ein Burst-/Rate-Limit, keine harte Tages-Sperre wie zuerst
befuerchtet.

**User-Entscheidung (2026-07-28)**: restliche ~44 Tage NICHT heute
nachziehen — morgen in kleineren Haeppchen (z.B. 3× `--backfill 15`,
~15 Tage × 2 Modelle × ~450 Spieler ≈ 13.500 Writes pro Lauf, sicher
unter der Tagesgrenze). Trainingslogik ist bereits optimal (kein Firestore-
Read waehrend des Trainings, ein einziger Write am Ende) — das Volumen an
sich (Tage × Modelle × Spieler) ist der begrenzende Faktor, keine
Architektur-Ineffizienz.

## Firestore-Read-Quota-Fix im Detail

Der Backfill-Vorfall deckte ein STRUKTURELLES Problem auf, nicht nur den
einmaligen Backfill-Write: `market_predictor._load_prediction_log()` las
bei JEDEM der 12 taeglichen `dashboard.yml`-Laeufe die KOMPLETTE, taeglich
wachsende `ml_prediction_log`-Collection — und wurde dabei auch noch
**zweimal pro Lauf** aufgerufen (eigener Wiring-Fehler). Hochrechnung zum
Zeitpunkt des Funds: **~832% der 50.000-Reads/Tag-Quota**, selbst nach
Fix des Doppel-Calls noch **~416%** — waere in Produktion taeglich
mehrfach in `RESOURCE_EXHAUSTED` gelaufen.

**Architektur-Aenderung** (Plan `2026-07-28-ml-accuracy-quota-fix.md`):
- `ml_prediction_log` ist jetzt nur noch eine KURZLEBIGE Staging-Zone:
  `firestore_db.get_recent_prediction_log_entries(client, since, before)`
  liest nur ein kleines Zeitfenster (`market_predictor.EVALUATION_LOOKBACK_DAYS
  = 3` Tage), serverseitig per Doppel-Range-Filter auf demselben Feld
  gefiltert (`since <= date < heute` — die exklusive Obergrenze spart
  zusaetzlich die ~25% Reads, die sonst fuer den heutigen, noch gar nicht
  auswertbaren Tag verschwendet wuerden).
- Neue Collection `ml_accuracy_daily` (`{date}_{model_type}`, EIN
  aggregiertes Dokument statt Rohdaten pro Spieler: `{n, sign_correct,
  abs_error_sum}`) ist jetzt die eigentliche Historie-Quelle fuer
  Trailing-Fenster-Auswahl (`_realized_by_model_from_daily`) UND
  Trend-Chart (`_trend_from_daily`) — bleibt bei ~2 Dokumenten/Tag, auch
  nach einem Jahr nur ~730 Dokumente total (statt ~164.000+ vorher).
- `_append_todays_predictions` (schreibt heutige frische Prognosen) nutzt
  jetzt `_load_local_prediction_log()` (NUR lokale Datei, kein
  Firestore-Read mehr an dieser Stelle noetig — Firestore-Upsert ist
  idempotent per Doc-Id, braucht keinen vorherigen Read).
- `backfill_prediction_log` schreibt jetzt DIREKT Tages-Aggregate (kennt
  Prognose UND echten Wert im selben Walk-Forward-Fold, keine spaetere
  Auswertung wie der Live-Pfad noetig) — nutzt jetzt auch dieselben
  Hyperparameter wie die echte Live-Prognose (`_build_candidates()`,
  500-Baum-RandomForest statt der abweichenden 200er aus dem
  unabhaengigen `_walk_forward_backtest`, das selbst NICHT angefasst wurde).
- **Externe Form von `metrics["accuracy_trend"]`/`metrics["realized_by_model"]`
  blieb identisch** (bis auf eine harmlose Nuance: fehlende Modell-Werte
  sind jetzt als fehlender Key statt explizitem `null` reprsentiert,
  von `index.html` ueberall bereits nullish-sicher behandelt) —
  `dashboard_export.py`/`index.html` brauchten dadurch KEINE Aenderung,
  ausser einer bewussten Header-Klarstellung (`metrics["synthetic_winner"]`
  neu, unterscheidet synthetischen Split-Sieger von live gewaehltem Modell).
- **Restrisiko (dokumentiert, kein Blocker)**: Read-Volumen liegt jetzt
  bei geschaetzt ~35-40k/Tag (von 50k Quota) — deutlich besser, aber die
  Marge wird enger je mehr Tage in `ml_accuracy_daily` liegen (die
  Collection selbst waechst nur um 2 Dokumente/Tag, aber `get_accuracy_daily()`
  liest sie komplett bei jedem Lauf — bei einem vollen Jahr ~730 Dokumente
  ist das immer noch trivial, aber im Hinterkopf behalten).

**KEIN echter Firestore-Call wurde fuer diesen Fix ausgefuehrt** (User-
Vorgabe nach dem Quota-Vorfall) — nur `unittest.mock`-basierte Tests (59
gruen). Echte Live-Verifikation ist morgen der ALLERERSTE Schritt, VOR dem
Rest-Backfill.

## Not Yet Done

- [ ] **Quota-Fix live verifizieren** (ALLERERSTER Schritt morgen, VOR
  allem anderen): ein `FIRESTORE_ENABLED=1 python -m src.dashboard_export`-
  Testlauf, pruefen dass `ml_accuracy_daily` befuellt wird und die
  Read-Anzahl (Firebase-Console -> Nutzung, oder `gh`/Firestore-Metriken)
  deutlich niedriger ist als vorher.
- [ ] **Backfill-Fortsetzung**: restliche ~44 Tage in kleineren Haeppchen
  nachziehen (siehe oben), z.B. `--backfill 15` dreimal an verschiedenen
  Tagen/mit Pausen dazwischen — ERST nachdem der Quota-Fix live bestaetigt ist.
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
| `ml_prediction_log`: beide Modelle taeglich loggen statt nur Tagessieger | User-Entscheidung: ermoeglicht echten Kopf-an-Kopf-Vergleich ueber Zeit fuer die Live-Modellwahl, nicht nur "welches Modell hat heute den synthetischen Split gewonnen" |
| Backfill nur teilweise (46/90 Tage), Rest morgen in Haeppchen statt heute erzwingen | Firestore-Spark-Quota gesprengt bei 90 Tagen auf einmal (~81k Docs) — 46 Tage liegen schon ueber der Live-Auswahl-Schwelle, kein Grund heute weiter zu droengen |
| `ml_accuracy_daily`-Aggregat-Collection statt Rohdaten-Voll-Scan | Read-Quota-Vorfall zeigte: komplette Collection bei jedem Lauf lesen skaliert strukturell nicht (~832% der Quota) — User-Wunsch war explizit "jeden DB-Call untersuchen und minimieren, ruhig Richtung Tages-Aggregat" |
| Quota-Fix HEUTE nur per Mock-Tests verifiziert, kein echter Firestore-Call mehr | Expliziter User-Wunsch nach dem Quota-Vorfall — Dashboard sollte heute noch produktiv nutzbar bleiben, echte Verifikation verschoben auf morgen |

## Current State

**Working**: Phase 1-4 komplett fertig (Code/Tests), live verifiziert
(Ausnahme: der Read-Quota-Fix selbst, siehe unten). Dashboard laeuft unter
https://tyrabite.github.io/KickbaseAgent/, Login+Live-Read funktionieren,
Firestore-Write laeuft automatisch alle 2h per GitHub Action.
Alle-Spieler-Tab und editierbarer Wunschkader-Tab sind fertig und im
Dashboard live, inkl. Nacharbeit (Buttons sichtbar, neue Filter). Neuer
"ML-Genauigkeit"-Tab mit Kopf-an-Kopf-Vergleich + Trend-Chart. Alle 59
Unit-Tests gruen.

**Offen**:
- **Quota-Fix noch NICHT live verifiziert** (nur Mock-Tests heute, siehe
  eigener Abschnitt) — allererster Schritt morgen.
- Backfill-Fortsetzung (44 fehlende Tage, siehe Phase-4-Abschnitt oben) —
  ERST nach der Quota-Fix-Verifikation.
- Rönnow-Eintrag in Firestore (`wunschkader/current`, `targets[0]`) zeigt
  noch faelschlich "Gebot fuehrend" — noch nicht auf "verloren an Fassii"
  aktualisiert.
- Torwart-Kaufentscheidung (Zentner?) noch nicht final getroffen.

**Uncommitted lokal (Stand Session-Ende)**: mehrere Commits aus dieser
Session (Dashboard-Nacharbeit + kompletter Phase-4-Plan) sind lokal
committed, **noch nicht gepusht** — User pusht das selbst (siehe Warnings).

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
| `docs/superpowers/plans/2026-07-28-ml-accuracy-tracking.md` | Der umgesetzte Phase-4-Plan (Tasks 1-8 fertig) — Referenz fuer die Backfill-Fortsetzung morgen |
| `docs/superpowers/plans/2026-07-28-ml-accuracy-quota-fix.md` | Der umgesetzte Read-Quota-Fix-Plan (Tasks 1-5 fertig) — NUR Mock-verifiziert, Live-Check ist morgens erster Schritt |
| `src/market_predictor.py::backfill_prediction_log` | `python -m src.market_predictor --backfill N` — morgen mit kleineren `N`-Werten (z.B. 15) mehrfach aufrufen, schreibt jetzt direkt Tages-Aggregate nach `ml_accuracy_daily` (nicht mehr Rohdaten) |
| `src/firestore_db.py::get_recent_prediction_log_entries`/`upsert_accuracy_daily`/`get_accuracy_daily` | Neue Quota-Fix-Funktionen — falls die Read-Zahl morgen immer noch zu hoch ist, hier zuerst nachschauen (`EVALUATION_LOOKBACK_DAYS` in `market_predictor.py` ggf. auf 2 senken) |

## Resume Instructions

1. **Zuerst**: pruefen ob der User offene lokale Commits (siehe `git log
   origin/main` vs. lokal) schon gepusht hat — Push ist weiterhin
   User-Sache, nicht automatisch machen.
2. **Quota-Fix live verifizieren** (ALLERERSTER echter Firestore-Call
   dieser Session-Fortsetzung): `FIRESTORE_ENABLED=1
   GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3
   -m src.dashboard_export` einmal laufen lassen, danach kurz
   `firestore_db.get_accuracy_daily(firestore_db.connect())` gegenchecken
   (sollte befuellt sein), und in der Firebase-Console (Firestore ->
   Nutzung/Quota-Tab) die tatsaechliche Read-Zahl fuer diesen einen Lauf
   pruefen — sollte im niedrigen Tausenderbereich liegen, nicht mehr im
   30-40k-Bereich (das waere noch der alte Bug).
3. **Backfill-Fortsetzung** (User-Wunsch, ERST nach Schritt 2): `--backfill`
   schreibt seit dem Quota-Fix nur noch 2 Dokumente PRO TAG (nicht mehr
   2×450) — `--backfill 90` in einem Rutsch sollte jetzt unproblematisch
   sein (~180 Writes total), trotzdem in ein paar kleineren Haeppchen
   bleiben ist unkritisch/sicherer. `FIRESTORE_ENABLED=1
   GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python3
   -m src.market_predictor --backfill 44` (oder direkt `90`, um die schon
   vorhandenen 46 Tage einfach zu ueberschreiben/aufzufuellen) sollte
   reichen. Danach `firestore_db.get_accuracy_daily(...)` gegenchecken
   (Anzahl distinkter Tage sollte nahe 90 sein).
4. Danach **Phase 5** (Mobile/UX, braucht User-Interview-Schritt zuerst).
5. Torwart-Entscheidung mit User abschliessen (Zentner bieten?), Rönnow-
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
- **Firestore Spark-Free-Tier hat Tageslimits (~50.000 Reads, ~20.000
  Writes/Tag)** — `backfill_prediction_log(days=N)` schreibt seit dem
  Quota-Fix nur noch ~2 Dokumente PRO TAG (Tages-Aggregate, nicht mehr
  Rohdaten pro Spieler), grosse `N`-Werte sind beim WRITE also
  unproblematisch geworden. Das eigentliche Risiko ist jetzt READS bei
  den taeglichen 2h-Laeufen (siehe Read-Quota-Fix-Abschnitt) — falls die
  Read-Zahl trotz Fix noch zu hoch ist, `EVALUATION_LOOKBACK_DAYS` in
  `market_predictor.py` (aktuell 3) senken. Quota erholt sich nach
  einer kurzen Abkuehlphase von selbst wieder (war bei uns eher Minuten
  als ein voller Tag) — kein Grund in Panik zu geraten, aber auch kein
  Freibrief fuer grosse Backfill-Werte.
