"""Sends the day's Garmin data to Claude for analysis, using the running
conversation history so it reads as one continuous dedicated thread rather
than a one-off, context-free call each day.
"""
import json
import os

import anthropic

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = (
    "You are a personal training/health analyst reviewing the user's daily "
    "Garmin data. You have access to the running history of previous days "
    "in this conversation, so refer back to trends when relevant (e.g. "
    "'your resting HR is down 3bpm from last week'). Keep each report tight "
    "enough to read comfortably in a Telegram message: a short headline "
    "takeaway, then 3-6 bullet points on sleep, activity, HR/body battery, "
    "and one concrete suggestion for today. No long preambles."
)


def analyze_day(daily_data: dict, history: list[dict]) -> tuple[str, list[dict]]:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    user_message = {
        "role": "user",
        "content": (
            f"Here is my Garmin data for {daily_data.get('date')}:\n\n"
            f"```json\n{json.dumps(daily_data, indent=2, default=str)}\n```"
        ),
    }

    messages = history + [user_message]

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    reply_text = "".join(block.text for block in response.content if block.type == "text")

    updated_history = messages + [{"role": "assistant", "content": reply_text}]
    return reply_text, updated_history
