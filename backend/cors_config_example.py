# 生产环境 CORS 配置示例
# 将此内容添加到 backend/core/config.py 中

# 开发环境
CORS_ORIGINS_DEV = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

# 生产环境 - 部署后需要更新这些域名
CORS_ORIGINS_PROD = [
    "https://relife-app.pages.dev",  # 👈 替换为你的 Cloudflare Pages 默认域名
    "https://your-custom-domain.com",  # 👈 如果有自定义域名，添加在这里
]

# 根据环境选择
import os
ENV = os.getenv("ENVIRONMENT", "development")
CORS_ORIGINS = CORS_ORIGINS_PROD if ENV == "production" else CORS_ORIGINS_DEV + CORS_ORIGINS_PROD
