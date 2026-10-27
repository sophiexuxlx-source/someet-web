"""
SoMeet Web - User Quota & Usage Tracking Service
Tracks recording duration for standard users (60 minutes free quota)
and provides capacity expansion request handling.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

USAGE_FILE = DATA_DIR / "user_usage.json"
REQUESTS_FILE = DATA_DIR / "capacity_requests.json"

DEFAULT_FREE_QUOTA_SECONDS = 3600  # 1 hour free recording for standard users
UNLIMITED_ADMIN_EMAILS = {
    "sophiexuxlx@gmail.com",
    "xusophiexiaoxiao@gmail.com"
}
ADMIN_CONTACT_EMAIL = "sophiexuxlx@gmail.com"

_lock = threading.Lock()


def is_unlimited_user(email: str) -> bool:
    """Returns True if the email belongs to Sophie (Founder / Lifetime Unlimited)."""
    if not email:
        return False
    return email.strip().lower() in UNLIMITED_ADMIN_EMAILS


def _load_json(file_path: Path) -> dict:
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[UsageService] Error reading {file_path}: {e}")
        return {}


def _save_json(file_path: Path, data: dict):
    tmp_path = file_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(file_path)
    except Exception as e:
        print(f"[UsageService] Error writing {file_path}: {e}")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass


def get_user_usage(uid: str, email: str) -> dict:
    """Returns user tier, quota, recorded usage, and remaining seconds."""
    unlimited = is_unlimited_user(email)
    if unlimited:
        return {
            "uid": uid,
            "email": email,
            "is_unlimited": True,
            "tier": "Founder (Lifetime Unlimited)",
            "quota_seconds": None,
            "used_seconds": 0,
            "remaining_seconds": None,
            "is_exhausted": False,
            "admin_contact": ADMIN_CONTACT_EMAIL
        }

    with _lock:
        data = _load_json(USAGE_FILE)
        user_record = data.get(uid, {})
        used_sec = int(user_record.get("used_seconds", 0))
        quota_sec = int(user_record.get("quota_seconds", DEFAULT_FREE_QUOTA_SECONDS))
        remaining_sec = max(0, quota_sec - used_sec)

        return {
            "uid": uid,
            "email": email or user_record.get("email", ""),
            "is_unlimited": False,
            "tier": "Standard Free Tier (1 Hour)",
            "quota_seconds": quota_sec,
            "used_seconds": used_sec,
            "remaining_seconds": remaining_sec,
            "is_exhausted": remaining_sec <= 0,
            "admin_contact": ADMIN_CONTACT_EMAIL
        }


def add_user_usage(uid: str, email: str, additional_seconds: int) -> dict:
    """
    Increments user's consumed recording seconds and persists to disk.
    If unlimited, returns success without deducting quota.
    """
    if additional_seconds <= 0:
        return get_user_usage(uid, email)

    unlimited = is_unlimited_user(email)
    if unlimited:
        return get_user_usage(uid, email)

    with _lock:
        data = _load_json(USAGE_FILE)
        user_record = data.get(uid, {
            "email": email,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "used_seconds": 0,
            "quota_seconds": DEFAULT_FREE_QUOTA_SECONDS
        })

        current_used = int(user_record.get("used_seconds", 0))
        new_used = current_used + additional_seconds
        user_record["used_seconds"] = new_used
        user_record["email"] = email or user_record.get("email", "")
        user_record["last_active"] = datetime.now(timezone.utc).isoformat()
        
        data[uid] = user_record
        _save_json(USAGE_FILE, data)

        quota_sec = int(user_record.get("quota_seconds", DEFAULT_FREE_QUOTA_SECONDS))
        remaining_sec = max(0, quota_sec - new_used)

        return {
            "uid": uid,
            "email": email,
            "is_unlimited": False,
            "tier": "Standard Free Tier (1 Hour)",
            "quota_seconds": quota_sec,
            "used_seconds": new_used,
            "remaining_seconds": remaining_sec,
            "is_exhausted": remaining_sec <= 0,
            "admin_contact": ADMIN_CONTACT_EMAIL
        }


def save_capacity_request(uid: str, email: str, message: str) -> dict:
    """Logs a user's request for additional recording capacity."""
    with _lock:
        data = _load_json(REQUESTS_FILE)
        requests_list = data.get("requests", [])
        new_entry = {
            "uid": uid,
            "email": email,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        requests_list.append(new_entry)
        data["requests"] = requests_list
        _save_json(REQUESTS_FILE, data)

    return {
        "success": True,
        "message": f"Your request has been forwarded to Sophie ({ADMIN_CONTACT_EMAIL}). We will review and upgrade your quota shortly!",
        "admin_contact": ADMIN_CONTACT_EMAIL
    }
