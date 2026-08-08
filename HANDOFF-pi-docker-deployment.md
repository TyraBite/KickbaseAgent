# Handoff: KickbaseAgent Backend per Docker auf dem Raspberry Pi deployen

**Generated**: 2026-08-08
**Branch**: `main` (Repo-Änderungen liegen in PR #21, `worktree-pi-docker-cron-deployment` → `main`)
**Status**: Ready for Review / In Progress — Repo-seitige Vorbereitung fertig, Pi-seitiges Deployment noch nicht begonnen

## Goal

Die stündlichen/täglichen Kickbase-Dashboard-Exports (Light/Heavy) zusätzlich
per Docker-Container auf dem eigenen Raspberry Pi laufen lassen statt sie
ausschließlich GitHub Actions' `schedule`-Trigger zu überlassen. Grund: GH
Actions' Cron ist nur "best effort" (beobachtete Verzögerungen bis ~65 Min.,
gelegentliche mehrstündige Komplettausfälle, zuletzt 2026-08-06). Host-Cron
auf eigener Hardware feuert exakt zur gewählten Minute und ist von GH-Actions-
Ausfällen unabhängig. Alle Programme auf dem Pi laufen bereits in Docker —
dieses Deployment fügt sich in dieses bestehende Muster ein.

**Wichtig:** dieser Session-Agent hatte keinen Zugriff auf den Pi selbst und
konnte auch lokal kein Docker testen (nicht installiert in der Sandbox) — alle
Repo-Dateien sind sorgfältig gegen den echten Code verifiziert, aber der
eigentliche `docker build`/`docker run` auf ARM-Hardware ist komplett
unverifiziert. Das ist der wichtigste Teil, den du (ClaudeWeb) jetzt testest.

## Completed

- [x] `Dockerfile` (Repo-Root): `python:3.11-slim`, installiert `requirements.txt`,
      `COPY . .` (siehe Failed Approaches unten, warum nicht `COPY src/`).
- [x] `.dockerignore`: schließt Frontend/Docs/Tests/Secrets/`.git` aus, aber
      NICHT `data/valuation_k.json`/`data/ml_prediction_log.jsonl` (committet,
      werden zur Laufzeit gelesen) — nur `data/kickbase.db` ist ausgeschlossen
      (gitignored, pro Lauf frisch, exakt wie im bestehenden GH-Actions-Setup).
- [x] `README.md`, neuer Abschnitt "Backend per Docker/Cron betreiben
      (Raspberry Pi)" — Build-Befehl, Secrets-Platzierung, die zwei fertigen
      Crontab-Zeilen.
- [x] PR #21 erstellt, Auto-Merge gesetzt (Status beim Schreiben dieses Docs:
      offen, Checks laufen/liefen — vor dem nächsten Schritt per
      `gh pr view 21 --json state,mergedAt` selbst nochmal prüfen).

## Not Yet Done

- [ ] Repo auf den Pi klonen (oder `git pull`, falls schon geklont).
- [ ] `.env` + `firebase-service-account.json` auf dem Pi ablegen (Secrets,
      NICHT aus diesem Dokument — vom User erfragen, siehe Setup Required).
- [ ] `docker build -t kickbaseagent .` — erster echter Test dieses Dockerfiles
      überhaupt.
- [ ] Manueller Testlauf Light UND Heavy (siehe Resume Instructions Schritt 5-6)
      VOR dem Eintragen in Crontab.
