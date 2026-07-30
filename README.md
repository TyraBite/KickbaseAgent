# KickbaseAgent

Taeglich automatisch laufender Decision-Support-Agent fuer Kickbase.

Sammelt Kader-, Liga-, Transfermarkt- und Punktedaten ueber die inoffizielle
Kickbase-API (inkl. eingebautem Verletzt-/Gesperrt-Status und Startelf-Rang
je Spieler), schaetzt die Budgets aller Liga-Manager aus dem Activity-Feed
und prognostiziert Marktwertaenderungen per taeglich neu trainiertem
RandomForest-Modell. Daraus entsteht ein live gehostetes Dashboard
(React/Vite/Tailwind-Frontend in `frontend/`, per GitHub Pages + Firebase
Auth/Firestore) mit sieben Ansichten: Eigenes Team, Spekulation,
Wunschkader, Transfermarkt, Ligaanalyse, Alle Spieler, ML-Genauigkeit.

Details siehe Plan-Dokument (Projektverlauf). Die manuelle Recherche-
Methodik (Startelf-Einschaetzungen, Verletzungslage, Vereinskontext) liegt
in `MDs/*.md` - ein separater, von Hand gepflegter Wissensspeicher, kein
Code-Feature.

## Setup

**macOS/Linux (bash):**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Secrets lokal eintragen, .env nie committen
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
# Falls Skript-Ausfuehrung blockiert ist:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install -r requirements.txt
copy .env.example .env  # Secrets lokal eintragen, .env nie committen
```

## Secrets (lokal in `.env`, in GitHub Actions als Repo-Secrets)

- `KICKBASE_EMAIL`
- `KICKBASE_PASSWORD`
- `FIREBASE_SERVICE_ACCOUNT` (JSON-Inhalt des Firebase-Service-Account-Keys, fuer den Firestore-Schreibpfad)

## Optionale Konfiguration

- `KICKBASE_LEAGUE_ID`: Falls der Account in mehreren Ligen ist, sonst wird die erste genommen.
- `KICKBASE_LEAGUE_START_BUDGET`: Startbudget der Liga fuer die Manager-Budget-Schaetzung
  (Default 50.000.000, Kickbase-Plattform-Standard).
- `KICKBASE_LEAGUE_START_DATE`: ISO-Datum (z.B. `2026-08-01`). Setzt einen Cutoff fuer die
  Budget-Schaetzung - Trades vor diesem Datum werden ignoriert. Standardmaessig leer (kein
  Cutoff, ganzer verfuegbarer Activity-Feed wird verwendet). Bei Saisonwechsel mit
  Budget-Reset auf das Reset-Datum setzen, sonst verzerren Trades der Vorsaison die Schaetzung.
- `MARKET_PREDICTOR_ENABLED`: Kill-Switch fuer die ML-Marktwertprognose (Default `true`).
  Auf `false` setzen, falls der Schritt mal Probleme macht - der Rest der Pipeline laeuft
  dann unveraendert weiter.
- `MARKET_PREDICTOR_MAX_WORKERS` / `PLAYER_VALUATION_MAX_WORKERS`: Nebenlaeufigkeit beim
  Abruf der ligaweiten Spielerhistorie (Default je 8).

## Ausfuehren

**Dashboard-Export** (Light, laeuft automatisch per `.github/workflows/dashboard.yml`,
stuendlich). Berechnet den Snapshot und schreibt ihn nach Firestore
(`dashboard_snapshot/latest`), von wo das React-Frontend (`frontend/`) ihn live liest:

```bash
FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python -m src.dashboard_export
```

**Dashboard-Export Marktwerte** (Heavy, laeuft automatisch per
`.github/workflows/dashboard-marktwerte.yml`, 1x/Tag um 22:05 Berlin-Zeit).
Teure Kickbase-Calls (Marktwert-Historie, ML-Prognosen) - ausgelagert aus dem
stuendlichen Light-Lauf:

```bash
DASHBOARD_MODE=heavy FIRESTORE_ENABLED=1 GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json python -m src.dashboard_export
```

**Frontend** (`frontend/`, React/Vite/Tailwind, deployt per
`.github/workflows/frontend-pilot.yml` auf GitHub Pages):

```bash
cd frontend && npm install && npm run dev
```

**Fairwert/K-Punkt-Kalibrierung** (Referenzpreis je Position aus allen ~450 Liga-Spielern,
siehe `MDs/methodik.md`, Abschnitt "Fairwert und Signal"). Kein taeglicher Job - manuell
anstossen, wenn sich die Formkurve deutlich geaendert hat (z.B. nach ein paar Spieltagen).
Ergebnis landet in `data/valuation_k.json`, das Dashboard nutzt automatisch den letzten Stand:

```bash
python -m src.player_valuation
```
