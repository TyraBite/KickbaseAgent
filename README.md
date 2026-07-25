# KickbaseAgent

Taeglich automatisch laufender Decision-Support-Agent fuer Kickbase.

Sammelt Kader-, Liga-, Transfermarkt- und Punktedaten ueber die inoffizielle
Kickbase-API, ergaenzt Verletzungs-/Sperrdaten von kicker.de und baut daraus
einen fertigen Analyse-Prompt (Aufstellung, Kauf-/Verkaufsempfehlungen pro
Spieler, Liga-Konkurrenzanalyse). Der Prompt wird per Discord-Webhook
zugestellt und manuell ins Claude-WebUI eingefuegt (MVP-Phase: keine
Anthropic-API-Kosten).

Details siehe Plan-Dokument (Projektverlauf).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Secrets lokal eintragen, .env nie committen
```

## Secrets (lokal in `.env`, in GitHub Actions als Repo-Secrets)

- `KICKBASE_EMAIL`
- `KICKBASE_PASSWORD`
- `DISCORD_WEBHOOK_URL`

## Ausfuehren

```bash
python -m src.main
```