- [ ] Crontab-Zeilen eintragen (`README.md`, Abschnitt "Backend per
      Docker/Cron betreiben").
- [ ] Mindestens einen echten stündlichen und einen echten täglichen Lauf
      unbeaufsichtigt abwarten und verifizieren (Firestore-Doc bzw. Live-
      Frontend aktualisiert sich zur erwarteten Zeit).
- [ ] Erst NACH dieser Verifikation: `schedule`-Trigger aus
      `.github/workflows/dashboard.yml` und `dashboard-marktwerte.yml`
      entfernen (`workflow_dispatch` bleibt als manueller Fallback), plus den
      Berlin-Zeit-Guard-Step in `dashboard-marktwerte.yml` entfernen (der
      existiert nur, um GH Actions' Cron-Verzögerung abzufedern — ohne
      Schedule-Trigger ist er totes Gewicht). Als eigener kleiner PR über den
      normalen Workflow (`gh pr create` + `gh pr merge --auto --squash`),
      NICHT per Direct-Push.

## Failed Approaches (Don't Repeat These)

- **`COPY src/` als Dockerfile-Allowlist** — zuerst so gebaut, dann als falsch
  erkannt: `player_valuation.py::CALIBRATION_PATH` liest zur Laufzeit
  `data/valuation_k.json`, `market_predictor.py::PREDICTION_LOG_PATH` liest/
  schreibt `data/ml_prediction_log.jsonl` — beide sind committet (nicht
  gitignored, nur `data/kickbase.db` ist es), eine reine `COPY src/` hätte sie
  stillschweigend weggelassen und Fairwert/Signal-Berechnung auf dem Pi
  gebrochen. Fix: `COPY . .` + `.dockerignore` als Deny-Liste, damit das Image
  denselben Stand bekommt wie `actions/checkout@v4` in GitHub Actions.
- **GHCR (GitHub Container Registry) fürs Image-Verteilen** — verworfen, siehe
  Key Decisions.
- **`ofelia`-Sidecar-Container fürs Scheduling** — verworfen, siehe Key
  Decisions.
- **In-Prozess-Scheduler (APScheduler) in einem dauerhaft laufenden
  Container** — verworfen, siehe Key Decisions.
- **GH-Actions-Schedule UND Pi-Cron dauerhaft parallel laufen lassen** — vom
  User nach Abwägung explizit verworfen (verdoppelt Kickbase-API-Calls und
  Firestore-Reads/Writes pro Lauf; Firestore-Freetier-Quota hat hier schon
  einmal, am 2026-08-04, einen kompletten Tagesausfall verursacht).

## Key Decisions

| Decision | Rationale |
|---|---|
| Host-Crontab (`CRON_TZ=Europe/Berlin`) + `docker run --rm` pro Lauf | Einfachste Option, kein neues Framework. Fixt beide urspruenglichen Probleme: exaktes Timing (kein "best effort" wie GH Actions) und `CRON_TZ` macht das fragile UTC-Offset-Nachrechnen bei der DST-Umstellung ueberfluessig. |
| Git-Clone + manuelles `git pull`/`docker build` auf dem Pi, keine Registry | Passt zum Hobby-Tempo, keine Registry-Auth auf dem Pi noetig, Pi braucht nur ausgehenden Zugriff. |
| Pi wird alleinige Quelle fuer geplante Laeufe; GH-Actions-Schedule wird ENTFERNT (erst nach Verifikation), `workflow_dispatch` bleibt | Kein doppelter API-/Firestore-Verbrauch im Normalbetrieb, GH Actions bleibt als manueller Notfall-Fallback erreichbar. |
| `COPY . .` statt Datei-Allowlist im Dockerfile | Muss 1:1 dem entsprechen, was `actions/checkout@v4` liefert - siehe Failed Approaches. |

## Current State

**Working**: Alle drei Repo-Dateien (`Dockerfile`, `.dockerignore`,
`README.md`-Abschnitt) sind geschrieben, gegen den echten Code verifiziert
(`data/`-Pfade, `requirements.txt`, `DASHBOARD_MODE`-Handling) und liegen in
PR #21. `python -m pytest tests/ -v` läuft weiterhin grün (382/382,
unverändert — dieser PR ändert keine Python-Logik).

**Nicht verifiziert / dein Auftrag**: `docker build`/`docker run` selbst,
insbesondere auf ARM (Raspberry Pi). Nie getestet, weil in der Autoren-Sandbox
kein Docker verfügbar war.

**GitHub Actions unverändert**: `dashboard.yml`/`dashboard-marktwerte.yml`
laufen weiterhin wie bisher als aktive geplante Quelle — nichts geht kaputt,
während du den Pi einrichtest.

## Files to Know

