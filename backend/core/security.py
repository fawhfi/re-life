"""安全工具函数"""
import time
from collections import defaultdict
from fastapi import HTTPException, Request

# 简单的内存速率限制器
_rate_limit_store: dict[str, list[float]] = defaultdict(list)

async def check_rate_limit(
    request: Request,
    max_requests: int = 5,
    window_sec: int = 60
):
    """检查速率限制"""
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"

    # 结合 IP 和 User-Agent
    ua = (request.headers.get("user-agent", "") or "")[:64]
    fingerprint = f"{ip}|{ua}"
    route = request.url.path
    key = f"rl:{fingerprint}:{route}"

    now = time.time()
    cutoff = now - window_sec

    # 清理过期记录
    _rate_limit_store[key] = [t for t in _rate_limit_store.get(key, []) if t > cutoff]

    # 检查限制
    if len(_rate_limit_store[key]) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests — slow down")

    _rate_limit_store[key].append(now)
