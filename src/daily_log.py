"""Keeps a rolling log of each day's Garmin summary, separate from the chat
history, so multi-week stats (session counts, hours by activity type) can be
computed exactly in Python instead of asking the LLM to count across many
turns of raw JSON — LLMs are unreliable at that kind of arithmetic.

Only the aggregate/summary fields are kept per day (not the intraday arrays
like raw heart rate or step-by-step traces) so the log stays small even at a
year of history.
"""
import datetime

import storage

LOG_NAME = "daily_log.json"
STATS_NAME = "activity_stats.json"
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
    return storage.read_json(LOG_NAME, [])


def append_day(log: list[dict], trimmed_day: dict) -> list[dict]:
    date = trimmed_day.get("date")
    updated = [d for d in log if d.get("date") != date] + [trimmed_day]
    updated.sort(key=lambda d: d.get("date", ""))
    return updated[-MAX_DAYS:]


def save_log(log: list[dict]) -> None:
    storage.write_json(LOG_NAME, log)


def save_activity_stats(stats: dict) -> None:
    storage.write_json(STATS_NAME, stats)


def load_activity_stats() -> dict:
    return storage.read_json(STATS_NAME, {})


def summarize_activities(activities: list[dict], days: int = 28) -> dict:
    """Exact session counts/hours over the trailing window, computed in Python
    (not left to the model to tally from raw JSON). Takes the flat activity
    list Garmin returns for a date range, filtered to the window by each
    activity's start date."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    by_type: dict[str, dict] = {}
    sessions: list[dict] = []
    total_seconds = 0.0
    count = 0
    for activity in activities or []:
        start = (activity.get("startTimeLocal") or activity.get("startTimeGMT") or "")[:10]
        if start and start < cutoff:
            continue
        count += 1
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
        sessions.append({
            "date": start,
            "type": type_key,
            "name": activity.get("activityName"),
            "minutes": round(duration / 60),
        })

    sessions.sort(key=lambda s: s["date"])
    return {
        "window_days": days,
        "total_sessions": count,
        "total_hours": round(total_seconds / 3600, 1),
        "by_type": {
            k: {"count": v["count"], "hours": round(v["seconds"] / 3600, 1)}
            for k, v in by_type.items()
        },
        # Per-day session list so chat can answer "what did I do yesterday" from
        # real data instead of guessing. Tiny (~one line per session).
        "sessions": sessions,
    }


if __name__ == "__main__":
    _acts = [
        {"startTimeLocal": "2026-07-20 18:00:00", "duration": 3600,
         "activityType": {"typeKey": "strength_training"}, "activityName": "Pull A"},
        {"startTimeLocal": "2026-07-19 17:00:00", "duration": 5400,
         "activityType": {"typeKey": "tennis_v2"}, "activityName": "Tennis"},
        {"startTimeLocal": "2026-06-01 10:00:00", "duration": 1800,  # outside 28d
         "activityType": {"typeKey": "running"}, "activityName": "Run"},
    ]
    s = summarize_activities(_acts, days=28)
    assert s["total_sessions"] == 2, s
    assert s["by_type"]["strength_training"]["count"] == 1, s
    assert s["sessions"][-1]["name"] == "Pull A", s  # newest last
    print("OK", s)
