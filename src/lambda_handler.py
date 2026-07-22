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

import chat
import main as daily
from google.genai.errors import APIError
from telegram_notify import send_message

ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
SCHEDULER_TOKEN = os.environ.get("SCHEDULER_TOKEN")


def _resp(status: int):
    return {"statusCode": status, "body": ""}


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
            return {"ok": False, "error": str(e)}

    # Otherwise it's a Function URL HTTP event.
    rc = event.get("requestContext") or {}
    path = (rc.get("http") or {}).get("path") or event.get("rawPath") or ""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    if path.endswith("/telegram-webhook"):
        if WEBHOOK_SECRET and headers.get("x-telegram-bot-api-secret-token") != WEBHOOK_SECRET:
            return _resp(403)

        update = json.loads(body or "{}")
        message = update.get("message") or update.get("edited_message") or {}
        text = message.get("text")
        chat_id = str((message.get("chat") or {}).get("id", ""))

        # Always return 200 so Telegram never retries. A raised error here =
        # ~12 webhook retries = ~12 wasted Gemini requests against the 20/day
        # free-tier cap. On failure, tell the user once with a plain message
        # (send_message uses the Telegram API, not Gemini, so it's free).
        if text and (not ALLOWED_CHAT_ID or chat_id == str(ALLOWED_CHAT_ID)):
            try:
                chat.handle_message(text)
            except APIError as e:
                print(f"chat failed: {e}")
                is_quota = e.code == 429 or e.status == "RESOURCE_EXHAUSTED"
                reply = (
                    "⚠️ Coach is out of AI quota for now — try again later."
                    if is_quota
                    else "⚠️ Coach hit an error and couldn't reply — try again later."
                )
                try:
                    send_message(reply)
                except Exception:
                    pass
            except Exception as e:
                print(f"chat failed: {e}")
                try:
                    send_message("⚠️ Coach hit an error and couldn't reply — try again later.")
                except Exception:
                    pass
        return _resp(200)

    if path.endswith("/daily-report"):
        if SCHEDULER_TOKEN and headers.get("x-scheduler-token") != SCHEDULER_TOKEN:
            return _resp(403)
        daily.main()
        return _resp(200)

    return _resp(404)
