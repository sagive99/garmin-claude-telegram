# Deploying to Cloud Run

One service, two triggers: Cloud Scheduler hits `/daily-report` once a day,
Telegram hits `/telegram-webhook` on each message. State lives in a GCS bucket.

Prereqs: a GCP project with billing enabled, `gcloud` installed and logged in
(`gcloud auth login`), and these APIs on:

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com storage.googleapis.com
```

## 1. State bucket + seed the profile

```bash
gcloud storage buckets create gs://YOUR_BUCKET --location=us-central1
# Seed the empty state so first reads don't have to special-case a fresh bucket.
gcloud storage cp data/athlete_profile.json gs://YOUR_BUCKET/athlete_profile.json
gcloud storage cp data/daily_log.json        gs://YOUR_BUCKET/daily_log.json
gcloud storage cp data/conversation_history.json gs://YOUR_BUCKET/conversation_history.json
```

Edit `data/athlete_profile.json` first (goals, split, injuries, motivation),
then re-upload it whenever you change it.

## 2. Pick secrets

- `TELEGRAM_WEBHOOK_SECRET` and `SCHEDULER_TOKEN`: any random strings, e.g.
  `openssl rand -hex 16`. They gate the two routes.

## 3. Deploy

```bash
gcloud run deploy garmin-coach \
  --source . \
  --region us-central1 \
  --min-instances 0 \
  --concurrency 1 \
  --allow-unauthenticated \
  --set-env-vars "GCS_BUCKET=YOUR_BUCKET" \
  --set-env-vars "GARMIN_EMAIL=...,GARMIN_PASSWORD=..." \
  --set-env-vars "GEMINI_API_KEY=...,TELEGRAM_BOT_TOKEN=...,TELEGRAM_CHAT_ID=..." \
  --set-env-vars "TELEGRAM_WEBHOOK_SECRET=...,SCHEDULER_TOKEN=..."
```

The service account Cloud Run runs as needs read/write on the bucket:

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role=roles/storage.objectAdmin
```

Note the deployed URL (shown after deploy), call it `SERVICE_URL` below.

`--allow-unauthenticated` is fine because both routes are gated by their own
secret tokens; the webhook must be publicly reachable for Telegram anyway.

## 4. Register the Telegram webhook

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=SERVICE_URL/telegram-webhook" \
  -d "secret_token=YOUR_TELEGRAM_WEBHOOK_SECRET"
```

## 5. Daily schedule

```bash
gcloud scheduler jobs create http garmin-daily \
  --location us-central1 \
  --schedule "0 6 * * *" \
  --uri "SERVICE_URL/daily-report" \
  --http-method POST \
  --headers "X-Scheduler-Token=YOUR_SCHEDULER_TOKEN"
```

## Verify

- `curl SERVICE_URL/` → `ok`.
- Trigger the daily run once: `gcloud scheduler jobs run garmin-daily --location us-central1`
  → a report lands in Telegram, bucket JSON updates.
- Message the bot → a reply comes back in a couple seconds.
