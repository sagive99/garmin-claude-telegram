"""AWS Lambda entrypoint. One function, two trigger shapes:

  - EventBridge Scheduler invokes it with {"task": "daily-report"} once a day
    → runs the full Garmin pull + report pipeline.
  - A Function URL delivers Telegram webhook POSTs (and, optionally, an HTTP
    /daily-report) → handled as HTTP.

No web framework: Function URL events are plain dicts, so a few lines of
dispatch is lighter than dragging Flask + an adapter into the zip.
"""
import base64
import json
import os
import time

import chat
import main as daily
import storage
from telegram_notify import send_message

# Lambda's clock is UTC but the user's day is Israel time — affects the Garmin
# fetch date, the 28-day stats cutoff, and the date told to Gemini. tzset()
# doesn't exist on Windows; local dev already runs in the right timezone.
os.environ.setdefault("TZ", "Asia/Jerusalem")
if hasattr(time, "tzset"):
    time.tzset()

ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
SCHEDULER_TOKEN = os.environ.get("SCHEDULER_TOKEN")

SEEN_NAME = "processed_updates.json"


def _resp(status: int):
    return {"statusCode": status, "body": ""}


def _already_processed(update_id) -> bool:
    """Telegram retries a webhook (same update_id) when our response is slow —
    /report runs the multi-second Garmin pull inline, which blows Telegram's
    timeout and triggers a retry, i.e. a second pull + Gemini call. Record the
    id before the slow work; the retry only fires after Telegram's timeout, so
    the marker is already stored and the second invocation short-circuits."""
    if update_id is None:
        return False
    seen = storage.read_json(SEEN_NAME, [])
    if update_id in seen:
        return True
    storage.write_json(SEEN_NAME, (seen + [update_id])[-50:])
    return False


def handler(event, context):
    # Scheduled daily run — invoked directly by EventBridge Scheduler.
    if event.get("task") == "daily-report":
        # Never raise: a raised error makes Scheduler retry up to 185x/24h,
        # and each retry burns another Gemini request (20/day free-tier cap).
        try:
            daily.main()
            return {"ok": True}
        except Exception as e:
            print(f"daily failed: {e}")
            # Tell the user once instead of failing silently — send_message is
            # the Telegram API (free), so it doesn't touch the Gemini quota.
            try:
                send_message(
                    "⚠️ This morning's Garmin pull failed — send /report to retry."
                )
            except Exception:
                pass
            return {"ok": False, "error": str(e)}

    # Otherwise it's a Function URL HTTP event.
    rc = event.get("requestContext") or {}
    path = (rc.get("http") or {}).get("path") or event.get("rawPath") or ""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    if path.endswith("/telegram-webhook"):
        # Fail closed: a missing WEBHOOK_SECRET env var must mean "reject all",
        # not "accept all" — otherwise one config slip opens the bot to anyone
        # who finds the Function URL.
        if not WEBHOOK_SECRET or headers.get("x-telegram-bot-api-secret-token") != WEBHOOK_SECRET:
            return _resp(403)

        update = json.loads(body or "{}")
        if _already_processed(update.get("update_id")):
            return _resp(200)

        message = update.get("message") or update.get("edited_message") or {}
        text = message.get("text")
        chat_id = str((message.get("chat") or {}).get("id", ""))

        # Always return 200 so Telegram never retries. A raised error here =
        # ~12 webhook retries = ~12 wasted Gemini requests against the 20/day
        # free-tier cap. On failure, tell the user once with a plain message
        # (send_message uses the Telegram API, not Gemini, so it's free).
        if text and (not ALLOWED_CHAT_ID or chat_id == str(ALLOWED_CHAT_ID)):
            # /report@BotName -> /report ; whitespace-only text -> ""
            cmd = (text.strip().split() or [""])[0].split("@")[0].lower()
            if cmd in ("/report", "/update"):
                # On-demand daily report: pull today's Garmin data and analyze
                # it now, so chat isn't stuck saying "I don't have today's data".
                # Ack first — the Garmin pull takes several seconds.
                try:
                    send_message("📊 Pulling your latest Garmin data...")
                    daily.main()
                except Exception as e:
                    print(f"report failed: {e}")
                    try:
                        send_message("⚠️ Garmin pull failed — wait a minute or two, then send /report again.")
                    except Exception:
                        pass
            elif cmd in ("/help", "/start"):
                try:
                    send_message(
                        "Commands:\n"
                        "/report — pull today's Garmin data and post a fresh report\n"
                        "Anything else you type goes straight to the coach."
                    )
                except Exception as e:
                    print(f"help failed: {e}")
            else:
                try:
                    chat.handle_message(text)
                except Exception as e:
                    print(f"chat failed: {e}")
                    try:
                        send_message("⚠️ Coach hit an error answering that — try again in a minute.")
                    except Exception:
                        pass
        return _resp(200)

    if path.endswith("/daily-report"):
        if not SCHEDULER_TOKEN or headers.get("x-scheduler-token") != SCHEDULER_TOKEN:
            return _resp(403)
        daily.main()
        return _resp(200)

    return _resp(404)
