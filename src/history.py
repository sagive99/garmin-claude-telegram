"""Maintains a rolling conversation history file so each day's Gemini call
sees prior context, giving the effect of one ongoing dedicated chat instead
of a fresh, memoryless call every time.
"""
import storage

HISTORY_NAME = "conversation_history.json"

# Keep the file bounded — without this it grows forever and eventually
# blows the model's context window.
MAX_TURNS = 40  # ~20 exchanges (user+assistant pairs)


def load_history() -> list[dict]:
    return storage.read_json(HISTORY_NAME, [])


def save_history(messages: list[dict]) -> None:
    storage.write_json(HISTORY_NAME, messages[-MAX_TURNS:])
