# KickbaseAgent

Decision-Support-Tool für Kickbase. Sammelt Kader-, Liga-, Transfermarkt- und
Punktedaten über die inoffizielle Kickbase-API (inkl. Verletzt-/Gesperrt-Status
und Startelf-Rang je Spieler), schätzt die Budgets aller Liga-Manager aus dem
Activity-Feed und prognostiziert Marktwertänderungen (1-Tages- und
3-Tages-Horizont) per täglich neu trainiertem ML-Modell. Ein
React/Vite/Tailwind-Frontend zeigt daraus Fairwert/Signal je Spieler,
Transfermarkt-Gebotsempfehlungen, Ligaanalyse und Wunschkader-Planung.

Die manuelle Recherche-Methodik (Startelf-Einschätzungen, Verletzungslage,
Vereinskontext) liegt in `MDs/*.md` — ein separater, von Hand gepflegter
Wissensspeicher, kein Code-Feature.

## Architektur

**Backend (`src/`, Python)**

- `kickbase_client.py` — Wrapper um die inoffizielle Kickbase-API (Login,
  Kader/Liga/Transfermarkt-Abruf, Status-Codes).
- `fetcher.py` — ein kompletter Abruf-Lauf, schreibt einen Tages-Snapshot in
  eine lokale SQLite-Datenbank (`db.py`, `data/kickbase.db`).
- `manager_budgets.py` — schätzt die verfügbaren Budgets aller Liga-Manager
  aus dem Activity-Feed (Trades, Boni, Überziehungsregel).
- `player_valuation.py` — Fairwert/K-Punkt-Kalibrierung: Referenzpreis je
  Position aus allen Liga-Spielern.
- `market_predictor.py` — trainiert täglich ein ML-Modell (RandomForest/
  HistGradientBoosting/LightGBM, Walk-Forward-Validierung) und prognostiziert
  Marktwertänderungen für 1 und 3 Tage.
- `bid_premium.py` — trackt Aufschläge bei abgeschlossenen Systemangeboten,
  liefert Gebotsempfehlungen mit Perzentil-Verteilung.
- `dashboard_export.py` — Haupt-Einstiegspunkt: ruft die obigen Module auf
  und baut daraus einen einzigen Snapshot (ein dict) für alle Frontend-Ansichten.
- `prompt_builder.py` / `discord_notify.py` / `main.py` — älterer, paralleler
  Pfad: baut aus den Rohdaten einen Text-Prompt und verschickt ihn per
  Discord-Webhook (fürs manuelle Einfügen in eine Claude-Konversation, statt
  des Dashboards).

**Datenhaltung**

- Lokale SQLite (`data/kickbase.db`) für historische Tages-Snapshots.
- Firestore als zentraler Snapshot-Store: `dashboard_export.py` schreibt dort
  ein Dokument (`dashboard_snapshot/latest`), das Frontend liest es live.
  Ein zweites Dokument (`wunschkader/current`) hält die vom Nutzer editierbare
  Wunschkader-Zielliste, unabhängig vom Snapshot.

**Frontend (`frontend/`, React + Vite + TypeScript + Tailwind)**

Liest den Snapshot aus Firestore und leitet daraus client-seitig alles
Weitere ab (Fairwert/Signal, Sortierung, Filter — siehe
`frontend/src/lib/derive.ts`); das Backend liefert nur Rohdaten. Login läuft
über Firebase Auth. Acht Tabs: Eigenes Team, Spekulation, Wunschkader,
Transfermarkt, Ligaanalyse, Alle Spieler, Modell-Tracking, Bugs & Ideen.

**Tests (`tests/`)**

Python-`unittest`-Suite für die Backend-Logik (Client, Fetcher, Budgets,
ML-Prediction, Bid-Premium, Dashboard-Export-Contract).

## Lokal einrichten

**Backend — macOS/Linux (bash):**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Secrets lokal eintragen, .env nie committen
```

**Backend — Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
# Falls Skript-Ausfuehrung blockiert ist:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r requirements.txt
copy .env.example .env  # Secrets lokal eintragen, .env nie committen
```

`src/news_sentiment.py` (News/Sentiment-Ingestion) braucht zusaetzlich
`pip install -r requirements-news.txt` (germansentiment/transformers/torch,
bewusst nicht im geteilten `requirements.txt`, siehe Kommentar in `requirements-news.txt`).

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Für den Firestore-Lesepfad braucht das Frontend ein eigenes Firebase-Projekt
(Auth + Firestore) mit passender Konfiguration in `frontend/src/firebase.ts`
und eingehaltenen `firestore.rules`.

## Secrets (lokal in `.env`)

- `KICKBASE_EMAIL` / `KICKBASE_PASSWORD`
- `DISCORD_WEBHOOK_URL` — nur für den `main.py`-Pfad (Discord-Prompt-Versand).
- `FIREBASE_SERVICE_ACCOUNT` bzw. `GOOGLE_APPLICATION_CREDENTIALS` — Pfad zum
  JSON-Key eines eigenen Firebase-Service-Accounts, nur nötig, wenn
  `FIRESTORE_ENABLED=1` gesetzt wird.

## Optionale Konfiguration

- `KICKBASE_LEAGUE_ID`: Falls der Account in mehreren Ligen ist, sonst wird die erste genommen.
- `KICKBASE_LEAGUE_START_BUDGET`: Startbudget der Liga für die Manager-Budget-Schätzung
  (Default 50.000.000, Kickbase-Plattform-Standard).
- `KICKBASE_LEAGUE_START_DATE`: ISO-Datum (z.B. `2026-08-01`). Setzt einen Cutoff für die
  Budget-Schätzung — Trades vor diesem Datum werden ignoriert. Standardmäßig leer (kein
  Cutoff, ganzer verfügbarer Activity-Feed wird verwendet). Bei Saisonwechsel mit
  Budget-Reset auf das Reset-Datum setzen, sonst verzerren Trades der Vorsaison die Schätzung.
- `MARKET_PREDICTOR_ENABLED`: Kill-Switch für die ML-Marktwertprognose (Default `true`).
  Auf `false` setzen, falls der Schritt mal Probleme macht — der Rest der Pipeline läuft
  dann unverändert weiter.
- `MARKET_PREDICTOR_MAX_WORKERS` / `PLAYER_VALUATION_MAX_WORKERS`: Nebenläufigkeit beim
  Abruf der ligaweiten Spielerhistorie (Default je 8).

## Backend ausführen

**Dashboard-Snapshot (Light)** — Kern-Pipeline, Kader/Liga/Transfermarkt-Abruf
+ Fairwert/Signal, keine teuren Marktwert-Historie-Calls:

```bash
python -m src.dashboard_export
```

**Dashboard-Snapshot (Heavy)** — inkl. Marktwert-Historie und ML-Prognosen
(teuer, mehr Kickbase-Calls):

```bash
DASHBOARD_MODE=heavy python -m src.dashboard_export
```

Mit `FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./pfad-zum-key.json`
davor schreibt der Lauf den Snapshot zusätzlich nach Firestore.

**Fairwert/K-Punkt-Kalibrierung** (siehe `MDs/methodik.md`, Abschnitt
"Fairwert und Signal"). Kein täglicher Schritt — manuell anstoßen, wenn sich
die Formkurve deutlich geändert hat (z.B. nach ein paar Spieltagen). Ergebnis
landet in `data/valuation_k.json`:

```bash
python -m src.player_valuation
```

**Discord-Prompt-Pfad** (älterer, paralleler Einstiegspunkt, siehe oben):

```bash
python -m src.main
```

## Tests

```bash
python -m unittest discover -s tests
```
