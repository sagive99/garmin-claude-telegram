"""Keeps a rolling log of each day's Garmin summary, separate from the chat
history, so multi-week stats (session counts, hours by activity type) can be
computed exactly in Python instead of asking the LLM to count across many
turns of raw JSON — LLMs are unreliable at that kind of arithmetic.

Only the aggregate/summary fields are kept per day (not the intraday arrays
like raw heart rate or step-by-step traces) so the log stays small even at a
year of history.
"""
import datetime
import json
import os

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "daily_log.json")
MAX_DAYS = 180

# Fields worth keeping for trend analysis. Everything else in daily_data
# (heart_rate, steps_intraday, all_day_stress, spo2, respiration, body_battery)
# is an intraday time-series — useful for the same-day report but not worth
# carrying forward day after day.
KEEP_FIELDS = (
    "date", "stats", "sleep", "training_readiness", "training_status", "hrv",
    "max_metrics", "resting_hr", "stress", "activities", "fitness_age",
    "endurance_score", "hill_score", "daily_weigh_ins", "body_composition",
    "intensity_minutes", "floors", "hydration", "body_battery_events",
    "race_predictions", "running_tolerance", "lactate_threshold",
)


def trim_for_log(daily_data: dict) -> dict:
    return {k: daily_data[k] for k in KEEP_FIELDS if k in daily_data}


def load_log() -> list[dict]:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def append_day(log: list[dict], trimmed_day: dict) -> list[dict]:
    date = trimmed_day.get("date")
    updated = [d for d in log if d.get("date") != date] + [trimmed_day]
    updated.sort(key=lambda d: d.get("date", ""))
    return updated[-MAX_DAYS:]


def save_log(log: list[dict]) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False, default=str)


def summarize_activities(log: list[dict], days: int = 28) -> dict:
    """Exact session counts/hours over the trailing window — computed here,
    not left to the model to tally from raw JSON."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    sessions = []
    for day in log:
        if day.get("date", "") < cutoff:
            continue
        activities = day.get("activities")
        if isinstance(activities, list):
            sessions.extend(activities)

    by_type: dict[str, dict] = {}
    total_seconds = 0.0
    for activity in sessions:
        duration = activity.get("duration") or 0
        total_seconds += duration
        type_key = (
            (activity.get("activityType") or {}).get("typeKey")
            or activity.get("activityName")
            or "other"
        )
        entry = by_type.setdefault(type_key, {"count": 0, "seconds": 0.0})
        entry["count"] += 1
        entry["seconds"] += duration

    return {
        "window_days": days,
        "total_sessions": len(sessions),
        "total_hours": round(total_seconds / 3600, 1),
        "by_type": {
            k: {"count": v["count"], "hours": round(v["seconds"] / 3600, 1)}
            for k, v in by_type.items()
        },
    }
