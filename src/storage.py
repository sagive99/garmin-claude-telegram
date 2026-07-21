"""JSON state storage. Uses a GCS bucket when GCS_BUCKET is set (Cloud Run),
otherwise the local data/ directory (local dev/testing, no cloud needed).

Both the daily report and the chat webhook share this so there's one source
of truth for conversation history, the rolling daily log, and the profile.
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BUCKET = os.environ.get("GCS_BUCKET")

_gcs_bucket = None


def _bucket():
    global _gcs_bucket
    if _gcs_bucket is None:
        from google.cloud import storage
        _gcs_bucket = storage.Client().bucket(BUCKET)
    return _gcs_bucket


def read_json(name: str, default):
    if BUCKET:
        blob = _bucket().blob(name)
        if not blob.exists():
            return default
        return json.loads(blob.download_as_text())

    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(name: str, obj) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    if BUCKET:
        _bucket().blob(name).upload_from_string(text, content_type="application/json")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        f.write(text)
