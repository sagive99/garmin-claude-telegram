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

ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
SCHEDULER_TOKEN = os.environ.get("SCHEDULER_TOKEN")


def _resp(status: int):
    return {"statusCode": status, "body": ""}


def handler(event, context):
    # Scheduled daily run — invoked directly by EventBridge Scheduler.
    if event.get("task") == "daily-report":
        daily.main()
        return {"ok": True}

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

        # 200 for anything we won't act on so Telegram doesn't retry.
        if text and (not ALLOWED_CHAT_ID or chat_id == str(ALLOWED_CHAT_ID)):
            chat.handle_message(text)
        return _resp(200)

    if path.endswith("/daily-report"):
        if SCHEDULER_TOKEN and headers.get("x-scheduler-token") != SCHEDULER_TOKEN:
            return _resp(403)
        daily.main()
        return _resp(200)

    return _resp(404)
