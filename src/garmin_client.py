"""Pulls a day's activity + health data from Garmin Connect.

Uses the unofficial `garminconnect` library (reverse-engineered from the
Garmin Connect mobile API). This is NOT an officially supported integration —
Garmin could change something on their end and break it. Treat it as a
personal-use tool, not production infrastructure.
"""
import datetime
import json
import os

from garminconnect import Garmin

# ponytail: no token cache — dedup means ~1 login/day, under Garmin's 429
# threshold, so a plain login is enough. Re-add garth token reuse (garminconnect
# exposes it through client.garth — verify the exact dump/load call against the
# pinned version first) only if login-rate 429s come back under normal use.


def fetch_daily_summary(target_date: datetime.date | None = None) -> dict:
    """Log in to Garmin Connect and pull a summary of one day's data.

    Credentials come from env vars GARMIN_EMAIL / GARMIN_PASSWORD.
    """
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    # Default to today: run in the morning, this gives last night's sleep and
    # this morning's HRV/readiness/body battery. Garmin files a night's sleep
    # under the date you wake up, so "today" is the freshest recovery picture.
    if target_date is None:
        target_date = datetime.date.today()
    date_str = target_date.isoformat()

    client = Garmin(email, password)
    client.login()

    summary: dict = {"date": date_str}

    # Wrap each call so one failing endpoint doesn't kill the whole run —
    # Garmin's API is inconsistent about what's available on a given day.
    def safe_get(label, fn):
        try:
            summary[label] = fn()
        except Exception as e:
            summary[label] = {"error": str(e)}

    safe_get("stats", lambda: client.get_stats(date_str))
    safe_get("sleep", lambda: client.get_sleep_data(date_str))
    safe_get("heart_rate", lambda: client.get_heart_rates(date_str))
    safe_get("body_battery", lambda: client.get_body_battery(date_str))
    safe_get("activities", lambda: client.get_activities_by_date(date_str, date_str))
    safe_get("stress", lambda: client.get_stress_data(date_str))

    # Recovery/load signals — these are what turn a data dump into coaching:
    # readiness score + why, HRV status, and Garmin's own training load read.
    safe_get("training_readiness", lambda: client.get_training_readiness(date_str))
    safe_get("training_status", lambda: client.get_training_status(date_str))
    safe_get("hrv", lambda: client.get_hrv_data(date_str))
    safe_get("max_metrics", lambda: client.get_max_metrics(date_str))

    # Everything else Garmin exposes per-day. Some of these need a device
    # Garmin doesn't sync for everyone (e.g. lactate threshold needs a
    # running power meter) — safe_get just records the error for those
    # instead of failing the run, so it's harmless to ask for all of it.
    safe_get("respiration", lambda: client.get_respiration_data(date_str))
    safe_get("spo2", lambda: client.get_spo2_data(date_str))
    safe_get("floors", lambda: client.get_floors(date_str))
    safe_get("intensity_minutes", lambda: client.get_intensity_minutes_data(date_str))
    safe_get("resting_hr", lambda: client.get_rhr_day(date_str))
    safe_get("hydration", lambda: client.get_hydration_data(date_str))
    safe_get("body_composition", lambda: client.get_body_composition(date_str, date_str))
    safe_get("daily_weigh_ins", lambda: client.get_daily_weigh_ins(date_str))
    safe_get("endurance_score", lambda: client.get_endurance_score(date_str, date_str))
    safe_get("hill_score", lambda: client.get_hill_score(date_str, date_str))
    safe_get("fitness_age", lambda: client.get_fitnessage_data(date_str))
    safe_get("all_day_stress", lambda: client.get_all_day_stress(date_str))
    safe_get("body_battery_events", lambda: client.get_body_battery_events(date_str))
    safe_get("steps_intraday", lambda: client.get_steps_data(date_str))
    safe_get("daily_steps", lambda: client.get_daily_steps(date_str, date_str))
    safe_get("race_predictions", lambda: client.get_race_predictions(startdate=date_str, enddate=date_str))
    safe_get("running_tolerance", lambda: client.get_running_tolerance(date_str, date_str))
    safe_get(
        "lactate_threshold",
        lambda: client.get_lactate_threshold(latest=False, start_date=date_str, end_date=date_str),
    )

    # Full trailing-window activity list in one call, so session counts/hours
    # are accurate from the very first run instead of waiting for the daily
    # log to fill up day by day.
    window_start = (target_date - datetime.timedelta(days=27)).isoformat()
    safe_get("activities_28d", lambda: client.get_activities_by_date(window_start, date_str))

    return summary


if __name__ == "__main__":
    # Quick local test: prints the payload instead of sending anywhere.
    print(json.dumps(fetch_daily_summary(), indent=2, default=str))
