# KickbaseAgent

Taeglich automatisch laufender Decision-Support-Agent fuer Kickbase.

Sammelt Kader-, Liga-, Transfermarkt- und Punktedaten ueber die inoffizielle
Kickbase-API (inkl. eingebautem Verletzt-/Gesperrt-Status je Spieler) und
baut daraus einen fertigen Analyse-Prompt (Aufstellung, Kauf-/Verkaufs-
empfehlungen pro Spieler, Liga-Konkurrenzanalyse). Der Prompt wird per
Discord-Webhook zugestellt und manuell ins Claude-WebUI eingefuegt
(MVP-Phase: keine Anthropic-API-Kosten).

Details siehe Plan-Dokument (Projektverlauf).

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

## Ausfuehren

```bash
python -m src.main
```
