"""
SoMeet Web - User Quota & Whitelist Tracking Service
Manages private beta access for up to 20 community testers:
- 120 minutes (7,200 seconds) free AI speech transcription & executive summaries
- Valid for 90 days from activation date (whichever comes first)
- Option A: Whitelist mode (unapproved accounts see private beta notice to DM Sophie on LinkedIn)
- Sophie's accounts remain Founder (Lifetime Unlimited)
"""
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

USAGE_FILE = DATA_DIR / "user_usage.json"
REQUESTS_FILE = DATA_DIR / "capacity_requests.json"
WHITELIST_FILE = DATA_DIR / "whitelist.json"

DEFAULT_FREE_QUOTA_SECONDS = 7200  # 120 minutes (2 hours)
DEFAULT_VALIDITY_DAYS = 90
MAX_BETA_TESTER_SLOTS = 20
LINKEDIN_URL = "https://www.linkedin.com/in/sophie-xu-cpa/"
ADMIN_CONTACT_EMAIL = "sophiexuxlx@gmail.com"

UNLIMITED_ADMIN_EMAILS = {
    "sophiexuxlx@gmail.com",
    "xusophiexiaoxiao@gmail.com"
}

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


def get_whitelist_data() -> dict:
    """Loads whitelist configuration from data/whitelist.json, creating initial defaults if missing."""
    with _lock:
        data = _load_json(WHITELIST_FILE)
        if not data:
            data = {
                "max_slots": MAX_BETA_TESTER_SLOTS,
                "whitelist": {
                    "sophiexuxlx@gmail.com": {
                        "name": "Sophie Xu",
                        "notes": "Founder",
                        "unlimited": True,
                        "added_at": datetime.now(timezone.utc).isoformat()
                    },
                    "xusophiexiaoxiao@gmail.com": {
                        "name": "Sophie Xu",
                        "notes": "Founder",
                        "unlimited": True,
                        "added_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            }
            _save_json(WHITELIST_FILE, data)
        return data


def is_user_whitelisted(email: str) -> tuple[bool, dict]:
    """
    Checks if user is whitelisted or founder.
    Returns (is_whitelisted, entry_metadata).
    """
    if not email:
        return False, {}
    clean_email = email.strip().lower()
    if is_unlimited_user(clean_email):
        return True, {"unlimited": True, "notes": "Founder"}

    wl_data = get_whitelist_data()
    whitelist_map = wl_data.get("whitelist", {})
    for key_email, meta in whitelist_map.items():
        if key_email.strip().lower() == clean_email:
            return True, meta

    return False, {}


def add_to_whitelist(email: str, name: str = "", notes: str = "", quota_seconds: int = DEFAULT_FREE_QUOTA_SECONDS) -> dict:
    """Adds or updates an approved tester email in whitelist.json."""
    if not email:
        return {"success": False, "error": "Email is required"}
    clean_email = email.strip().lower()

    with _lock:
        wl_data = _load_json(WHITELIST_FILE) or {"max_slots": MAX_BETA_TESTER_SLOTS, "whitelist": {}}
        whitelist_map = wl_data.setdefault("whitelist", {})
        whitelist_map[clean_email] = {
            "name": name,
            "notes": notes,
            "quota_seconds": quota_seconds,
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        _save_json(WHITELIST_FILE, wl_data)
    return {"success": True, "email": clean_email, "slots_used": len(whitelist_map)}


def get_user_usage(uid: str, email: str) -> dict:
    """
    Returns user tier, whitelist status, quota, remaining seconds, and days remaining.
    """
    clean_email = (email or "").strip().lower()
    unlimited = is_unlimited_user(clean_email)
    if unlimited:
        return {
            "uid": uid,
            "email": clean_email,
            "is_unlimited": True,
            "is_whitelisted": True,
            "tier": "Founder (Lifetime Unlimited)",
            "quota_seconds": None,
            "used_seconds": 0,
            "remaining_seconds": None,
            "days_remaining": None,
            "is_expired": False,
            "is_exhausted": False,
            "linkedin_url": LINKEDIN_URL,
            "admin_contact": ADMIN_CONTACT_EMAIL
        }

    whitelisted, meta = is_user_whitelisted(clean_email)
    if not whitelisted:
        return {
            "uid": uid,
            "email": clean_email,
            "is_unlimited": False,
            "is_whitelisted": False,
            "tier": "Private Beta (Invite Required)",
            "quota_seconds": 0,
            "used_seconds": 0,
            "remaining_seconds": 0,
            "days_remaining": 0,
            "is_expired": False,
            "is_exhausted": True,
            "linkedin_url": LINKEDIN_URL,
            "admin_contact": ADMIN_CONTACT_EMAIL,
            "message": "SoMeet is currently in private beta for 20 community testers. DM Sophie on LinkedIn to get an invite!"
        }

    # Calculate 90-day expiry
    added_at_str = meta.get("added_at")
    days_remaining = DEFAULT_VALIDITY_DAYS
    is_expired = False
    if added_at_str:
        try:
            added_at = datetime.fromisoformat(added_at_str.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - added_at).days
            days_remaining = max(0, DEFAULT_VALIDITY_DAYS - elapsed)
            if days_remaining <= 0:
                is_expired = True
        except Exception as e:
            print(f"[UsageService] Error parsing added_at {added_at_str}: {e}")

    with _lock:
        data = _load_json(USAGE_FILE)
        user_record = data.get(uid, {})
        used_sec = int(user_record.get("used_seconds", 0))
        quota_sec = int(meta.get("quota_seconds") or user_record.get("quota_seconds", DEFAULT_FREE_QUOTA_SECONDS))
        remaining_sec = 0 if is_expired else max(0, quota_sec - used_sec)

        return {
            "uid": uid,
            "email": clean_email or user_record.get("email", ""),
            "is_unlimited": False,
            "is_whitelisted": True,
            "tier": "Community Beta Tester (120 Minutes / 90 Days)",
            "quota_seconds": quota_sec,
            "used_seconds": used_sec,
            "remaining_seconds": remaining_sec,
            "days_remaining": days_remaining,
            "is_expired": is_expired,
            "is_exhausted": remaining_sec <= 0 or is_expired,
            "linkedin_url": LINKEDIN_URL,
            "admin_contact": ADMIN_CONTACT_EMAIL
        }


def add_user_usage(uid: str, email: str, additional_seconds: int) -> dict:
    """
    Increments user's consumed recording seconds and persists to disk.
    If unlimited, returns success without deducting quota.
    """
    if additional_seconds <= 0:
        return get_user_usage(uid, email)

    clean_email = (email or "").strip().lower()
    if is_unlimited_user(clean_email):
        return get_user_usage(uid, email)

    whitelisted, meta = is_user_whitelisted(clean_email)
    if not whitelisted:
        return get_user_usage(uid, email)

    with _lock:
        data = _load_json(USAGE_FILE)
        user_record = data.get(uid, {
            "email": clean_email,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "used_seconds": 0,
            "quota_seconds": meta.get("quota_seconds", DEFAULT_FREE_QUOTA_SECONDS)
        })

        current_used = int(user_record.get("used_seconds", 0))
        new_used = current_used + additional_seconds
        user_record["used_seconds"] = new_used
        user_record["email"] = clean_email or user_record.get("email", "")
        user_record["last_active"] = datetime.now(timezone.utc).isoformat()
        
        data[uid] = user_record
        _save_json(USAGE_FILE, data)

    return get_user_usage(uid, email)


def save_capacity_request(uid: str, email: str, message: str) -> dict:
    """Logs a user's request for additional recording capacity or beta invite."""
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
        "message": f"Your invite or expansion request has been forwarded to Sophie ({ADMIN_CONTACT_EMAIL}). You can also reach out directly via LinkedIn ({LINKEDIN_URL})!",
        "admin_contact": ADMIN_CONTACT_EMAIL,
        "linkedin_url": LINKEDIN_URL
    }


def get_all_capacity_requests() -> list:
    """Returns all tester requests, sorted newest first."""
    with _lock:
        data = _load_json(REQUESTS_FILE)
        reqs = data.get("requests", [])
        return sorted(reqs, key=lambda x: x.get("timestamp", ""), reverse=True)


def delete_capacity_request(timestamp: str) -> dict:
    """Removes a processed tester request by timestamp."""
    with _lock:
        data = _load_json(REQUESTS_FILE)
        reqs = data.get("requests", [])
        data["requests"] = [r for r in reqs if r.get("timestamp") != timestamp]
        _save_json(REQUESTS_FILE, data)
    return {"success": True}

