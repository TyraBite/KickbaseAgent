"""Schritt 3 (MVP): den fertigen Prompt per Discord-Webhook zustellen.

Der Prompt geht als einzelne Text-Datei-Anlage raus statt als viele
2000-Zeichen-Text-Chunks (Discords Nachrichten-Limit) - auf dem Handy
deutlich einfacher zu oeffnen und komplett zu kopieren als 10+ einzelne
Nachrichten. Discord-Webhooks erlauben bis zu 25 MB pro Anhang, der Prompt
liegt bei ein paar zehn KB - passt locker.
"""

import json
import os
import time

import requests

_MAX_RETRIES = 5


def _post_with_retry(webhook_url: str, **kwargs) -> None:
    """Discord limitiert Requests pro Webhook - 429 mit 'retry_after'
    respektieren statt sofort aufzugeben."""
    for _ in range(_MAX_RETRIES):
        response = requests.post(webhook_url, timeout=15, **kwargs)
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1)
            time.sleep(float(retry_after) + 0.1)
            continue
        if response.status_code >= 300:
            raise RuntimeError(
                f"Discord-Webhook-Fehler ({response.status_code}): {response.text}"
            )
        return
    raise RuntimeError(f"Discord-Webhook: nach {_MAX_RETRIES} Versuchen weiterhin rate-limited")


def send_prompt(webhook_url: str, prompt_text: str, fetched_at: str | None = None) -> None:
    filename = f"kickbase-prompt-{fetched_at}.txt" if fetched_at else "kickbase-prompt.txt"
    message = "Kickbase-Prompt - Datei antippen, Text markieren, kopieren, ins Claude-WebUI einfuegen."

    files = {"file": (filename, prompt_text.encode("utf-8"), "text/plain")}
    payload = {"payload_json": json.dumps({"content": message})}
    _post_with_retry(webhook_url, data=payload, files=files)


if __name__ == "__main__":
    from dotenv import load_dotenv

    from src.prompt_builder import build_prompt

    load_dotenv()
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise RuntimeError("DISCORD_WEBHOOK_URL fehlt (lokal: .env, GitHub Actions: Secret)")

    send_prompt(url, build_prompt())
    print("Prompt an Discord gesendet.")
