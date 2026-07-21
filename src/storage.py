"""JSON state storage. Uses an S3 bucket when S3_BUCKET is set (on Lambda),
otherwise the local data/ directory (local dev/testing, no cloud needed).

Both the daily report and the chat webhook share this so there's one source
of truth for conversation history, the rolling daily log, and the profile.
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BUCKET = os.environ.get("S3_BUCKET")

_s3 = None


def _client():
    global _s3
    if _s3 is None:
        import boto3  # bundled in the Lambda runtime; lazy so local dev needn't install it
        _s3 = boto3.client("s3")
    return _s3


def read_json(name: str, default):
    if BUCKET:
        client = _client()
        try:
            obj = client.get_object(Bucket=BUCKET, Key=name)
        except client.exceptions.NoSuchKey:
            return default
        return json.loads(obj["Body"].read())

    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(name: str, obj) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    if BUCKET:
        _client().put_object(
            Bucket=BUCKET, Key=name,
            Body=text.encode("utf-8"), ContentType="application/json",
        )
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        f.write(text)
