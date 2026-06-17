"""配置管理"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
root_dir = Path(__file__).parent.parent
env_path = root_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)

# ── AI 模型配置 ──
NVIDIA_API_KEY = os.getenv("NVIDIA_API", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
OPENAI_API_KEY = os.getenv("OPENAI_API", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY = os.getenv("GEMINI_API", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API", "")

# 可用模型列表
AVAILABLE_MODELS = []
if NVIDIA_API_KEY: AVAILABLE_MODELS.append("nvidia")
if OPENAI_API_KEY: AVAILABLE_MODELS.append("openai")
if GEMINI_API_KEY: AVAILABLE_MODELS.append("gemini")
if DEEPSEEK_API_KEY: AVAILABLE_MODELS.append("deepseek")
if CLAUDE_API_KEY: AVAILABLE_MODELS.append("claude")

DEFAULT_AI_MODEL = os.getenv("DEFAULT_AI_MODEL", AVAILABLE_MODELS[0] if AVAILABLE_MODELS else "nvidia")

# ── Firebase 配置 ──
FIREBASE_CONFIG = {
    "apiKey": os.getenv("FIREBASE_API_KEY", ""),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
    "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
    "appId": os.getenv("FIREBASE_APP_ID", ""),
    "databaseURL": os.getenv("FIREBASE_DATABASE_URL", ""),
}
FIREBASE_DB_URL = FIREBASE_CONFIG.get("databaseURL", "")

# ── SMTP 配置 ──
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
VERIFICATION_CODE_EXPIRY = 300  # 5 分钟

# ── SerpAPI 配置 ──
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")

# ── 上传限制 ──
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

# ── CORS 配置 ──
# 开发环境默认域名
CORS_ORIGINS_DEFAULT = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

# 从环境变量读取 CORS 域名（用逗号分隔）
# 生产环境示例: "https://relife-app.pages.dev,https://your-custom-domain.com"
CORS_ORIGINS = os.getenv("CORS_ORIGINS", CORS_ORIGINS_DEFAULT).split(",")

# 去除空白字符
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS if origin.strip()]

# ── 模型路径 ──
MODEL_PATH = root_dir / "models" / "model_INT8.onnx"
