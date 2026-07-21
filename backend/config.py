"""Re-Life configuration — env vars and runtime constants."""
import os
from email.utils import parseaddr


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").strip().lower() in {"1", "true", "yes", "on"}


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
if APP_ENV not in {"development", "production"}:
    raise RuntimeError(
        f"Invalid APP_ENV {APP_ENV!r}; expected 'development' or 'production'"
    )
IS_DEVELOPMENT = APP_ENV == "development"
IS_PRODUCTION = APP_ENV == "production"
ALLOW_DEV_AUTH_CODES = IS_DEVELOPMENT and _env_bool("ALLOW_DEV_AUTH_CODES")
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "rel_session").strip() or "rel_session"
SESSION_IDLE_DAYS = max(1, int(os.getenv("SESSION_IDLE_DAYS", "30")))
SESSION_IDLE_SECONDS = SESSION_IDLE_DAYS * 24 * 60 * 60
SESSION_TOUCH_INTERVAL_SECONDS = max(60, int(os.getenv("SESSION_TOUCH_INTERVAL_SECONDS", "900")))
SESSION_CLOCK_SKEW_SECONDS = max(0, int(os.getenv("SESSION_CLOCK_SKEW_SECONDS", "300")))
# The database trigger independently enforces the same absolute ceiling.
SESSION_MAX_PER_USER = min(10, max(1, int(os.getenv("SESSION_MAX_PER_USER", "10"))))
SESSION_METADATA_HASH_KEY = os.getenv("SESSION_METADATA_HASH_KEY", "").strip()
if IS_DEVELOPMENT and not SESSION_METADATA_HASH_KEY:
    SESSION_METADATA_HASH_KEY = "development-only-session-metadata-key"
if IS_PRODUCTION:
    if len(SESSION_METADATA_HASH_KEY) < 32:
        raise RuntimeError(
            "SESSION_METADATA_HASH_KEY must be at least 32 characters in production"
        )
    supabase_keys = {
        value
        for name in (
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_PUBLISHABLE_KEY",
        )
        if (value := os.getenv(name, "").strip())
    }
    if SESSION_METADATA_HASH_KEY in supabase_keys:
        raise RuntimeError(
            "SESSION_METADATA_HASH_KEY must be independent from Supabase keys"
        )

# ── Multi-model AI ──────────────────────────────────────────────────────────
NVIDIA_API_KEY   = os.getenv("NVIDIA_API", "")
NVIDIA_MODEL     = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", os.getenv("OPENAI_API", ""))
OPENAI_MODEL     = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AGENT_MODEL      = os.getenv("AGENT_MODEL", "gpt-5.6").strip() or "gpt-5.6"
AGENT_MEMORY_MODEL = os.getenv("AGENT_MEMORY_MODEL", AGENT_MODEL).strip() or AGENT_MODEL
AGENT_BASE_URL   = os.getenv("AGENT_BASE_URL", "").strip()
_AGENT_API_KEY   = os.getenv("AGENT_API_KEY", "").strip()
# Never forward an OpenAI key to a third-party endpoint by implicit fallback.
AGENT_API_KEY    = _AGENT_API_KEY or ("" if AGENT_BASE_URL else OPENAI_API_KEY)
AGENT_API_MODE   = os.getenv("AGENT_API_MODE", "auto").strip().lower() or "auto"
if AGENT_API_MODE not in {"auto", "responses", "chat_completions"}:
    raise RuntimeError(
        "Invalid AGENT_API_MODE; expected 'auto', 'responses', or 'chat_completions'"
    )
AGENT_SESSION_TTL_SECONDS = max(300, int(os.getenv("AGENT_SESSION_TTL_SECONDS", "1800")))
AGENT_LOCAL_FALLBACK_ENABLED = _env_bool("AGENT_LOCAL_FALLBACK_ENABLED", True)
REMOTE_MODEL_MAX_CONCURRENCY = min(
    32,
    max(1, int(os.getenv("REMOTE_MODEL_MAX_CONCURRENCY", "1"))),
)
REMOTE_MODEL_MAX_QUEUE = min(
    256,
    max(0, int(os.getenv("REMOTE_MODEL_MAX_QUEUE", "8"))),
)
REMOTE_MODEL_QUEUE_TIMEOUT_SECONDS = min(
    300.0,
    max(0.1, float(os.getenv("REMOTE_MODEL_QUEUE_TIMEOUT_SECONDS", "5"))),
)
NVIDIA_INTEGRATE_BASE_URL = "https://integrate.api.nvidia.com/v1"
AGENT_GUARD_MODEL = os.getenv("AGENT_GUARD_MODEL", "").strip()
AGENT_GUARD_BASE_URL = (
    os.getenv("AGENT_GUARD_BASE_URL", NVIDIA_INTEGRATE_BASE_URL).strip().rstrip("/")
    or NVIDIA_INTEGRATE_BASE_URL
)
_AGENT_GUARD_API_KEY = os.getenv("AGENT_GUARD_API_KEY", "").strip()
# Never forward an NVIDIA key to a custom guard endpoint by implicit fallback.
AGENT_GUARD_API_KEY = _AGENT_GUARD_API_KEY or (
    NVIDIA_API_KEY
    if AGENT_GUARD_BASE_URL.lower() == NVIDIA_INTEGRATE_BASE_URL
    else ""
)
AGENT_GUARD_TIMEOUT_SECONDS = min(
    30.0,
    max(1.0, float(os.getenv("AGENT_GUARD_TIMEOUT_SECONDS", "8"))),
)
GEMINI_API_KEY   = os.getenv("GEMINI_API", "")
GEMINI_MODEL     = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API", "")
CLAUDE_API_KEY   = os.getenv("CLAUDE_API", "")
CLAUDE_MODEL     = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
CUSTOM_MODEL     = os.getenv("CUSTOM_ENDPOINT_MODEL", "")
CUSTOM_BASE_URL  = os.getenv("CUSTOM_BASE_URL", "")
CUSTOM_API_KEY   = os.getenv("CUSTOM_API", "")
CUSTOM_METHOD    = os.getenv("CUSTOM_ENDPOINT_METHOD", "openai")

