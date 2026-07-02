"""Re-Life data — scoring, rewards, schemas, disposal guides, news, records."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import random
import time
from typing import Any

import httpx

from auth import get_user_by_id, get_user_by_name
from config import SERPAPI_KEY
from storage import (
    normalize_supabase_storage_url,
    supabase_delete,
    supabase_enabled,
    supabase_insert,
    supabase_select,
    supabase_select_one,
    supabase_update,
)

# ── Scoring Engine ──────────────────────────────────────────────────────────

SCHEMA_WEIGHTS = {
    "food_new": {"a": 0.30, "b": 0.25, "c": 0.20, "d": 0.15, "e": 0.10},
    "food_expire": {"a": 0.20, "b": 0.20, "c": 0.25, "d": 0.20, "e": 0.15},
    "item_new": {"a": 0.25, "b": 0.35, "c": 0.10, "d": 0.20, "e": 0.10},
    "item_expire": {"a": 0.25, "b": 0.30, "c": 0.10, "d": 0.25, "e": 0.10},
}

CRITERIA_LABELS = {
    "food_new": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recyclability", "e": "Food Preservation"},
    "food_expire": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Safety & Waste Prevention"},
    "item_new": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Social & Innovation"},
    "item_expire": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Reuse Potential"},
}

HK_DISPOSAL = {
    "plastic": {"type": "Plastic (PET/HDPE)", "method": "Rinse clean, flatten", "location": "Tri-colour recycling bins, GREEN@COMMUNITY"},
    "pp_plastic": {"type": "Other Plastic / PP", "method": "Rinse clean, disassemble parts", "location": "GREEN@COMMUNITY"},
    "paper": {"type": "Paper / Cardboard", "method": "Keep dry, no grease, flatten", "location": "Blue paper recycling bins"},
    "metal": {"type": "Metal Cans", "method": "Rinse clean, flatten", "location": "Metal recycling bins"},
    "glass": {"type": "Glass Bottles", "method": "Rinse clean, remove caps", "location": "Government glass recycling points"},
    "compostable": {"type": "Compostable", "method": "Do NOT place in regular recycling", "location": "Industrial/home composting programs"},
    "wood": {"type": "Wood / Bulky Waste", "method": "Remove metal fittings, compress", "location": "LCSD collection points or private recyclers"},
}


def calc_weighted(scores, sid):
    w = SCHEMA_WEIGHTS.get(sid, SCHEMA_WEIGHTS["food_new"])
    return round(sum(scores.get(k, 50) * w[k] for k in w))


def get_grade(score):
    if score >= 85:
        return {"grade": "Excellent (A)", "advice": "Highly Recommended", "color": "#065f46"}
    if score >= 70:
        return {"grade": "Good (B)", "advice": "Acceptable", "color": "#047857"}
    if score >= 55:
        return {"grade": "Fair (C)", "advice": "Consider Alternatives", "color": "#ca8a04"}
    if score >= 40:
        return {"grade": "Poor (D)", "advice": "Avoid if Possible", "color": "#b45309"}
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

_memory_news_cache: dict[str, dict] = {}
_memory_records_by_id: dict[int, dict] = {}
_memory_record_seq = 1
NEWS_CACHE_KEY = "hk_green_news"


def _parse_iso(value) -> float:
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    return 0.0


def _hk_today_6am() -> float:
    now = time.time()
    return now - ((now - 8 * 3600) % 86400) + 6 * 3600 + 8 * 3600


def _normalize_record_row(row: dict | None, user_name: str | None = None) -> dict | None:
    if not row:
        return None
    photo_url = normalize_supabase_storage_url(row.get("image_url") or row.get("photo_url"))
    overall_score = int(row.get("overall_score") or row.get("overallScore") or 0)
    grade_info = get_grade(overall_score)
    grade = row.get("grade") or grade_info["grade"]
    grade_color = row.get("grade_color") or grade_info["color"]
    grade_advice = row.get("grade_advice") or grade_info["advice"]
    return {
        "id": row.get("id"),
        "name": row.get("name") or "Scanned Item",
        "status": row.get("mode") or row.get("status") or "dispose",
        "createdAt": row.get("created_at") or row.get("createdAt"),
        "description": row.get("description") or "",
        "photoUrl": photo_url,
        "photo_url": photo_url,
        "dealtWithMethod": row.get("dealt_with_method") or row.get("dealtWithMethod") or "",
        "dealtWithDate": row.get("dealt_with_date") or row.get("dealtWithDate"),
        "userId": row.get("user_id") or row.get("userId"),
        "userName": user_name or row.get("user_name") or row.get("userName"),
        "eco_rate": row.get("eco_rate") or 3,
        "recycle_rate": row.get("recycle_rate") or 4,
        "overall_score": overall_score,
        "material": row.get("material") or "",
        "grade": grade,
        "grade_color": grade_color,
        "grade_advice": grade_advice,
        "brand": row.get("brand") or "",
        "category": row.get("category") or "",
        "weighted_scores": row.get("weighted_scores") or row.get("weightedScores") or {},
        "schema_id": row.get("schema_id") or row.get("schemaId") or "",
        "alternative": row.get("alternative"),
        "precaution": row.get("precaution"),
        "image_url": photo_url,
    }


def _memory_store_record(row: dict) -> dict:
    global _memory_record_seq
    if not row.get("id"):
        row["id"] = _memory_record_seq
        _memory_record_seq += 1
    row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    _memory_records_by_id[int(row["id"])] = row
    return row


async def _resolve_user_id(user_id=None, display_name=None, user_key=None) -> dict | None:
    if user_id is not None:
        user = await get_user_by_id(user_id)
        if user:
            return user
    if user_key is not None and user_key != user_id:
        user = await get_user_by_id(user_key)
        if user:
            return user
    if display_name:
        return await get_user_by_name(display_name)
    return None


async def get_news_cached(db_get=None, db_put=None) -> list[dict]:
    """Fetch environmental news via SerpAPI, cached in Supabase or memory."""
    if supabase_enabled():
        cache = await supabase_select_one("news_cache", filters={"cache_key": NEWS_CACHE_KEY})
        if cache and cache.get("data"):
            fetched_at = _parse_iso(cache.get("fetched_at"))
            if fetched_at > _hk_today_6am():
                return cache["data"]
    else:
        cache = _memory_news_cache.get(NEWS_CACHE_KEY)
        if cache and cache.get("data") and cache.get("fetched_at", 0) > _hk_today_6am():
            return cache["data"]

    if not SERPAPI_KEY:
        if supabase_enabled():
            if cache and cache.get("data"):
                return cache["data"]
        elif cache and cache.get("data"):
            return cache["data"]
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
            if supabase_enabled():
                if cache:
                    await supabase_update("news_cache", {"data": items, "fetched_at": datetime.now(timezone.utc).isoformat()}, filters={"cache_key": NEWS_CACHE_KEY})
                else:
                    await supabase_insert("news_cache", {"cache_key": NEWS_CACHE_KEY, "data": items, "fetched_at": datetime.now(timezone.utc).isoformat()}, returning=False)
            else:
                _memory_news_cache[NEWS_CACHE_KEY] = {"data": items, "fetched_at": time.time()}
            return items
        return _FALLBACK_NEWS
    except Exception:
        if supabase_enabled():
            cache = await supabase_select_one("news_cache", filters={"cache_key": NEWS_CACHE_KEY})
            if cache and cache.get("data"):
                return cache["data"]
        else:
            cache = _memory_news_cache.get(NEWS_CACHE_KEY)
            if cache and cache.get("data"):
                return cache["data"]
        return _FALLBACK_NEWS


async def add_item(item: dict) -> dict:
    owner = await _resolve_user_id(item.get("userId"), item.get("userName"), item.get("userKey"))
    if not owner:
        raise ValueError("Login required to save records")
    owner_id = owner["id"]
    record = {
        "user_id": owner_id,
        "mode": item.get("mode") or item.get("status") or "dispose",
        "name": item.get("name") or "Scanned Item",
        "description": item.get("description") or "",
        "image_url": item.get("image_url") or item.get("photoUrl") or "",
        "dealt_with_method": item.get("disposal_guide") or item.get("dealtWithMethod") or "",
        "eco_rate": int(item.get("eco_rate") or 3),
        "recycle_rate": int(item.get("recycle_rate") or 4),
        "overall_score": int(item.get("overall_score") or item.get("overallScore") or 50),
        "material": item.get("material") or "",
        "grade": item.get("grade") or "",
        "grade_color": item.get("grade_color"),
        "grade_advice": item.get("grade_advice"),
        "brand": item.get("brand") or "",
        "category": item.get("category") or "",
        "weighted_scores": item.get("weighted_scores") or item.get("weightedScores") or {},
        "schema_id": item.get("schema_id") or item.get("schemaId") or "",
        "alternative": item.get("alternative"),
        "precaution": item.get("precaution"),
    }

    if supabase_enabled():
        rows = await supabase_insert(
            "scan_records",
            {
                "user_id": record["user_id"],
                "mode": record["mode"],
                "name": record["name"],
                "description": record["description"],
                "image_url": record["image_url"],
                "dealt_with_method": record["dealt_with_method"],
                "eco_rate": record["eco_rate"],
                "recycle_rate": record["recycle_rate"],
                "overall_score": record["overall_score"],
                "material": record["material"],
                "grade": record["grade"],
                "brand": record["brand"],
                "category": record["category"],
                "weighted_scores": record["weighted_scores"],
                "schema_id": record["schema_id"],
                "alternative": record["alternative"],
                "precaution": record["precaution"],
            },
        )
        row = rows[0] if rows else None
        return {"id": row.get("id") if row else None}

    row = _memory_store_record(record)
    return {"id": row["id"]}


async def get_items(user_id=None, display_name=None, user_key=None) -> list[dict]:
    if not user_id and not display_name and not user_key:
        return []

    owner = await _resolve_user_id(user_id, display_name, user_key)
    if not owner:
        return []

    if supabase_enabled():
        rows = await supabase_select(
            "scan_records",
            order="created_at.desc",
            filters={"user_id": owner["id"]},
        )
        return [
            _normalize_record_row(row, owner.get("displayName"))
            for row in rows or []
        ]

    rows = [
        row for row in _memory_records_by_id.values()
        if int(row.get("user_id") or 0) == int(owner["id"])
    ]
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return [_normalize_record_row(row, owner.get("displayName")) for row in rows]


async def delete_item(item_id) -> None:
    if supabase_enabled():
        await supabase_delete("scan_records", filters={"id": item_id})
        return
    _memory_records_by_id.pop(int(item_id), None)


async def clear_all_items(user_id=None, display_name=None, user_key=None) -> None:
    owner = await _resolve_user_id(user_id, display_name, user_key)
    if not owner:
        return
    if supabase_enabled():
        await supabase_delete("scan_records", filters={"user_id": owner["id"]})
        return
    doomed = [rid for rid, row in _memory_records_by_id.items() if int(row.get("user_id") or 0) == int(owner["id"])]
    for rid in doomed:
        _memory_records_by_id.pop(rid, None)
