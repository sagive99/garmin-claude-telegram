"""Sends the day's Garmin data to Gemini for analysis, using the running
conversation history so it reads as one continuous dedicated thread rather
than a one-off, context-free call each day.
"""
import json

from google import genai
from google.genai import types

MODEL = "gemini-3.5-flash"

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
    client = genai.Client()  # reads GEMINI_API_KEY from env

    user_message = {
        "role": "user",
        "parts": [{
            "text": (
                f"Here is my Garmin data for {daily_data.get('date')}:\n\n"
                f"```json\n{json.dumps(daily_data, indent=2, default=str)}\n```"
            )
        }],
    }

    contents = history + [user_message]

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )

    reply_text = response.text

    # Gemini's chat role is "model", not "assistant".
    updated_history = contents + [{"role": "model", "parts": [{"text": reply_text}]}]
    return reply_text, updated_history
