"""Schritt 3 (MVP): den fertigen Prompt per Discord-Webhook zustellen.

Discord begrenzt den Nachrichteninhalt auf 2000 Zeichen - laengere Prompts
werden in mehrere Nachrichten aufgeteilt (an Zeilenumbruechen, nicht mitten
im Wort).
"""

import os

import requests

DISCORD_MESSAGE_LIMIT = 2000
_CHUNK_TARGET = 1900  # Puffer fuer Teil-Praefix ("(2/3)\n")


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


def send_prompt(webhook_url: str, prompt_text: str) -> None:
    chunks = _chunk_text(prompt_text)
    total = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        content = chunk if total == 1 else f"({index}/{total})\n{chunk}"
        if len(content) > DISCORD_MESSAGE_LIMIT:
            # Sicherheitsnetz, falls eine einzelne Zeile laenger als das Limit ist
            content = content[: DISCORD_MESSAGE_LIMIT - 3] + "..."

        response = requests.post(webhook_url, json={"content": content}, timeout=15)
        if response.status_code >= 300:
            raise RuntimeError(
                f"Discord-Webhook-Fehler ({response.status_code}): {response.text}"
            )


if __name__ == "__main__":
    from dotenv import load_dotenv

    from src.prompt_builder import build_prompt

    load_dotenv()
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise RuntimeError("DISCORD_WEBHOOK_URL fehlt (lokal: .env, GitHub Actions: Secret)")

    send_prompt(url, build_prompt())
    print("Prompt an Discord gesendet.")
