"""Sends the analysis to a Telegram chat via a bot."""
import os

import requests

TELEGRAM_API = "https://api.telegram.org"


def send_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # Telegram messages cap at 4096 chars; chunk just in case.
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]

    for chunk in chunks:
        resp = requests.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk},
            timeout=15,
        )
        resp.raise_for_status()
