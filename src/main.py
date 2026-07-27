"""Orchestriert den kompletten taeglichen Lauf: Fetch -> Prompt-Builder -> Discord.

MVP: keine Anthropic-API, der Prompt wird nur zugestellt und manuell ins
Claude-WebUI eingefuegt.
"""

import os
import sys

from dotenv import load_dotenv

from src import fetcher
from src.discord_notify import send_prompt
from src.prompt_builder import build_prompt


def _predict_market_values() -> dict | None:
    """ML-Marktwertprognose ist ein optionaler Zusatz-Schritt, der die
    Kern-Pipeline (Fetch -> Prompt -> Discord) NIEMALS blockieren darf -
    daher hier bewusst ein breites except (auch fuer z.B. fehlendes
    scikit-learn, ImportError beim Modul-Import eingeschlossen), statt wie
    sonst im Projekt Fehler spezifisch zu behandeln."""
    enabled = os.environ.get("MARKET_PREDICTOR_ENABLED", "true").lower() not in ("0", "false", "no")
    if not enabled:
        return None
    try:
        from src import market_predictor

        return market_predictor.predict_market_value_changes()
    except Exception as exc:  # noqa: BLE001 - optionaler Schritt, darf den Rest nie blockieren
        print(f"Warnung: ML-Marktwertprognose nicht verfuegbar, wird uebersprungen: {exc}", file=sys.stderr)
        return None


def run() -> None:
    load_dotenv()

    fetched_at = fetcher.run()
    predictions = _predict_market_values()
    prompt_text = build_prompt(fetched_at, predictions)

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL fehlt (lokal: .env, GitHub Actions: Secret)")

    send_prompt(webhook_url, prompt_text, fetched_at)
    print(f"Prompt fuer {fetched_at} an Discord gesendet.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Lauf fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