| File | Warum wichtig |
|---|---|
| `Dockerfile` | Image-Definition, Repo-Root |
| `.dockerignore` | Build-Context-Ausschlüsse — Vorsicht, nur `data/kickbase.db` ist ausgeschlossen, nicht ganz `data/` |
| `README.md` (Abschnitt "Backend per Docker/Cron betreiben (Raspberry Pi)") | Exakte Crontab-Zeilen + Build-Befehl, Quelle der Wahrheit für Schritt 7 unten |
| `.env.example` | Liste der benötigten Env-Var-Namen (Werte NICHT hier — vom User erfragen) |
| `src/dashboard_export.py` | Entry-Point (`python -m src.dashboard_export`), liest `DASHBOARD_MODE`/`FIRESTORE_ENABLED`/`GOOGLE_APPLICATION_CREDENTIALS` |
| `src/kickbase_client.py` | `BASE_URL` = `https://api.kickbase.com` — die einzige externe API außer Google/Docker/GitHub |
| `.github/workflows/dashboard.yml`, `dashboard-marktwerte.yml` | Aktuelle GH-Actions-Quelle, erst NACH Verifikation anfassen (siehe Not Yet Done) |

## Code Context

**Docker-Aufruf, Light (Default):**
```bash
docker run --rm --env-file .env \
  -v "$(pwd)/firebase-service-account.json:/app/firebase-service-account.json:ro" \
  -e FIRESTORE_ENABLED=1 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/firebase-service-account.json \
  kickbaseagent
```

**Docker-Aufruf, Heavy:** wie oben, zusätzlich `-e DASHBOARD_MODE=heavy`.

**Benötigte `.env`-Keys** (Werte sind Secrets, siehe Setup Required):
```
KICKBASE_EMAIL=
KICKBASE_PASSWORD=
DISCORD_WEBHOOK_URL=
KICKBASE_LEAGUE_ID=
KICKBASE_LEAGUE_START_BUDGET=
KICKBASE_LEAGUE_START_DATE=
```

**Erwartete Ausgabe eines erfolgreichen Laufs** (aus `src/fetcher.py`, letzte
Zeile eines Laufs, Zahlen variieren):
```
Snapshot <timestamp>: N eigene Spieler, M Marktangebote, K Liga-Manager, J geschaetzte Budgets
```

## Verbindungen, die gebraucht werden (nur ausgehend, KEIN offener Port)

Das war eine offene Frage in der Ursprungs-Session — wichtig, dass das klar
ist, bevor du anfängst:

- **GitHub** (`git clone`/`git pull`) — ausgehend, HTTPS.
- **Docker Hub** (`python:3.11-slim`-Base-Image) und **PyPI**
  (`pip install`-Pakete während `docker build`) — ausgehend, HTTPS.
- **Kickbase-API**, `https://api.kickbase.com` (`src/kickbase_client.py`,
  `BASE_URL`) — ausgehend, Login + alle Datenabrufe.
- **Google Cloud Firestore** (`google-cloud-firestore`-Client, Standard-
  `*.googleapis.com`-Endpunkte, kein fixer Host) — nur wenn
  `FIRESTORE_ENABLED=1` gesetzt ist (immer der Fall in den Crontab-Zeilen
  unten).
- **Kein eingehender Port nötig.** Das ist ein rein ausgehender, geplanter
  Batch-Job, kein Server. Die "muss ich einen Port exposen"-Frage aus der
  Ursprungs-Session ist damit erledigt — für BEIDE ursprünglich erwogenen
  Deployment-Varianten (Git-Pull wie jetzt gebaut, oder GHCR) wäre kein Port
  nötig gewesen.

## Resume Instructions

1. Prüfen, ob PR #21 gemergt ist: `gh pr view 21 --json state,mergedAt`.
   Falls noch offen: warten oder selbst mergen, bevor du vom Pi aus klonst.
2. Auf dem Pi: `git clone <repo-url> ~/kickbaseagent && cd ~/kickbaseagent`
   (oder `git pull`, falls schon vorhanden).
3. `.env` und `firebase-service-account.json` in `~/kickbaseagent/` ablegen —
   die echten Werte beim User erfragen, niemals selbst raten/erfinden.
