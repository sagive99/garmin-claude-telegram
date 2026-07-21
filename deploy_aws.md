# Deploying to AWS Lambda (from CloudShell — no local install)

One Lambda function, two trigger shapes: EventBridge Scheduler invokes it
daily with `{"task":"daily-report"}`; a Function URL delivers Telegram webhook
messages. State lives in an S3 bucket. Effectively free (Lambda 1M req/mo +
400k GB-s always-free; Function URL free; Scheduler ~30 invokes/mo; S3 pennies).

## Step 0 — open CloudShell

Log into the AWS console, pick your region (top-right), and click the
**CloudShell** icon (`>_`, top bar). It has `aws`, `git`, `python`, and `zip`
preinstalled — run everything below there. No Docker needed (plain zip deploy).

```bash
export AWS_REGION=$(aws configure get region || echo us-east-1)
export FN=garmin-coach
export BUCKET=garmin-coach-state-$(date +%s)   # S3 bucket, globally unique
echo "region=$AWS_REGION bucket=$BUCKET"
```

## Step 1 — clone + profile

```bash
git clone https://github.com/sagive99/garmin-claude-telegram
cd garmin-claude-telegram
nano data/athlete_profile.json     # goals, split, injuries, motivation
```

## Step 2 — state bucket + seed

```bash
aws s3 mb s3://$BUCKET --region $AWS_REGION
aws s3 cp data/athlete_profile.json      s3://$BUCKET/athlete_profile.json
aws s3 cp data/daily_log.json            s3://$BUCKET/daily_log.json
aws s3 cp data/conversation_history.json s3://$BUCKET/conversation_history.json
```

## Step 3 — build the zip (Linux wheels for py3.12)

```bash
rm -rf build function.zip
pip install --target build --platform manylinux2014_x86_64 \
  --python-version 3.12 --implementation cp --only-binary=:all: \
  -r requirements.txt
cp src/*.py build/
(cd build && zip -qr ../function.zip .)
aws s3 cp function.zip s3://$BUCKET/function.zip     # >50MB, so deploy via S3
```

## Step 4 — IAM role for the function

```bash
cat > trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
aws iam create-role --role-name ${FN}-role --assume-role-policy-document file://trust.json
aws iam attach-role-policy --role-name ${FN}-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
cat > s3policy.json <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject"],"Resource":"arn:aws:s3:::$BUCKET/*"}]}
EOF
aws iam put-role-policy --role-name ${FN}-role --policy-name s3-state --policy-document file://s3policy.json
ROLE_ARN=$(aws iam get-role --role-name ${FN}-role --query 'Role.Arn' --output text)
sleep 10     # let the role propagate before the function references it
```

## Step 5 — secrets file + create the function

Fill in the five `...` values; the last two are pre-generated for you. A JSON
file (not inline) so a password with special chars survives; it's gitignored.

```bash
cat > env.json <<EOF
{"Variables":{
  "S3_BUCKET":"$BUCKET",
  "GARMIN_EMAIL":"...",
  "GARMIN_PASSWORD":"...",
  "GEMINI_API_KEY":"...",
  "TELEGRAM_BOT_TOKEN":"...",
  "TELEGRAM_CHAT_ID":"...",
  "TELEGRAM_WEBHOOK_SECRET":"85c29c99b1a50057cc03231c8e40b82d",
  "SCHEDULER_TOKEN":"aac644c1b628c284fed39e37b8870884"
}}
EOF
nano env.json     # paste your real values into the ... fields

aws lambda create-function --function-name $FN \
  --runtime python3.12 --architecture x86_64 \
  --handler lambda_handler.handler --role $ROLE_ARN \
  --code S3Bucket=$BUCKET,S3Key=function.zip \
  --timeout 120 --memory-size 512 \
  --environment file://env.json --region $AWS_REGION
```

## Step 6 — public Function URL

`NONE` auth is fine: both routes are gated by their own secret tokens, and the
webhook must be publicly reachable for Telegram anyway.

```bash
aws lambda create-function-url-config --function-name $FN \
  --auth-type NONE --region $AWS_REGION
aws lambda add-permission --function-name $FN --statement-id fnurl \
  --action lambda:InvokeFunctionUrl --principal '*' \
  --function-url-auth-type NONE --region $AWS_REGION
FN_URL=$(aws lambda get-function-url-config --function-name $FN \
  --query FunctionUrl --output text --region $AWS_REGION)
echo "$FN_URL"
```

## Step 7 — register the Telegram webhook

```bash
TG=$(grep TELEGRAM_BOT_TOKEN env.json | sed -E 's/.*"TELEGRAM_BOT_TOKEN":"([^"]+)".*/\1/')
curl "https://api.telegram.org/bot${TG}/setWebhook" \
  -d "url=${FN_URL}telegram-webhook" \
  -d "secret_token=85c29c99b1a50057cc03231c8e40b82d"
```

## Step 8 — daily schedule (06:00 UTC — adjust)

```bash
cat > sched-trust.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"scheduler.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF
aws iam create-role --role-name ${FN}-sched-role --assume-role-policy-document file://sched-trust.json
FN_ARN=$(aws lambda get-function --function-name $FN --query 'Configuration.FunctionArn' --output text --region $AWS_REGION)
cat > sched-policy.json <<EOF
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"lambda:InvokeFunction","Resource":"$FN_ARN"}]}
EOF
aws iam put-role-policy --role-name ${FN}-sched-role --policy-name invoke --policy-document file://sched-policy.json
SCHED_ROLE_ARN=$(aws iam get-role --role-name ${FN}-sched-role --query 'Role.Arn' --output text)
sleep 10
aws scheduler create-schedule --name garmin-daily \
  --schedule-expression "cron(0 6 * * ? *)" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target "{\"Arn\":\"$FN_ARN\",\"RoleArn\":\"$SCHED_ROLE_ARN\",\"Input\":\"{\\\"task\\\":\\\"daily-report\\\"}\"}" \
  --region $AWS_REGION
```

## Verify

```bash
# fire the daily pipeline once → a report should land in Telegram
aws lambda invoke --function-name $FN --payload '{"task":"daily-report"}' \
  --cli-binary-format raw-in-base64-out --region $AWS_REGION out.json && cat out.json
```

Then message the bot — a reply should come back in a couple seconds.

## Updating the code later

```bash
git pull && rm -rf build function.zip
pip install --target build --platform manylinux2014_x86_64 --python-version 3.12 \
  --implementation cp --only-binary=:all: -r requirements.txt
cp src/*.py build/ && (cd build && zip -qr ../function.zip .)
aws s3 cp function.zip s3://$BUCKET/function.zip
aws lambda update-function-code --function-name $FN \
  --s3-bucket $BUCKET --s3-key function.zip --region $AWS_REGION
```
