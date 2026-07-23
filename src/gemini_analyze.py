"""Sends the day's Garmin data to Gemini for analysis, using the running
conversation history so it reads as one continuous dedicated thread rather
than a one-off, context-free call each day.
"""
import json
import time

from google import genai
from google.genai import types
from google.genai.errors import ServerError

MODEL = "gemini-3.6-flash"

# Only retries on 5xx (transient overload) — a 429/quota error is a
# ClientError, not a ServerError, so it's never retried here: retrying
# a real quota error just burns more of the daily cap for nothing.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2


def _generate_with_retry(client, **kwargs):
    for attempt in range(MAX_ATTEMPTS):
        try:
            return client.models.generate_content(**kwargs)
        except ServerError:
            if attempt == MAX_ATTEMPTS - 1:
                raise
            time.sleep(RETRY_BACKOFF_SECONDS * (2 ** attempt))


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

CHAT_SYSTEM_PROMPT = (
    "You are the user's personal AI coach, replying to a message they sent "
    "you in Telegram. You have the running history of your past daily reports "
    "and conversations, their self-reported profile, and computed rolling "
    "activity stats — use all of it. Answer the actual question directly and "
    "conversationally; this is a chat reply, not a daily report, so don't "
    "force the go-hard/easy/rest report structure unless they're asking what "
    "to do today. Ground answers in their real numbers and history, treat any "
    "computed activity stats as ground truth (never recompute), and shape "
    "advice by their goals and injuries. If you genuinely don't have the data "
    "to answer (e.g. they ask about a metric not in the log), say so plainly. "
    "Keep it tight for Telegram — no long preambles or disclaimers."
)


def _context_parts(profile: dict | None, activity_stats: dict | None) -> list[str]:
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
    return parts


def analyze_day(
    daily_data: dict,
    history: list[dict],
    profile: dict | None = None,
    activity_stats: dict | None = None,
) -> tuple[str, list[dict]]:
    client = genai.Client()  # reads GEMINI_API_KEY from env

    parts = _context_parts(profile, activity_stats)
    parts.append(
        f"Here is my Garmin data for {daily_data.get('date')}:\n\n"
        f"```json\n{json.dumps(daily_data, indent=2, default=str)}\n```"
    )

    sent_message = {"role": "user", "parts": [{"text": "\n\n".join(parts)}]}

    response = _generate_with_retry(
        client,
        model=MODEL,
        contents=history + [sent_message],
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )

    reply_text = response.text

    # Persist only a marker for the day's data, never the raw payload — a full
    # day of Garmin intraday arrays is hundreds of KB, and keeping it in the
    # rolling history balloons every later call past the model's token limits.
    # The trends live in daily_log (computed) and in the reports themselves.
    # Gemini's chat role is "model", not "assistant".
    compact_user = {
        "role": "user",
        "parts": [{"text": f"[Garmin data for {daily_data.get('date')} — raw payload omitted from history]"}],
    }
    updated_history = history + [compact_user, {"role": "model", "parts": [{"text": reply_text}]}]
    return reply_text, updated_history


def chat_reply(
    user_text: str,
    history: list[dict],
    profile: dict | None = None,
    activity_stats: dict | None = None,
) -> tuple[str, list[dict]]:
    """Free-form reply to a Telegram message. Same history-threading as the
    daily report, but answers the user's actual question rather than emitting
    the fixed daily structure. Profile + computed stats are sent as context
    every turn (so they can't age out of the history window) but only the raw
    user text is persisted, so the stored history doesn't balloon."""
    client = genai.Client()

    sent_parts = _context_parts(profile, activity_stats) + [user_text]
    sent_message = {"role": "user", "parts": [{"text": "\n\n".join(sent_parts)}]}

    response = _generate_with_retry(
        client,
        model=MODEL,
        contents=history + [sent_message],
        config=types.GenerateContentConfig(system_instruction=CHAT_SYSTEM_PROMPT),
    )

    reply_text = response.text
    updated_history = history + [
        {"role": "user", "parts": [{"text": user_text}]},
        {"role": "model", "parts": [{"text": reply_text}]},
    ]
    return reply_text, updated_history
