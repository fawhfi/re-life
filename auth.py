"""Re-Life auth — email verification, password reset, rate limiting, user helpers."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
import hashlib
import hmac
import random
import time
import uuid

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from config import (
    REDIS_URL,
    RESEND_API_KEY,
    RESEND_FROM,
    UPSTASH_REDIS_REST_TOKEN,
    UPSTASH_REDIS_REST_URL,
    VERIFICATION_CODE_EXPIRY,
)
from storage import (
    supabase_delete,
    supabase_enabled,
    supabase_insert,
    supabase_select,
    supabase_select_one,
    supabase_update,
)

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)

_pending_verifications: dict[str, dict] = {}
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_memory_users_by_id: dict[int, dict] = {}
_memory_users_by_public_id: dict[str, dict] = {}
_memory_user_seq = 1
RESEND_API_URL = "https://api.resend.com/emails"
RESEND_USER_AGENT = "Re-Life/1.0"
KV_USER_AGENT = "Re-Life/1.0"
_redis_client = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(offset_seconds: int = 0) -> str:
    return (_utc_now() + timedelta(seconds=offset_seconds)).isoformat()


def _safe_list(value) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = __import__("json").loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _code_digest(purpose: str, email: str, code: str) -> str:
    payload = f"{purpose}:{email}:{code}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_user_row(row: dict | None) -> dict | None:
    if not row:
        return None
    claimed = _safe_list(row.get("claimed_coupons") or row.get("claimedCoupons"))
    display_name = row.get("display_name") or row.get("displayName") or ""
    public_id = row.get("public_id") or row.get("userId") or row.get("_key")
    result = {
        "id": row.get("id"),
        "public_id": public_id,
        "userId": public_id,
        "_key": public_id,
        "displayName": display_name,
        "display_name": display_name,
        "email": row.get("email"),
        "photoUrl": row.get("photo_url") or row.get("photoUrl"),
        "photo_url": row.get("photo_url") or row.get("photoUrl"),
        "spent_points": int(row.get("spent_points") or row.get("spentPoints") or 0),
        "spentPoints": int(row.get("spent_points") or row.get("spentPoints") or 0),
        "earned_points": int(row.get("earned_points") or row.get("earnedPoints") or 0),
        "earnedPoints": int(row.get("earned_points") or row.get("earnedPoints") or 0),
        "claimed_coupons": claimed,
        "claimedCoupons": claimed,
        "emailVerified": bool(row.get("email_verified") or row.get("emailVerified")),
        "createdAt": row.get("created_at") or row.get("createdAt"),
        "updatedAt": row.get("updated_at") or row.get("updatedAt"),
    }
    return result


def _memory_store_user(row: dict) -> dict:
    global _memory_user_seq
    if not row.get("id"):
        row["id"] = _memory_user_seq
        _memory_user_seq += 1
    if not row.get("public_id"):
        row["public_id"] = f"usr_{uuid.uuid4().hex[:12]}"
    row.setdefault("created_at", _utc_iso())
    row.setdefault("updated_at", row["created_at"])
    row.setdefault("claimed_coupons", [])
    row.setdefault("spent_points", 0)
    row.setdefault("earned_points", 0)
    _memory_users_by_id[int(row["id"])] = row
    _memory_users_by_public_id[str(row["public_id"])] = row
    return row


def _memory_find_user(identifier) -> dict | None:
    if identifier is None:
        return None
    if isinstance(identifier, dict):
        for key in ("id", "public_id", "userId", "displayName", "display_name"):
            if identifier.get(key):
                identifier = identifier.get(key)
                break
    if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
        row = _memory_users_by_id.get(int(identifier))
        if row:
            return row
    identifier = str(identifier)
    row = _memory_users_by_public_id.get(identifier)
    if row:
        return row
    for candidate in _memory_users_by_id.values():
        if candidate.get("display_name") == identifier or candidate.get("email") == identifier:
            return candidate
    return None


async def _resolve_user_row(identifier) -> dict | None:
    if not identifier and identifier != 0:
        return None
    if supabase_enabled():
        if isinstance(identifier, dict):
            for key in ("id", "public_id", "userId", "displayName", "display_name", "email"):
                if identifier.get(key):
                    identifier = identifier.get(key)
                    break
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            row = await supabase_select_one("app_users", filters={"id": int(identifier)})
            if row:
                return row
        identifier = str(identifier)
        for filters in (
            {"public_id": identifier},
            {"display_name": identifier},
            {"email": identifier},
        ):
            row = await supabase_select_one("app_users", filters=filters)
            if row:
                return row
        return None
    return _memory_find_user(identifier)


def _memory_store_code(purpose: str, email: str, code: str, *, user_id: int | None = None) -> dict:
    key = f"{purpose}:{email}"
    row = {
        "purpose": purpose,
        "email": email,
        "user_id": user_id,
        "code_hash": _code_digest(purpose, email, code),
        "expires_at": _utc_now().timestamp() + VERIFICATION_CODE_EXPIRY,
        "attempts": 0,
        "consumed_at": None,
    }
    _pending_verifications[key] = row
    return row


def _memory_get_code(purpose: str, email: str) -> dict | None:
    return _pending_verifications.get(f"{purpose}:{email}")


async def _store_code_row(purpose: str, email: str, code: str, *, user_id: int | None = None) -> None:
    if supabase_enabled():
        await supabase_delete("auth_codes", filters={"purpose": purpose, "email": email})
        await supabase_insert(
            "auth_codes",
            {
                "purpose": purpose,
                "email": email,
                "user_id": user_id,
                "code_hash": _code_digest(purpose, email, code),
                "expires_at": _utc_iso(VERIFICATION_CODE_EXPIRY),
                "attempts": 0,
                "consumed_at": None,
            },
            returning=False,
        )
        return
    _memory_store_code(purpose, email, code, user_id=user_id)


async def _fetch_code_row(purpose: str, email: str) -> dict | None:
    if supabase_enabled():
        return await supabase_select_one(
            "auth_codes",
            filters={"purpose": purpose, "email": email},
        )
    return _memory_get_code(purpose, email)


async def _delete_code_row(purpose: str, email: str) -> None:
    if supabase_enabled():
        await supabase_delete("auth_codes", filters={"purpose": purpose, "email": email})
        return
    _pending_verifications.pop(f"{purpose}:{email}", None)


async def _send_code_email(email: str, subject: str, intro: str, code: str) -> bool:
    if not RESEND_API_KEY:
        print("[Resend] RESEND_API_KEY missing; email not sent, returning dev_code fallback")
        return False

    text = f"{intro}\n\nVerification code: {code}\n\nThis code expires in 5 minutes."
    html = (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f6f9f6;'
        'font-family:Arial,Helvetica,sans-serif;color:#0f172a;">'
        '<div style="max-width:560px;margin:0 auto;padding:24px;">'
        f'<div style="font-size:22px;line-height:1.35;font-weight:700;margin:0 0 16px;">{html_escape(subject)}</div>'
        f'<div style="font-size:16px;line-height:1.6;margin:0 0 20px;color:#334155;">{html_escape(intro)}</div>'
        f'<div style="display:inline-block;padding:14px 20px;border-radius:12px;background:#e8f5ec;'
        'font-size:28px;font-weight:700;letter-spacing:6px;color:#0f172a;">'
        f'{html_escape(code)}</div>'
        '<div style="font-size:13px;line-height:1.5;margin:18px 0 0;color:#64748b;">This code expires in 5 minutes.</div>'
        '</div></body></html>'
    )
    payload = {"from": RESEND_FROM, "to": [email], "subject": subject, "text": text, "html": html}
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": RESEND_USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            response = await client.post(RESEND_API_URL, headers=headers, json=payload)
        if response.status_code >= 400:
            print(f"[Resend] Email send failed: {response.status_code} {response.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[Resend] Email send failed: {e}")
        return False


async def _kv_command(*parts):
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        return None

    url = UPSTASH_REDIS_REST_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}",
        "User-Agent": KV_USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, headers=headers, json=list(parts))
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data
    except Exception as e:
        print(f"[KV] Command failed: {e}")
        raise


async def _redis_rate_count(key: str, window_sec: int) -> int:
    global _redis_client
    if not REDIS_URL:
        return 0
    try:
        from redis.asyncio import Redis
    except ImportError as e:
        raise RuntimeError("Install redis package to use REDIS_URL rate limiting") from e

    if _redis_client is None:
        _redis_client = Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    count = int(await _redis_client.incr(key))
    if count == 1:
        await _redis_client.expire(key, window_sec)
    return count


# ── Rate Limiter ────────────────────────────────────────────────────────────

async def check_rate_limit(request, max_requests: int = 5, window_sec: int = 60):
    from fastapi import HTTPException

    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"
    ua = (request.headers.get("user-agent", "") or "")[:64]
    fingerprint = f"{ip}|{ua}"
    route = request.url.path
    key = f"rl:{fingerprint}:{route}"
    safe_key = key.replace(":", "_").replace("/", "_").replace(".", "_").replace("|", "_")

    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        try:
            created = await _kv_command("SET", safe_key, "1", "EX", str(window_sec), "NX")
            if created == "OK":
                return
            count = int(await _kv_command("INCR", safe_key) or 0)
            if count > max_requests:
                raise HTTPException(status_code=429, detail="Too many requests — slow down")
            return
        except HTTPException:
            raise
        except Exception as e:
            print(f"[RateLimit] KV fallback triggered: {e}")

    if REDIS_URL:
        try:
            count = await _redis_rate_count(safe_key, window_sec)
            if count > max_requests:
                raise HTTPException(status_code=429, detail="Too many requests — slow down")
            return
        except HTTPException:
            raise
        except Exception as e:
            print(f"[RateLimit] Redis fallback triggered: {e}")

    now = time.time()
    cutoff = now - window_sec
    _rate_limit_store[key] = [t for t in _rate_limit_store.get(key, []) if t > cutoff]
    if len(_rate_limit_store[key]) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests — slow down")
    _rate_limit_store[key].append(now)


# ── Email verification ──────────────────────────────────────────────────────

async def send_verification_code(email: str) -> str | None:
    """Generate + send code. Returns dev_code if email delivery is unavailable, None if sent."""
    email = (email or "").strip().lower()
    code = str(random.randint(100000, 999999))
    await _store_code_row("verify", email, code)

    if await _send_code_email(
        email,
        "Re-Life — Email Verification Code",
        "Your Re-Life email verification code is ready.",
        code,
    ):
        return None
    return code


async def verify_code(email: str, code: str) -> bool:
    """Check verification code. Returns True if valid."""
    email = (email or "").strip().lower()
    code = (code or "").strip()
    row = await _fetch_code_row("verify", email)
    if not row:
        return False
    if row.get("consumed_at"):
        await _delete_code_row("verify", email)
        return False

    expires_at = row.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            expires_at = 0
    if expires_at and time.time() > float(expires_at):
        await _delete_code_row("verify", email)
        return False

    ok = False
    stored = row.get("code_hash", "")
    try:
        ok = hmac.compare_digest(stored, _code_digest("verify", email, code))
    except Exception:
        ok = False

    if ok:
        await _delete_code_row("verify", email)
        return True

    if supabase_enabled():
        attempts = int(row.get("attempts") or 0) + 1
        await supabase_update("auth_codes", {"attempts": attempts}, filters={"purpose": "verify", "email": email})
    else:
        row["attempts"] = int(row.get("attempts") or 0) + 1
    return False


# ── User helpers ────────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if supabase_enabled():
        return _normalize_user_row(await supabase_select_one("app_users", filters={"email": email}))
    for row in _memory_users_by_id.values():
        if row.get("email") == email:
            return _normalize_user_row(row)
    return None


async def get_user_by_name(display_name: str) -> dict | None:
    display_name = (display_name or "").strip()
    if supabase_enabled():
        return _normalize_user_row(
            await supabase_select_one("app_users", filters={"display_name": display_name})
        )
    for row in _memory_users_by_id.values():
        if row.get("display_name") == display_name:
            return _normalize_user_row(row)
    return None


async def get_user_by_id(identifier) -> dict | None:
    row = await _resolve_user_row(identifier)
    return _normalize_user_row(row)


async def get_all_users() -> list[dict]:
    if supabase_enabled():
        rows = await supabase_select(
            "app_users",
            columns="id,public_id,display_name,email,photo_url,spent_points,earned_points,claimed_coupons,email_verified,created_at,updated_at",
            order="created_at.desc",
        )
        return [_normalize_user_row(row) for row in rows or []]
    rows = sorted(_memory_users_by_id.values(), key=lambda item: item.get("created_at", ""), reverse=True)
    return [_normalize_user_row(row) for row in rows]


async def create_user(display_name: str, password: str, email: str | None = None) -> dict:
    display_name = (display_name or "").strip()
    email = (email or "").strip().lower() or None
    if not display_name:
        raise ValueError("USERNAME_REQUIRED")
    if len(password or "") < 4:
        raise ValueError("PASSWORD_TOO_SHORT")

    if await get_user_by_name(display_name):
        raise ValueError("USERNAME_TAKEN")
    if email and await get_user_by_email(email):
        raise ValueError("EMAIL_TAKEN")

    password_hash = PASSWORD_HASHER.hash(password)
    payload = {
        "display_name": display_name,
        "email": email,
        "password_hash": password_hash,
        "photo_url": None,
        "spent_points": 0,
        "earned_points": 0,
        "claimed_coupons": [],
        "email_verified": bool(email),
    }

    if supabase_enabled():
        rows = await supabase_insert("app_users", payload)
        user = _normalize_user_row(rows[0] if rows else None)
        if not user:
            raise RuntimeError("CREATE_USER_FAILED")
        return user

    row = _memory_store_user(
        {
            "display_name": display_name,
            "email": email,
            "password_hash": password_hash,
            "photo_url": None,
            "spent_points": 0,
            "earned_points": 0,
            "claimed_coupons": [],
            "email_verified": bool(email),
        }
    )
    return _normalize_user_row(row)


async def login_user(display_name: str, password: str) -> dict:
    display_name = (display_name or "").strip()
    user = await get_user_by_name(display_name)
    if not user:
        raise ValueError("USER_NOT_FOUND")

    row = await _resolve_user_row(user["id"] or user["public_id"])
    stored_hash = (row or {}).get("password_hash") if row else None
    if not stored_hash:
        raise ValueError("WRONG_PASSWORD")
    try:
        if not PASSWORD_HASHER.verify(stored_hash, password):
            raise ValueError("WRONG_PASSWORD")
    except (VerifyMismatchError, VerificationError):
        raise ValueError("WRONG_PASSWORD")
    return user


async def save_user_data(identifier, data: dict) -> bool:
    fallback_name = (data or {}).get("_fallbackName") or ""
    row = await _resolve_user_row(identifier)
    if not row and fallback_name:
        row = await _resolve_user_row(fallback_name)
    if not row:
        return False

    update_payload: dict[str, object] = {}
    if "photoUrl" in data or "photo_url" in data:
        update_payload["photo_url"] = data.get("photoUrl", data.get("photo_url"))
    if "spent_points" in data or "spentPoints" in data:
        update_payload["spent_points"] = int(data.get("spent_points", data.get("spentPoints", 0)) or 0)
    if "earned_points" in data or "earnedPoints" in data:
        update_payload["earned_points"] = int(data.get("earned_points", data.get("earnedPoints", 0)) or 0)
    if "claimed_coupons" in data or "claimedCoupons" in data:
        update_payload["claimed_coupons"] = _safe_list(data.get("claimed_coupons", data.get("claimedCoupons")))

    if not update_payload:
        return True

    if supabase_enabled():
        await supabase_update("app_users", update_payload, filters={"id": row["id"]})
        return True

    memory_row = _memory_find_user(row["id"] or row["public_id"])
    if not memory_row:
        return False
    memory_row.update(update_payload)
    memory_row["updated_at"] = _utc_iso()
    return True


# ── Password reset ──────────────────────────────────────────────────────────

async def send_reset_code(email: str) -> str | None:
    email = (email or "").strip().lower()
    user = await get_user_by_email(email)
    if not user:
        return None

    code = str(random.randint(100000, 999999))
    await _store_code_row("reset", email, code, user_id=user.get("id"))

    if await _send_code_email(
        email,
        "Re-Life — Password Reset Code",
        "Your Re-Life password reset code is ready.",
        code,
    ):
        return None
    return code


async def verify_reset_code(email: str, code: str) -> dict | None:
    email = (email or "").strip().lower()
    code = (code or "").strip()
    row = await _fetch_code_row("reset", email)
    if not row:
        return None
    if row.get("consumed_at"):
        await _delete_code_row("reset", email)
        return None

    expires_at = row.get("expires_at")
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            expires_at = 0
    if expires_at and time.time() > float(expires_at):
        await _delete_code_row("reset", email)
        return None

    ok = False
    try:
        ok = hmac.compare_digest(row.get("code_hash", ""), _code_digest("reset", email, code))
    except Exception:
        ok = False

    if not ok:
        if supabase_enabled():
            attempts = int(row.get("attempts") or 0) + 1
            await supabase_update("auth_codes", {"attempts": attempts}, filters={"purpose": "reset", "email": email})
        else:
            row["attempts"] = int(row.get("attempts") or 0) + 1
        return None

    await _delete_code_row("reset", email)
    user_id = row.get("user_id")
    if user_id:
        return await get_user_by_id(user_id)
    return await get_user_by_email(email)


async def update_password(email: str, new_password: str) -> bool:
    email = (email or "").strip().lower()
    if len(new_password or "") < 8:
        return False

    user = await get_user_by_email(email)
    if not user:
        return False

    password_hash = PASSWORD_HASHER.hash(new_password)
    if supabase_enabled():
        await supabase_update("app_users", {"password_hash": password_hash}, filters={"id": user["id"]})
        return True

    row = _memory_find_user(user["id"] or user["public_id"])
    if not row:
        return False
    row["password_hash"] = password_hash
    row["updated_at"] = _utc_iso()
    return True
