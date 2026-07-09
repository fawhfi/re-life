"""Re-Life data — news cache and user records."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import re
import time
import uuid

import httpx

from auth import get_user_by_id, get_user_by_name
from config import NEWS_API_KEY, SUPABASE_STORAGE_BUCKET, SUPABASE_URL
from scoring import CRITERIA_LABELS, HK_DISPOSAL, REWARDS_CATALOG, SCHEMA_WEIGHTS, calc_weighted, get_grade
from storage import (
    normalize_supabase_storage_url,
    supabase_delete,
    supabase_enabled,
    supabase_insert,
    supabase_select,
    supabase_select_one,
    supabase_storage_signed_url,
    supabase_storage_upload,
    supabase_update,
)


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
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[-\w.+/]+);base64,(?P<data>.+)$", re.DOTALL)


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


def _image_extension_for_mime(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get((mime or "").lower(), ".jpg")


def _image_data_url(contents: bytes, mime: str) -> str:
    b64 = base64.b64encode(contents).decode()
    return f"data:{mime or 'image/jpeg'};base64,{b64}"


async def persist_record_image(contents: bytes, filename: str, content_type: str | None = None) -> str:
    mime = (content_type or "").split(";", 1)[0].lower() or "image/jpeg"
    if not (supabase_enabled() and SUPABASE_STORAGE_BUCKET and SUPABASE_URL):
        return _image_data_url(contents, mime)

    ext = _image_extension_for_mime(mime)
    path = f"scan-records/{uuid.uuid4()}{ext}"
    await supabase_storage_upload(
        SUPABASE_STORAGE_BUCKET,
        path,
        contents,
        mime,
    )
    bucket = SUPABASE_STORAGE_BUCKET.strip("/")
    return supabase_storage_signed_url(bucket, path)


async def _persist_record_image_url(image_url: str | None) -> str:
    if not image_url or not isinstance(image_url, str):
        return ""
    match = _DATA_URL_RE.match(image_url.strip())
    if not match:
        return image_url
    if not (supabase_enabled() and SUPABASE_STORAGE_BUCKET and SUPABASE_URL):
        return image_url

    mime = match.group("mime").lower()
    try:
        contents = base64.b64decode(match.group("data"), validate=True)
    except (binascii.Error, ValueError):
        return image_url

    ext = _image_extension_for_mime(mime)
    return await persist_record_image(contents, f"record{ext}", mime)


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
    """Fetch environmental news via NewsAPI, cached in Supabase or memory."""
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

    if not NEWS_API_KEY:
        if supabase_enabled():
            if cache and cache.get("data"):
                return cache["data"]
        elif cache and cache.get("data"):
            return cache["data"]
        return _FALLBACK_NEWS

    query = '(recycling OR sustainability OR climate OR "environmental protection") AND "Hong Kong"'
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                "https://newsapi.org/v2/everything",
                headers={"X-Api-Key": NEWS_API_KEY},
                params={
                    "q": query,
                    "searchIn": "title,description",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 8,
                },
            )
            res.raise_for_status()
        data = res.json()
        if data.get("status") == "error":
            raise RuntimeError(data.get("message") or "NewsAPI request failed")
        results = data.get("articles", [])
        items = []
        for r in results[:8]:
            items.append({
                "title": r.get("title", ""),
                "source": r.get("source", {}).get("name", "NewsAPI") if isinstance(r.get("source"), dict) else "NewsAPI",
                "link": r.get("url", ""),
                "snippet": (r.get("description") or r.get("content") or "")[:120],
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
    image_url = await _persist_record_image_url(item.get("image_url") or item.get("photoUrl") or "")
    record = {
        "user_id": owner_id,
        "mode": item.get("mode") or item.get("status") or "dispose",
        "name": item.get("name") or "Scanned Item",
        "description": item.get("description") or "",
        "image_url": image_url,
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
