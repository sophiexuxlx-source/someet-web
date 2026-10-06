"""
VoiceFlow Web - Server Configuration
"""
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# External env paths to check for Gemini API key
EXTERNAL_ENV_PATH = Path(r"C:\AI Builder & AI Architect\AI Study\AI Architect\1_SuperMind_Core_Engine\.env")
LOCAL_ENV_PATH = BASE_DIR / ".env"


def load_env_file(path: Path) -> dict:
    env_vars = {}
    if not path.exists():
        return env_vars
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if re.search(r"gemini.*key", line, re.IGNORECASE):
                if ":" in line:
                    env_vars["GEMINI_API_KEY"] = line.split(":", 1)[1].strip().strip("'\"")
                elif "=" in line:
                    env_vars["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip("'\"")
            elif "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip("'\"")
    except Exception as e:
        print(f"[Config] Error reading {path}: {e}")
    return env_vars


_env = {}
_env.update(load_env_file(EXTERNAL_ENV_PATH))
_env.update(load_env_file(LOCAL_ENV_PATH))
_env.update(os.environ)

GEMINI_API_KEY = _env.get("GEMINI_API_KEY", "")
FIREBASE_PROJECT_ID = _env.get("FIREBASE_PROJECT_ID", "voiceflow-app")
HOST = _env.get("HOST", "0.0.0.0")
PORT = int(_env.get("PORT", 8000))
