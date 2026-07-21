import sys

from claude_analyze import analyze_day
from garmin_client import fetch_daily_summary
from history import load_history, save_history
from telegram_notify import send_message


def main() -> None:
    print("Fetching Garmin data...")
    daily_data = fetch_daily_summary()

    print("Loading conversation history...")
    history = load_history()

    print("Asking Claude for analysis...")
    reply_text, updated_history = analyze_day(daily_data, history)

    print("Sending to Telegram...")
    send_message(reply_text)

    print("Saving updated history...")
    save_history(updated_history)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Run failed: {e}", file=sys.stderr)
        raise
