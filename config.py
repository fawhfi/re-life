"""Re-Life configuration — env vars and runtime constants."""
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
CLAUDE_MODEL     = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")

AVAILABLE_MODELS = []
if NVIDIA_API_KEY:   AVAILABLE_MODELS.append("nvidia")
if OPENAI_API_KEY:   AVAILABLE_MODELS.append("openai")
if GEMINI_API_KEY:   AVAILABLE_MODELS.append("gemini")
if DEEPSEEK_API_KEY:  AVAILABLE_MODELS.append("deepseek")
if CLAUDE_API_KEY:    AVAILABLE_MODELS.append("claude")
if not AVAILABLE_MODELS:
    AVAILABLE_MODELS.append("nvidia")

DEFAULT_AI_MODEL = os.getenv("DEFAULT_AI_MODEL", AVAILABLE_MODELS[0] if AVAILABLE_MODELS else "nvidia")

# ── Supabase ────────────────────────────────────────────────────────────────
def get_public_config() -> dict[str, str]:
    return {
        "supabaseUrl": os.getenv("SUPABASE_URL", ""),
        "supabasePublishableKey": os.getenv("SUPABASE_PUBLISHABLE_KEY", os.getenv("SUPABASE_ANON_KEY", "")),
        "supabaseAnonKey": os.getenv("SUPABASE_ANON_KEY", os.getenv("SUPABASE_PUBLISHABLE_KEY", "")),
    }


PUBLIC_CONFIG = get_public_config()
SUPABASE_URL = PUBLIC_CONFIG.get("supabaseUrl", "")
SUPABASE_PUBLISHABLE_KEY = PUBLIC_CONFIG.get("supabasePublishableKey", "")
SUPABASE_ANON_KEY = PUBLIC_CONFIG.get("supabaseAnonKey", "")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
SUPABASE_SERVICE_ROLE_KEY = SUPABASE_SECRET_KEY
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")

# ── Vercel KV / Upstash Redis ───────────────────────────────────────────────
UPSTASH_REDIS_REST_URL = (
    os.getenv("UPSTASH_REDIS_REST_URL")
    or os.getenv("KV_REST_API_URL")
    or os.getenv("VERCEL_KV_REST_API_URL")
    or ""
)
UPSTASH_REDIS_REST_TOKEN = (
    os.getenv("UPSTASH_REDIS_REST_TOKEN")
    or os.getenv("KV_REST_API_TOKEN")
    or os.getenv("VERCEL_KV_REST_API_TOKEN")
    or ""
)
REDIS_URL = os.getenv("REDIS_URL", os.getenv("KV_URL", ""))

# ── Email ───────────────────────────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "Re-Life <noreply@yourdomain.com>")
VERIFICATION_CODE_EXPIRY = 300

# ── Upload ──────────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "scan-images")

# ── SerpAPI ─────────────────────────────────────────────────────────────────
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
