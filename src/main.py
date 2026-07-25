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


def run() -> None:
    load_dotenv()

    fetched_at = fetcher.run()
    prompt_text = build_prompt(fetched_at)

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL fehlt (lokal: .env, GitHub Actions: Secret)")

    send_prompt(webhook_url, prompt_text)
    print(f"Prompt fuer {fetched_at} an Discord gesendet.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Lauf fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
