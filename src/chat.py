"""Handles an inbound Telegram message: loads shared context, asks Gemini,
replies, and persists the turn to the same conversation history the daily
report uses — so chat and daily reports read as one continuous thread.

ponytail: answers from stored data only (profile + precomputed stats +
history), no live Garmin pull per message. The activity stats are refreshed
by the daily job; chat just reads the last computed snapshot. Add on-demand
fetch later if you want "pull my data right now" — it needs a cached garth
token to avoid re-login cost/MFA.
"""
from athlete_profile import load_profile
from daily_log import load_activity_stats
from gemini_analyze import chat_reply
from history import load_history, save_history
from telegram_notify import send_message


def handle_message(text: str) -> None:
    history = load_history()
    profile = load_profile()
    activity_stats = load_activity_stats()

    reply_text, updated_history = chat_reply(text, history, profile, activity_stats)

    send_message(reply_text)
    save_history(updated_history)
