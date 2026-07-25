"""Schritt 3 (MVP): den fertigen Prompt per Discord-Webhook zustellen.

Discord begrenzt den Nachrichteninhalt auf 2000 Zeichen - laengere Prompts
werden in mehrere Nachrichten aufgeteilt (an Zeilenumbruechen, nicht mitten
im Wort).
"""

import os
import time

import requests

DISCORD_MESSAGE_LIMIT = 2000
_CHUNK_TARGET = 1900  # Puffer fuer Teil-Praefix ("(2/3)\n")
_MAX_RETRIES = 5


def _chunk_text(text: str, target_size: int = _CHUNK_TARGET) -> list[str]:
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        # +1 fuer den Zeilenumbruch, der beim Zusammenfuegen wieder dazukommt
        added = len(line) + 1
        if current and current_len + added > target_size:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += added

    if current:
        chunks.append("\n".join(current))

    return chunks or [""]


def _post_with_retry(webhook_url: str, content: str) -> None:
    """Discord limitiert Requests pro Webhook (~5/2s). Bei vielen Chunks
    hintereinander (z.B. grosser Transfermarkt) kommt schnell ein 429 -
    dessen 'retry_after' respektieren statt sofort aufzugeben."""
    for attempt in range(_MAX_RETRIES):
        response = requests.post(webhook_url, json={"content": content}, timeout=15)
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


def send_prompt(webhook_url: str, prompt_text: str) -> None:
    chunks = _chunk_text(prompt_text)
    total = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        content = chunk if total == 1 else f"({index}/{total})\n{chunk}"
        if len(content) > DISCORD_MESSAGE_LIMIT:
            # Sicherheitsnetz, falls eine einzelne Zeile laenger als das Limit ist
            content = content[: DISCORD_MESSAGE_LIMIT - 3] + "..."

        _post_with_retry(webhook_url, content)
        # kleiner Sicherheitsabstand zwischen Nachrichten, um das Rate-Limit
        # bei vielen Chunks gar nicht erst zu reissen
        if index < total:
            time.sleep(0.4)


if __name__ == "__main__":
    from dotenv import load_dotenv

    from src.prompt_builder import build_prompt

    load_dotenv()
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise RuntimeError("DISCORD_WEBHOOK_URL fehlt (lokal: .env, GitHub Actions: Secret)")

    send_prompt(url, build_prompt())
    print("Prompt an Discord gesendet.")
