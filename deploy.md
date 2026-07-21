# Deploying to Cloud Run (from Cloud Shell — no local install)

One service, two triggers: Cloud Scheduler hits `/daily-report` once a day,
Telegram hits `/telegram-webhook` on each message. State lives in a GCS bucket.

## Step 0 — the part only you can do (needs your Google account + a card)

1. Go to <https://console.cloud.google.com> → create a project (or pick one).
   Note its **Project ID**.
2. Enable **billing** on that project (Billing → link a billing account). The
   always-free tier still covers a personal bot; the card is just required to
   turn Cloud Run on.
3. Open **Cloud Shell**: click the `>_` icon, top-right of the console. It has
   `gcloud`, `git`, and `docker` preinstalled — run everything below there.

## Step 1 — project + APIs

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com storage.googleapis.com
```

## Step 2 — clone the repo

```bash
git clone https://github.com/sagive99/garmin-claude-telegram
cd garmin-claude-telegram
```

## Step 3 — fill in your athlete profile

```bash
nano data/athlete_profile.json     # goals, split, injuries, motivation; Ctrl-O, Ctrl-X
```

## Step 4 — state bucket

Bucket names are globally unique — change the name if it's taken.

```bash
BUCKET=garmin-coach-$(date +%s)
gcloud storage buckets create gs://$BUCKET --location=us-central1
gcloud storage cp data/athlete_profile.json      gs://$BUCKET/athlete_profile.json
gcloud storage cp data/daily_log.json            gs://$BUCKET/daily_log.json
gcloud storage cp data/conversation_history.json gs://$BUCKET/conversation_history.json
echo "BUCKET=$BUCKET"     # note this
```

## Step 5 — secrets file

Create `env.yaml` (Cloud Shell only — never commit it; it's gitignored). Fill
in the five `...` values; the last two are pre-generated for you.

```bash
cat > env.yaml <<EOF
GCS_BUCKET: "$BUCKET"
GARMIN_EMAIL: "..."
GARMIN_PASSWORD: "..."
GEMINI_API_KEY: "..."
TELEGRAM_BOT_TOKEN: "..."
TELEGRAM_CHAT_ID: "..."
TELEGRAM_WEBHOOK_SECRET: "85c29c99b1a50057cc03231c8e40b82d"
SCHEDULER_TOKEN: "aac644c1b628c284fed39e37b8870884"
EOF
nano env.yaml     # paste your real values into the ... fields
```

An env file (not `--set-env-vars`) is used so a password with commas or `@`
survives intact and the secrets don't land in your shell history.

## Step 6 — deploy

```bash
gcloud run deploy garmin-coach \
  --source . \
  --region us-central1 \
  --min-instances 0 \
  --concurrency 1 \
  --allow-unauthenticated \
  --env-vars-file env.yaml
```

`--allow-unauthenticated` is fine: both routes are gated by their own secret
tokens, and the webhook has to be publicly reachable for Telegram anyway.

Grant the runtime service account read/write on the bucket:

```bash
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role=roles/storage.objectAdmin
```

Grab the service URL (used below):

```bash
SERVICE_URL=$(gcloud run services describe garmin-coach --region us-central1 --format='value(status.url)')
echo "$SERVICE_URL"
```

## Step 7 — register the Telegram webhook

```bash
source <(grep TELEGRAM_BOT_TOKEN env.yaml | sed 's/: /=/; s/"//g')
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=${SERVICE_URL}/telegram-webhook" \
  -d "secret_token=85c29c99b1a50057cc03231c8e40b82d"
```

## Step 8 — daily schedule (06:00 UTC — adjust)

```bash
gcloud scheduler jobs create http garmin-daily \
  --location us-central1 \
  --schedule "0 6 * * *" \
  --uri "${SERVICE_URL}/daily-report" \
  --http-method POST \
  --headers "X-Scheduler-Token=aac644c1b628c284fed39e37b8870884"
```

## Verify

```bash
curl "$SERVICE_URL/"                                   # -> ok
gcloud scheduler jobs run garmin-daily --location us-central1   # -> report in Telegram
```

Then message the bot — a reply should come back in a couple seconds.
