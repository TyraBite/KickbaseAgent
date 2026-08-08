# Fuer den Raspberry-Pi-Cron-Betrieb der Dashboard-Exports (Light/Heavy),
# siehe README.md Abschnitt "Backend per Docker/Cron betreiben (Raspberry Pi)".
# Kein Frontend, keine News-Sentiment-Dependencies (requirements-news.txt) -
# die laufen ueber einen eigenen GitHub-Actions-Workflow, nicht hier.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# COPY . . statt einer Datei-Allowlist, damit dieses Image denselben Stand
# bekommt wie ein `actions/checkout@v4` in GitHub Actions - u.a. braucht
# player_valuation.load_calibration() das committete data/valuation_k.json,
# das eine reine `COPY src/` sonst stillschweigend weglaesst. .dockerignore
# schliesst Secrets/Ephemeres/Irrelevantes aus (siehe dort).
COPY . .

# Default = Light-Lauf (dashboard_export.py's eigener Default ohne
# DASHBOARD_MODE). Heavy-Laeufe ueberschreiben das per
# `docker run -e DASHBOARD_MODE=heavy ...`, gleiches Image fuer beide.
CMD ["python", "-m", "src.dashboard_export"]