AVAILABLE_MODELS = []
if NVIDIA_API_KEY:   AVAILABLE_MODELS.append("nvidia")
if OPENAI_API_KEY:   AVAILABLE_MODELS.append("openai")
if GEMINI_API_KEY:   AVAILABLE_MODELS.append("gemini")
if DEEPSEEK_API_KEY:  AVAILABLE_MODELS.append("deepseek")
if CLAUDE_API_KEY:    AVAILABLE_MODELS.append("claude")
if CUSTOM_API_KEY and CUSTOM_BASE_URL and CUSTOM_MODEL:
    AVAILABLE_MODELS.append("custom")
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
).strip()
UPSTASH_REDIS_REST_TOKEN = (
    os.getenv("UPSTASH_REDIS_REST_TOKEN")
    or os.getenv("KV_REST_API_TOKEN")
    or os.getenv("VERCEL_KV_REST_API_TOKEN")
    or ""
).strip()
REDIS_URL = os.getenv("REDIS_URL", os.getenv("KV_URL", "")).strip()

# ── Email ───────────────────────────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "Re-Life <noreply@yourdomain.com>").strip()
AUTH_CODE_SECRET = os.getenv("AUTH_CODE_SECRET", "").strip()
if IS_DEVELOPMENT and not AUTH_CODE_SECRET:
    AUTH_CODE_SECRET = "development-only-auth-code-secret"
VERIFICATION_CODE_EXPIRY_SECONDS = max(
    60,
    int(os.getenv("VERIFICATION_CODE_EXPIRY_SECONDS", "600")),
)
VERIFICATION_CODE_EXPIRY = VERIFICATION_CODE_EXPIRY_SECONDS
AUTH_CODE_MAX_ATTEMPTS = min(
    5,
    max(1, int(os.getenv("AUTH_CODE_MAX_ATTEMPTS", "5"))),
)


def validate_auth_security_settings() -> None:
    """Reject unsafe production email-auth configuration."""
    if not IS_PRODUCTION:
        return
    if len(AUTH_CODE_SECRET) < 32:
        raise RuntimeError(
            "AUTH_CODE_SECRET must be at least 32 characters in production"
        )

    independent_secrets = {
        value
        for value in (
            SESSION_METADATA_HASH_KEY,
            SUPABASE_SECRET_KEY,
            SUPABASE_SERVICE_ROLE_KEY,
            SUPABASE_ANON_KEY,
            SUPABASE_PUBLISHABLE_KEY,
        )
        if value
    }
    if AUTH_CODE_SECRET in independent_secrets:
        raise RuntimeError(
            "AUTH_CODE_SECRET must be independent from session and Supabase keys"
        )
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is required in production")

    display_name, sender_address = parseaddr(RESEND_FROM)
    local_part, separator, domain = sender_address.lower().partition("@")
    placeholder_domains = {
        "yourdomain.com",
        "example.com",
        "example.org",
        "example.net",
    }
    if (
        not separator
        or not local_part
        or "." not in domain
        or domain in placeholder_domains
        or domain.startswith("your")
        or ("<" in RESEND_FROM and not display_name)
    ):
        raise RuntimeError(
            "RESEND_FROM must be a valid, non-placeholder sender address in production"
        )

    if bool(UPSTASH_REDIS_REST_URL) != bool(UPSTASH_REDIS_REST_TOKEN):
        raise RuntimeError(
            "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must be configured together"
        )
    if not (
        (UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN)
        or REDIS_URL
    ):
        raise RuntimeError(
            "A durable rate-limit backend is required in production"
        )

# ── Upload ──────────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "scan-images")

# ── SerpAPI ─────────────────────────────────────────────────────────────────
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
