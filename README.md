# garmin-claude-telegram

Pulls yesterday's Garmin Connect data on a daily schedule, sends it to Gemini
for analysis, and posts the result to a Telegram chat. Runs entirely on
GitHub Actions — no computer needs to be on.

**Heads up:** this uses the unofficial `garminconnect` Python library, which
reverse-engineers Garmin's private mobile API. It's not an officially
supported integration — it could break if Garmin changes something, and
technically isn't Garmin's sanctioned way of accessing your data. Fine for a
personal project, just don't rely on it for anything critical.

## How it works

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
   (`data/conversation_history.json`) so Gemini sees prior days' context —
   it behaves like one ongoing dedicated chat rather than a fresh call
   every time.
3. `src/gemini_analyze.py` sends the data + history to the Gemini API and
   gets back a coach-style verdict (go hard / train easy / rest, with the
   evidence) rather than a plain data summary — similar in spirit to what
   apps like athletedata.health do, just self-hosted and Garmin-only.
4. `src/telegram_notify.py` posts that report to your Telegram chat.
5. The GitHub Actions workflow commits the updated history file back to the
   repo after each run so continuity persists.

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

### 3. Fork/push this repo to your own GitHub account

### 4. Add repo secrets
Go to **Settings → Secrets and variables → Actions** on your repo and add:

| Secret | Value |
|---|---|
| `GARMIN_EMAIL` | Your Garmin Connect login email |
| `GARMIN_PASSWORD` | Your Garmin Connect password |
| `GEMINI_API_KEY` | From step 2 |
| `TELEGRAM_BOT_TOKEN` | From step 1 |
| `TELEGRAM_CHAT_ID` | From step 1 |

### 5. Test it
Go to the **Actions** tab → **Daily Garmin Report** → **Run workflow** to
trigger it manually before waiting for the schedule.

### 6. Adjust the schedule
Edit the `cron` line in `.github/workflows/daily-report.yml`. It's in UTC —
use [crontab.guru](https://crontab.guru) to convert your local time.

## Local testing

```bash
pip install -r requirements.txt
export GARMIN_EMAIL=... GARMIN_PASSWORD=...
export GEMINI_API_KEY=...
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
cd src
python main.py
```

## Notes / things you might want to change
- `garmin_client.py` pulls a fixed set of endpoints — trim or extend based
  on what you actually want analyzed.
- `history.py` caps history at 40 messages (~20 exchanges) to avoid
  unbounded growth; tune `MAX_TURNS` if you want more/less lookback.
- The system prompt in `gemini_analyze.py` controls tone/format of
  the report — edit it to match what's actually useful to you.
