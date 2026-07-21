"""Pulls yesterday's activity + health data from Garmin Connect.

Uses the unofficial `garminconnect` library (reverse-engineered from the
Garmin Connect mobile API). This is NOT an officially supported integration —
Garmin could change something on their end and break it. Treat it as a
personal-use tool, not production infrastructure.
"""
import datetime
import json
import os

from garminconnect import Garmin


def fetch_daily_summary(target_date: datetime.date | None = None) -> dict:
    """Log in to Garmin Connect and pull a summary of one day's data.

    Credentials come from env vars GARMIN_EMAIL / GARMIN_PASSWORD (set as
    GitHub Actions secrets — never hardcode them).
    """
    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    if target_date is None:
        target_date = datetime.date.today() - datetime.timedelta(days=1)
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

    return summary


if __name__ == "__main__":
    # Quick local test: prints the payload instead of sending anywhere.
    print(json.dumps(fetch_daily_summary(), indent=2, default=str))
