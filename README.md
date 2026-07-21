# garmin-claude-telegram

Pulls yesterday's Garmin Connect data on a daily schedule, sends it to Claude
for analysis, and posts the result to a Telegram chat. Runs entirely on
GitHub Actions — no computer needs to be on.

**Heads up:** this uses the unofficial `garminconnect` Python library, which
reverse-engineers Garmin's private mobile API. It's not an officially
supported integration — it could break if Garmin changes something, and
technically isn't Garmin's sanctioned way of accessing your data. Fine for a
personal project, just don't rely on it for anything critical.

## How it works

1. `src/garmin_client.py` logs into Garmin Connect and pulls stats, sleep,
   heart rate, body battery, stress, and activities for the previous day.
2. `src/history.py` keeps a rolling conversation log
   (`data/conversation_history.json`) so Claude sees prior days' context —
   it behaves like one ongoing dedicated chat rather than a fresh call
   every time.
3. `src/claude_analyze.py` sends the data + history to the Claude API and
   gets back a short readable report.
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

### 2. Get an Anthropic API key
- Create one at [platform.claude.com](https://platform.claude.com) (previously
  called the Claude Console) → Settings → API Keys. Note this is billed
  separately from any claude.ai subscription.

### 3. Fork/push this repo to your own GitHub account

### 4. Add repo secrets
Go to **Settings → Secrets and variables → Actions** on your repo and add:

| Secret | Value |
|---|---|
| `GARMIN_EMAIL` | Your Garmin Connect login email |
| `GARMIN_PASSWORD` | Your Garmin Connect password |
| `ANTHROPIC_API_KEY` | From step 2 |
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
export ANTHROPIC_API_KEY=...
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
cd src
python main.py
```

## Notes / things you might want to change
- `garmin_client.py` pulls a fixed set of endpoints — trim or extend based
  on what you actually want analyzed.
- `history.py` caps history at 40 messages (~20 exchanges) to avoid
  unbounded growth; tune `MAX_TURNS` if you want more/less lookback.
- The Claude system prompt in `claude_analyze.py` controls tone/format of
  the report — edit it to match what's actually useful to you.
