import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

STORAGE_MODE = os.getenv("STORAGE_MODE", "local").lower()
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
LOCAL_DIR = Path("local_data")


def _ensure_local():
    (LOCAL_DIR / "venues").mkdir(parents=True, exist_ok=True)
    (LOCAL_DIR / "ics").mkdir(parents=True, exist_ok=True)


def create_venue_id(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")
    slug = "-".join(part for part in slug.split("-") if part)[:24] or "venue"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def save_venue(venue_data: dict, ics_content: str) -> dict:
    venue_id = venue_data.get("venue_id") or create_venue_id(venue_data["name"])
    venue_data["venue_id"] = venue_id
    venue_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    if STORAGE_MODE == "gcp":
        from google.cloud import firestore, storage
        db = firestore.Client()
        db.collection("venues").document(venue_id).set(venue_data)
        if GCS_BUCKET_NAME:
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET_NAME)
            blob = bucket.blob(f"ics/{venue_id}.ics")
            blob.upload_from_string(ics_content, content_type="text/calendar; charset=utf-8")
    else:
        _ensure_local()
        (LOCAL_DIR / "venues" / f"{venue_id}.json").write_text(
            json.dumps(venue_data, indent=2), encoding="utf-8"
        )
        (LOCAL_DIR / "ics" / f"{venue_id}.ics").write_text(ics_content, encoding="utf-8")

    return venue_data


def get_venue(venue_id: str) -> Optional[dict]:
    if STORAGE_MODE == "gcp":
        from google.cloud import firestore
        doc = firestore.Client().collection("venues").document(venue_id).get()
        return doc.to_dict() if doc.exists else None
    else:
        path = LOCAL_DIR / "venues" / f"{venue_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


def get_ics(venue_id: str) -> Optional[str]:
    if STORAGE_MODE == "gcp" and GCS_BUCKET_NAME:
        from google.cloud import storage
        blob = storage.Client().bucket(GCS_BUCKET_NAME).blob(f"ics/{venue_id}.ics")
        return blob.download_as_text(encoding="utf-8") if blob.exists() else None
    else:
        path = LOCAL_DIR / "ics" / f"{venue_id}.ics"
        return path.read_text(encoding="utf-8") if path.exists() else None


def list_venues() -> List[dict]:
    if STORAGE_MODE == "gcp":
        from google.cloud import firestore
        docs = firestore.Client().collection("venues").limit(25).stream()
        return [d.to_dict() for d in docs]
    else:
        _ensure_local()
        items = []
        for p in sorted((LOCAL_DIR / "venues").glob("*.json"), reverse=True):
            items.append(json.loads(p.read_text(encoding="utf-8")))
        return items
