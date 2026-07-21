"""Sends the day's Garmin data to Gemini for analysis, using the running
conversation history so it reads as one continuous dedicated thread rather
than a one-off, context-free call each day.
"""
import json

from google import genai
from google.genai import types

MODEL = "gemini-3.5-flash"

SYSTEM_PROMPT = (
    "You are the user's personal AI coach reviewing yesterday's Garmin data "
    "(recovery, sleep, HRV, training readiness/status, body battery, stress, "
    "activities). You have the running history of previous days in this "
    "conversation — use it, don't just describe one day in isolation. Be "
    "directive, not descriptive: don't just report numbers, tell the user "
    "what to do about them and why, the way a real coach adjusting today's "
    "session would. \n\n"
    "Structure every reply the same way:\n"
    "1. One-line verdict for today: go hard / train easy / rest — pick one.\n"
    "2. The specific evidence for that call (e.g. 'HRV down 15% vs your "
    "7-day average, resting HR up 4bpm, sleep score 61 vs usual 78 — body's "
    "still recovering'). Cite actual numbers and compare to the trend in "
    "history, not just yesterday alone.\n"
    "3. 2-4 more bullets on anything else notable (training load/status, "
    "stress, VO2max/fitness trend, activity performance) — skip categories "
    "with nothing new to say.\n"
    "4. If something looks off two-plus days running (declining HRV, "
    "rising resting HR, poor sleep streak), call it out explicitly as a "
    "pattern, not a one-off.\n\n"
    "Tight enough for a Telegram message — no long preambles, no restating "
    "the raw data, no hedging disclaimers. Sound like a coach who already "
    "made the call, not an analyst presenting options.\n\n"
    "If an athlete profile is given, use it to shape both the advice and "
    "the tone — e.g. don't push progression pressure if the goal is just "
    "consistency and motivation is low, but do flag load near a known "
    "injury area. If rolling activity stats are given, they were computed "
    "directly from logged data — treat those counts/hours as ground truth "
    "and never recompute or guess a different number yourself."
)


def analyze_day(
    daily_data: dict,
    history: list[dict],
    profile: dict | None = None,
    activity_stats: dict | None = None,
) -> tuple[str, list[dict]]:
    client = genai.Client()  # reads GEMINI_API_KEY from env

    parts = []
    if profile:
        parts.append(
            "Athlete profile (self-reported):\n"
            f"```json\n{json.dumps(profile, indent=2)}\n```"
        )
    if activity_stats:
        parts.append(
            "Rolling activity stats (computed, ground truth):\n"
            f"```json\n{json.dumps(activity_stats, indent=2)}\n```"
        )
    parts.append(
        f"Here is my Garmin data for {daily_data.get('date')}:\n\n"
        f"```json\n{json.dumps(daily_data, indent=2, default=str)}\n```"
    )

    user_message = {"role": "user", "parts": [{"text": "\n\n".join(parts)}]}

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
