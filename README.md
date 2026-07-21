# garmin-claude-telegram

A self-hosted AI training coach on Telegram, backed by your Garmin data.
Every morning it pulls yesterday's Garmin Connect data, sends it to Gemini,
and posts a coach-style verdict (go hard / train easy / rest, with the
evidence) to your Telegram chat. You can also **message the bot any time** and
it answers from your data and history. Runs on AWS Lambda — no computer needs
to be on.

**Heads up:** this uses the unofficial `garminconnect` Python library, which
reverse-engineers Garmin's private mobile API. It's not an officially
supported integration — it could break if Garmin changes something, and
technically isn't Garmin's sanctioned way of accessing your data. Fine for a
personal project, just don't rely on it for anything critical.

## How it works

One Lambda function, two trigger shapes:

- **Daily report** — EventBridge Scheduler invokes it once a day with
  `{"task":"daily-report"}`. Runs the full pipeline: fetch Garmin → analyze →
  post to Telegram → persist state.
- **Chat** — a Lambda Function URL delivers Telegram webhook POSTs. Each
  message is answered from the same stored context, then the turn is persisted.

The pieces:

1. `src/garmin_client.py` logs into Garmin Connect and pulls essentially
   everything it exposes for the previous day: stats, sleep, heart rate,
   body battery (+ events), stress (+ all-day detail), activities, training
   readiness, training status, HRV, max metrics, respiration, SpO2, floors,
   intensity minutes, resting HR, hydration, body composition, weigh-ins,
   endurance/hill score, fitness age, steps (intraday + daily), race
   predictions, running tolerance, and lactate threshold. Endpoints that
   need a device you don't have (e.g. lactate threshold) just record an
   error for that field instead of failing the run.
2. `src/history.py` keeps a rolling conversation log
   (`conversation_history.json`) shared by the daily report *and* chat, so
   Gemini sees prior context and it all reads as one continuous thread.
3. `src/daily_log.py` keeps a separate, trimmed rolling log
   (`daily_log.json`, up to 180 days) of just the aggregate fields — no
   intraday arrays — and computes exact session counts/hours per activity
   type over the trailing window in Python. This exists because asking an LLM
   to tally "how many sessions in the last 28 days" from raw JSON is
   unreliable; the count going into the prompt is always correct.
4. `src/athlete_profile.py` loads `athlete_profile.json` — your self-reported
   goals, training split, injuries, motivation — so advice is tailored, not
   guessed from data alone.
5. `src/gemini_analyze.py` — `analyze_day()` produces the daily verdict;
   `chat_reply()` answers free-form messages. Both thread through the shared
   history and treat the computed activity stats as ground truth.
6. `src/chat.py` is the inbound-message handler; `src/telegram_notify.py`
   posts messages to Telegram.
7. `src/storage.py` reads/writes the JSON state in an **S3 bucket** on Lambda
   (`S3_BUCKET` env var), or the local `data/` dir when that's unset — so
   local testing needs no cloud setup.
8. `src/lambda_handler.py` is the Lambda entrypoint: it routes the scheduled
   event to the daily pipeline and Function URL requests to the chat/webhook
   logic. No web framework — the events are plain dicts.

### Scope / what it doesn't do
- **Chat answers from stored data**, not a live Garmin pull per message — the
  morning job already logged last night's data, so "how did I sleep" works
  without a re-login. On-demand live fetch is a deliberate later add (see
  `src/chat.py`).
- **Proactive nudges** come from the daily report adapting its verdict. True
  real-time "you just finished a hard session" pings would need periodic
  activity polling — not built.
- **Single user.** The webhook only responds to the chat ID in
  `TELEGRAM_CHAT_ID` and ignores everything else.

## Setup

### 1. Create a Telegram bot
- Message **@BotFather** on Telegram → `/newbot` → follow the prompts →
  you'll get a **bot token**.
- Message your new bot at least once (so it can message you back).
- Get your **chat ID**: message the bot, then visit
  `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and
  find `"chat":{"id": ...}` in the response.

### 2. Get a Gemini API key
- Create one at [Google AI Studio](https://aistudio.google.com/apikey) →
  Create API key. Free tier available; check current quotas/pricing there.

### 3. Fill in your athlete profile
Edit `data/athlete_profile.json` with your goals, training split, injuries,
motivation — whatever context you'd tell a real coach. It shapes the advice.

### 4. Deploy to AWS Lambda
Follow [`deploy_aws.md`](deploy_aws.md): all copy-paste, runnable entirely in
**AWS CloudShell** (browser — no local install, no Docker). It creates the S3
state bucket, builds the zip, creates the Lambda + Function URL, registers the
Telegram webhook, and creates the EventBridge Scheduler job.

## Local testing

State falls back to the local `data/` dir when `S3_BUCKET` is unset.

```bash
pip install -r requirements.txt
export GARMIN_EMAIL=... GARMIN_PASSWORD=...
export GEMINI_API_KEY=...
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
cd src

# Run the daily pipeline once (fetch + analyze + send + persist):
python main.py

# Exercise the chat handler with a fake Function URL event:
python -c 'import json,os,lambda_handler as h; print(h.handler({"rawPath":"/telegram-webhook","requestContext":{"http":{"path":"/telegram-webhook"}},"headers":{},"body":json.dumps({"message":{"text":"how did I sleep this week?","chat":{"id":int(os.environ["TELEGRAM_CHAT_ID"])}}})}, None))'
```

## Notes / things you might want to change
- `garmin_client.py` pulls a fixed set of endpoints — trim or extend based
  on what you actually want analyzed.
- `history.py` caps history at 40 messages (~20 exchanges); tune `MAX_TURNS`.
- `daily_log.py` caps the aggregate log at 180 days (`MAX_DAYS`) and the
  rolling activity stats window at 28 days (`summarize_activities(days=...)`)
  — tune either for a longer/shorter lookback.
- The prompts in `gemini_analyze.py` (`SYSTEM_PROMPT` for the daily report,
  `CHAT_SYSTEM_PROMPT` for chat) control tone/format — edit to taste.