4. `docker build -t kickbaseagent .`
   - Erwartet: Build läuft durch, letzter Layer ist der `CMD`-Eintrag.
   - Falls `pip install` fehlschlägt: `requirements.txt`-Versionen gegen die
     Pi-Architektur (voraussichtlich ARM64) prüfen — dieser Schritt ist
     komplett unverifiziert, siehe Warnings.
5. Manueller Testlauf VOR jedem Crontab-Eintrag (Light):
   ```bash
   docker run --rm --env-file .env -v "$(pwd)/firebase-service-account.json:/app/firebase-service-account.json:ro" -e FIRESTORE_ENABLED=1 -e GOOGLE_APPLICATION_CREDENTIALS=/app/firebase-service-account.json kickbaseagent
   ```
   - Erwartet: Ausgabe wie oben unter "Code Context", Exit-Code 0.
   - Login-Fehler → `KICKBASE_EMAIL`/`KICKBASE_PASSWORD` in `.env` prüfen.
   - Firestore-Fehler → `firebase-service-account.json` gültiges JSON? Mount-
     Pfad passt zu `GOOGLE_APPLICATION_CREDENTIALS`?
6. Denselben Testlauf mit `-e DASHBOARD_MODE=heavy` wiederholen (dauert
   länger, mehr Kickbase-Calls).
7. Erst wenn beide manuellen Läufe erfolgreich waren: die zwei Crontab-Zeilen
   aus `README.md` eintragen (`crontab -e`, `CRON_TZ=Europe/Berlin` als erste
   Zeile nicht vergessen).
8. Mindestens einen echten stündlichen und einen echten täglichen Zyklus
   unbeaufsichtigt abwarten, dann `dashboard_snapshot/latest` in Firestore
   (oder das Live-Frontend) auf Aktualisierung zur erwarteten Zeit prüfen.
9. Erfolg zurückmelden (an den User oder die Ursprungs-Session) — das ist der
   Trigger für den letzten Schritt aus "Not Yet Done" (GH-Actions-Schedule
   entfernen), den DIESE Session bewusst nicht selbst gemacht hat.

## Setup Required

- Docker auf dem Pi (laut User bereits vorhanden — "Alle Programme auf dem Pi
  laufen bereits in einem Docker Container").
- `git` auf dem Pi.
- Echte Secret-Werte (Kickbase-Login, Firebase-Service-Account-Key) — vom User
  erfragen, stehen nirgends in diesem Dokument oder im Git-Repo.

## Edge Cases & Error Handling

- Pi offline/Neustart genau zur Cron-Minute → dieser Lauf fällt einfach aus,
  kein Nachhol-Mechanismus (identisch zum heutigen GH-Actions-Verhalten,
  keine Regression).
- `docker run --rm` heißt: jeder Lauf ist ein frischer, zustandsloser
  Container — die lokale SQLite (`data/kickbase.db`) wird bei jedem Lauf neu
  erzeugt und persistiert nie zwischen Läufen. Das ist gewollt, identisch zum
  aktuellen GH-Actions-Verhalten (frischer Checkout pro Lauf), kein Bug.

## Warnings

- GH-Actions-`schedule`-Trigger NICHT entfernen, bevor die Pi-Läufe
  tatsächlich verifiziert sind — sonst gibt es eine Lücke ganz ohne geplante
  Läufe.
- NICHT GH-Actions-Schedule und Pi-Cron dauerhaft parallel laufen lassen "zur
  Sicherheit" — der User hat das nach Abwägung der Kosten (siehe Failed
  Approaches) bewusst abgelehnt.
- `.env` und `firebase-service-account.json` niemals ins Git-Repo auf dem Pi
  committen — beide sind in diesem Repo gitignored und müssen host-only
  bleiben, nur per `--env-file`/Volume-Mount in den Container gereicht.
- Diese ganze Pi-Idee stammt aus Firestore-Feedback-Item `306066b2`. Im
  selben Feedback-Thread gab es eine deutlich größere Idee ("perspektivisch
  das ganze Konstrukt auf dem Pi hosten") — die hat der User explizit auf
  später verschoben, nicht Teil dieses Handoffs.
