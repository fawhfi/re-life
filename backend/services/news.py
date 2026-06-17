"""新闻服务"""
import time
import httpx
from core.config import SERPAPI_KEY

# 缓存
_news_cache = {"data": [], "fetched_at": 0}

# 后备新闻
_FALLBACK_NEWS = [
    {"title": "Global push for plastic treaty gains momentum", "source": "Reuters", "link": "", "snippet": "UN members advance negotiations on legally binding plastic pollution treaty."},
    {"title": "New recycling technology triples plastic recovery rate", "source": "BBC News", "link": "", "snippet": "AI-powered sorting system can identify and separate 12 types of plastic."},
    {"title": "HK expands GREEN@COMMUNITY recycling network", "source": "SCMP", "link": "", "snippet": "11 new collection points added across Kowloon and New Territories."},
    {"title": "Global temperatures set to break records again in 2026", "source": "The Guardian", "link": "", "snippet": "Scientists warn of accelerating climate impacts as emissions continue to rise."},
    {"title": "Ocean cleanup removes 100,000kg of plastic", "source": "CNN", "link": "", "snippet": "Largest single extraction in the project's history achieved this month."},
]

async def get_news_cached() -> list[dict]:
    """获取新闻（带缓存）"""
    global _news_cache

    # 检查缓存（24小时）
    now = time.time()
    if _news_cache["fetched_at"] > now - 86400 and _news_cache["data"]:
        return _news_cache["data"]

    # 如果没有 API key，返回缓存或后备
    if not SERPAPI_KEY:
        return _news_cache["data"] if _news_cache["data"] else _FALLBACK_NEWS

    # 获取新闻
    try:
        query = "environmental+protection+climate+recycling+sustainability"
        url = f"https://serpapi.com/search?engine=google_news&q={query}&hl=en&gl=hk&api_key={SERPAPI_KEY}"

        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(url)
            res.raise_for_status()

        data = res.json()
        results = data.get("news_results", [])

        items = []
        for r in results[:8]:
            items.append({
                "title": r.get("title", ""),
                "source": r.get("source", {}).get("name", "Google News") if isinstance(r.get("source"), dict) else "Google News",
                "link": r.get("link", ""),
                "snippet": r.get("snippet", "")[:120] if r.get("snippet") else "",
            })

        if items:
            _news_cache = {"data": items, "fetched_at": now}
            return items
    except Exception as e:
        print(f"[News] Fetch failed: {e}")

    # 失败时返回缓存或后备
    return _news_cache["data"] if _news_cache["data"] else _FALLBACK_NEWS
