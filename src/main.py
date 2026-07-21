import sys

from gemini_analyze import analyze_day
from garmin_client import fetch_daily_summary
from history import load_history, save_history
from daily_log import load_log, save_log, append_day, trim_for_log, summarize_activities
from athlete_profile import load_profile
from telegram_notify import send_message


def main() -> None:
    print("Fetching Garmin data...")
    daily_data = fetch_daily_summary()

    print("Loading conversation history...")
    history = load_history()

    print("Updating rolling activity log...")
    log = append_day(load_log(), trim_for_log(daily_data))
    activity_stats = summarize_activities(log, days=28)

    print("Loading athlete profile...")
    profile = load_profile()

    print("Asking Gemini for analysis...")
    reply_text, updated_history = analyze_day(daily_data, history, profile, activity_stats)

    print("Sending to Telegram...")
    send_message(reply_text)

    print("Saving updated history...")
    save_history(updated_history)
    save_log(log)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Run failed: {e}", file=sys.stderr)
        raise
