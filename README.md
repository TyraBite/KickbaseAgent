# KickbaseAgent

Taeglich automatisch laufender Decision-Support-Agent fuer Kickbase.

Sammelt Kader-, Liga-, Transfermarkt- und Punktedaten ueber die inoffizielle
Kickbase-API (inkl. eingebautem Verletzt-/Gesperrt-Status und Startelf-Rang
je Spieler), schaetzt die Budgets aller Liga-Manager aus dem Activity-Feed
und prognostiziert Marktwertaenderungen per taeglich neu trainiertem
RandomForest-Modell. Daraus entstehen zwei Ausgaben:

1. Ein fertiger Analyse-Prompt (Aufstellung, Kauf-/Verkaufsempfehlungen pro
   Spieler, Liga-Konkurrenzanalyse), per Discord-Webhook zugestellt und
   manuell ins Claude-WebUI eingefuegt (MVP-Phase: keine Anthropic-API-Kosten).
2. Ein lokales Dashboard (`docs/dashboard.html`) mit drei Ansichten:
   Transfermarkt, Eigenes Team, Ligaanalyse.

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
- `DISCORD_WEBHOOK_URL`

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

**Taeglicher Discord-Report** (Fetch, Budget-Schaetzung, ML-Prognose, Prompt, Discord-Versand;
laeuft automatisch per `.github/workflows/daily.yml`, 07:00 UTC):

```bash
python -m src.main
```

**Dashboard** (Transfermarkt/Eigenes Team/Ligaanalyse; laeuft automatisch per
`.github/workflows/dashboard.yml`, 21:15 UTC - kurz nach Kickbases 22:00-Uhr-Marktwert-
Update). Schreibt `docs/dashboard.html`, danach lokal im Browser oeffnen (`file://`):

```bash
python -m src.dashboard_export
```

**Fairwert/K-Punkt-Kalibrierung** (Referenzpreis je Position aus allen ~450 Liga-Spielern,
siehe `MDs/methodik.md`, Abschnitt "Fairwert und Signal"). Kein taeglicher Job - manuell
anstossen, wenn sich die Formkurve deutlich geaendert hat (z.B. nach ein paar Spieltagen).
Ergebnis landet in `data/valuation_k.json`, das Dashboard nutzt automatisch den letzten Stand:

```bash
python -m src.player_valuation
```
