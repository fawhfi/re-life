"""Re-Life configuration — env vars, constants, Firebase config."""
import os
from pathlib import Path

root_dir = Path(__file__).parent

# ── Multi-model AI ──────────────────────────────────────────────────────────
NVIDIA_API_KEY   = os.getenv("NVIDIA_API", "")
NVIDIA_MODEL     = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
OPENAI_API_KEY   = os.getenv("OPENAI_API", "")
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY   = os.getenv("GEMINI_API", "")
GEMINI_MODEL     = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API", "")
CLAUDE_API_KEY   = os.getenv("CLAUDE_API", "")

AVAILABLE_MODELS = []
if NVIDIA_API_KEY:   AVAILABLE_MODELS.append("nvidia")
if OPENAI_API_KEY:   AVAILABLE_MODELS.append("openai")
if GEMINI_API_KEY:   AVAILABLE_MODELS.append("gemini")
if DEEPSEEK_API_KEY:  AVAILABLE_MODELS.append("deepseek")
if CLAUDE_API_KEY:    AVAILABLE_MODELS.append("claude")
if not AVAILABLE_MODELS:
    AVAILABLE_MODELS.append("nvidia")

DEFAULT_AI_MODEL = os.getenv("DEFAULT_AI_MODEL", AVAILABLE_MODELS[0] if AVAILABLE_MODELS else "nvidia")

# ── Firebase ────────────────────────────────────────────────────────────────
def get_firebase_config() -> dict[str, str]:
    return {
        "apiKey": os.getenv("FIREBASE_API_KEY", ""),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
        "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId": os.getenv("FIREBASE_APP_ID", ""),
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL", ""),
    }


FIREBASE_CONFIG = get_firebase_config()
FIREBASE_DB_URL = FIREBASE_CONFIG.get("databaseURL", "")

# ── Email ───────────────────────────────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
VERIFICATION_CODE_EXPIRY = 300

# ── Upload ──────────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

# ── SerpAPI ─────────────────────────────────────────────────────────────────
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
