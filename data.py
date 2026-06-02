"""Re-Life data — scoring, rewards, schemas, disposal guides, news."""
import json, random, time, httpx
from config import SERPAPI_KEY, FIREBASE_DB_URL

# ── Scoring Engine ──────────────────────────────────────────────────────────

SCHEMA_WEIGHTS = {
    "food_new":    {"a": 0.30, "b": 0.25, "c": 0.20, "d": 0.15, "e": 0.10},
    "food_expire": {"a": 0.20, "b": 0.20, "c": 0.25, "d": 0.20, "e": 0.15},
    "item_new":    {"a": 0.25, "b": 0.35, "c": 0.10, "d": 0.20, "e": 0.10},
    "item_expire": {"a": 0.25, "b": 0.30, "c": 0.10, "d": 0.25, "e": 0.10},
}

CRITERIA_LABELS = {
    "food_new":    {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recyclability", "e": "Food Preservation"},
    "food_expire": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Safety & Waste Prevention"},
    "item_new":    {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Social & Innovation"},
    "item_expire": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Reuse Potential"},
}

HK_DISPOSAL = {
    "plastic":     {"type": "Plastic (PET/HDPE)", "method": "Rinse clean, flatten", "location": "Tri-colour recycling bins, GREEN@COMMUNITY"},
    "pp_plastic":  {"type": "Other Plastic / PP", "method": "Rinse clean, disassemble parts", "location": "GREEN@COMMUNITY"},
    "paper":       {"type": "Paper / Cardboard", "method": "Keep dry, no grease, flatten", "location": "Blue paper recycling bins"},
    "metal":       {"type": "Metal Cans", "method": "Rinse clean, flatten", "location": "Metal recycling bins"},
    "glass":       {"type": "Glass Bottles", "method": "Rinse clean, remove caps", "location": "Government glass recycling points"},
    "compostable": {"type": "Compostable", "method": "Do NOT place in regular recycling", "location": "Industrial/home composting programs"},
    "wood":        {"type": "Wood / Bulky Waste", "method": "Remove metal fittings, compress", "location": "LCSD collection points or private recyclers"},
}

def calc_weighted(scores, sid):
    w = SCHEMA_WEIGHTS.get(sid, SCHEMA_WEIGHTS["food_new"])
    return round(sum(scores.get(k, 50) * w[k] for k in w))

def get_grade(score):
    if score >= 85: return {"grade": "Excellent (A)", "advice": "Highly Recommended", "color": "#065f46"}
    if score >= 70: return {"grade": "Good (B)", "advice": "Acceptable", "color": "#047857"}
    if score >= 55: return {"grade": "Fair (C)", "advice": "Consider Alternatives", "color": "#ca8a04"}
    if score >= 40: return {"grade": "Poor (D)", "advice": "Avoid if Possible", "color": "#b45309"}
    return {"grade": "Very Poor (E)", "advice": "Strongly Discouraged", "color": "#dc2626"}

# ── Rewards ─────────────────────────────────────────────────────────────────

REWARDS_CATALOG = [
    {"id": "tree-plant", "title": "Plant a Native Tree in HK Country Park", "provider": "Tree Planting HK", "cost": 500, "image": "🌳", "category": "Environment", "description": "Sponsor planting a native sapling in Tai Lam or Sai Kung country park."},
    {"id": "fairprice-voucher", "title": "PARKnSHOP HK$30 Cash Voucher", "provider": "PARKnSHOP", "cost": 350, "image": "🎟️", "category": "Voucher", "description": "Valid at all PARKnSHOP, TASTE, and Fusion stores across Hong Kong."},
    {"id": "mtr-ride", "title": "MTR Single Journey Ticket", "provider": "MTR Corporation", "cost": 200, "image": "🚇", "category": "Transport", "description": "One free adult single journey on any MTR urban line."},
    {"id": "starbucks-treat", "title": "Starbucks HK$25 eGift", "provider": "Starbucks HK", "cost": 280, "image": "☕", "category": "Voucher", "description": "Redeemable for any handcrafted beverage at Starbucks Hong Kong."},
    {"id": "ocean-cleanup", "title": "Sponsor Ocean Cleanup (1kg)", "provider": "Ocean Recovery Alliance", "cost": 150, "image": "🌊", "category": "Environment", "description": "Fund the removal of 1kg of marine plastic from HK coastal waters."},
    {"id": "reusable-kit", "title": "Reusable Eco Starter Kit", "provider": "Green Store HK", "cost": 400, "image": "🎒", "category": "Product", "description": "Bamboo cutlery set, beeswax wrap, and organic cotton tote bag."},
]

# ── News ────────────────────────────────────────────────────────────────────

_FALLBACK_NEWS = [
    {"title": "Global push for plastic treaty gains momentum", "source": "Reuters", "link": "", "snippet": "UN members advance negotiations on legally binding plastic pollution treaty."},
    {"title": "New recycling technology triples plastic recovery rate", "source": "BBC News", "link": "", "snippet": "AI-powered sorting system can identify and separate 12 types of plastic."},
    {"title": "HK expands GREEN@COMMUNITY recycling network", "source": "SCMP", "link": "", "snippet": "11 new collection points added across Kowloon and New Territories."},
    {"title": "Global temperatures set to break records again in 2026", "source": "The Guardian", "link": "", "snippet": "Scientists warn of accelerating climate impacts as emissions continue to rise."},
    {"title": "Ocean cleanup removes 100,000kg of plastic from Great Pacific Garbage Patch", "source": "CNN", "link": "", "snippet": "Largest single extraction in the project's history achieved this month."},
]

async def get_news_cached(db_get, db_put) -> list[dict]:
    """Fetch environmental news via SerpAPI, cached for 24h in Firebase."""
    # Return cached if fresh (refreshes daily at 6am HK)
    if FIREBASE_DB_URL:
        cache = await db_get("news_cache")
        if cache and isinstance(cache, dict):
            cached_at = cache.get("fetched_at", 0)
            now = time.time()
            today_6am = now - ((now - 8 * 3600) % 86400) + 6 * 3600 + 8 * 3600
            if cached_at > today_6am:
                items = cache.get("data", [])
                if items:
                    return items

    if not SERPAPI_KEY:
        cached = await db_get("news_cache")
        if cached and isinstance(cached, dict) and cached.get("data"):
            return cached["data"]
        return _FALLBACK_NEWS

    query = "environmental+protection+climate+recycling+sustainability"
    url = f"https://serpapi.com/search?engine=google_news&q={query}&hl=en&gl=hk&api_key={SERPAPI_KEY}"
    try:
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
            await db_put("news_cache", {"data": items, "fetched_at": time.time()})
            return items
        return _FALLBACK_NEWS
    except Exception:
        cached = await db_get("news_cache")
        if cached and isinstance(cached, dict) and cached.get("data"):
            return cached["data"]
        return _FALLBACK_NEWS
