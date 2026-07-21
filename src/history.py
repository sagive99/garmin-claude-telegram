"""Maintains a rolling conversation history file so each day's Claude call
sees prior context, giving the effect of one ongoing dedicated chat instead
of a fresh, memoryless call every time.
"""
import json
import os

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "conversation_history.json")

# Keep the file bounded — without this it grows forever and eventually
# blows the model's context window.
MAX_TURNS = 40  # ~20 exchanges (user+assistant pairs)


def load_history() -> list[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(messages: list[dict]) -> None:
    trimmed = messages[-MAX_TURNS:]
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, indent=2, ensure_ascii=False)
