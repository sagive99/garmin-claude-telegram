"""Cloud Run entrypoint. Two routes on one service:

  POST /telegram-webhook  — inbound Telegram messages (interactive chat)
  POST /daily-report      — Cloud Scheduler trigger for the daily pipeline

Thin by design: auth + routing only. All logic lives in the reused modules.
"""
import os

from flask import Flask, request

import chat
import main as daily

app = Flask(__name__)

# Only respond to the owner. Telegram sends the chat id on every update.
ALLOWED_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# Set as the secret_token when registering the webhook; Telegram echoes it back.
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
# Shared secret so only Cloud Scheduler can trigger the daily run.
SCHEDULER_TOKEN = os.environ.get("SCHEDULER_TOKEN")


@app.get("/")
def health():
    return "ok", 200


@app.post("/telegram-webhook")
def telegram_webhook():
    if WEBHOOK_SECRET and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return "forbidden", 403

    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}
    text = message.get("text")
    chat_id = str((message.get("chat") or {}).get("id", ""))

    # Ack anything we won't act on with 200 so Telegram doesn't retry.
    if not text or (ALLOWED_CHAT_ID and chat_id != str(ALLOWED_CHAT_ID)):
        return "", 200

    chat.handle_message(text)
    return "", 200


@app.post("/daily-report")
def daily_report():
    if SCHEDULER_TOKEN and request.headers.get("X-Scheduler-Token") != SCHEDULER_TOKEN:
        return "forbidden", 403
    daily.main()
    return "", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
