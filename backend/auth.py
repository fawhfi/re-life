"""Re-Life auth — email verification, password reset, rate limiting, user helpers."""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from typing import Annotated
from urllib.parse import urlsplit
import uuid

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.config import (
    ALLOW_DEV_AUTH_CODES,
    AUTH_CODE_MAX_ATTEMPTS,
    AUTH_CODE_SECRET,
    IS_DEVELOPMENT,
    REDIS_URL,
    RESEND_API_KEY,
    RESEND_FROM,
    UPSTASH_REDIS_REST_TOKEN,
    UPSTASH_REDIS_REST_URL,
    VERIFICATION_CODE_EXPIRY_SECONDS,
    validate_auth_security_settings,
)
from backend.storage import (
    supabase_delete,
    supabase_enabled,
    supabase_insert,
    supabase_select,
    supabase_select_one,
    supabase_update,
)

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))

_pending_verifications: dict[str, dict] = {}
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_memory_users_by_id: dict[int, dict] = {}
_memory_users_by_public_id: dict[str, dict] = {}
_memory_user_seq = 1
RESEND_API_URL = "https://api.resend.com/emails"
RESEND_USER_AGENT = "Re-Life/1.0"
KV_USER_AGENT = "Re-Life/1.0"
_redis_client = None
INT_MAX = 2_147_483_647
PHOTO_URL_MAX_LENGTH = 1_000_000
CLAIMED_COUPONS_JSON_MAX_BYTES = 64 * 1024
SAFE_USER_COLUMNS = (
    "id,public_id,display_name,email,photo_url,spent_points,earned_points,"
    "claimed_coupons,email_verified,created_at,updated_at"
)


class AuthDependencyUnavailable(RuntimeError):
    """A required authentication dependency cannot be used safely."""


class EmailDeliveryUnavailable(AuthDependencyUnavailable):
    """The configured email delivery service is unavailable."""


class RateLimitStoreUnavailable(AuthDependencyUnavailable):
    """No configured durable rate-limit store is currently usable."""

validate_auth_security_settings()

BoundedPoint = Annotated[StrictInt, Field(ge=0, le=INT_MAX)]
PhotoUrl = Annotated[StrictStr, Field(max_length=PHOTO_URL_MAX_LENGTH)]
CouponCode = Annotated[StrictStr, Field(min_length=1, max_length=256)]
CouponId = Annotated[StrictStr, Field(max_length=128)]
CouponLabel = Annotated[StrictStr, Field(max_length=256)]
CouponImage = Annotated[StrictStr, Field(max_length=64)]
CouponDescription = Annotated[StrictStr, Field(max_length=4_096)]
APPROVED_AVATAR_EMOJIS = frozenset({
    "👤", "🌿", "♻️", "🌱", "🍃", "🌳", "💚", "🌍", "🪴", "🐼",
    "🐨", "🦊", "🐸", "🌺", "🍀", "🌊", "🔥", "⭐", "🌈", "🦋", "🐝",
})
COUPON_CODE_PATTERN = re.compile(r"\A[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
DATA_IMAGE_PATTERN = re.compile(
    r"\Adata:image/(?:png|jpeg|webp|gif);base64,([A-Za-z0-9+/]+={0,2})\Z"
)
UNSAFE_COUPON_TEXT_PATTERN = re.compile(
    r"[<>`] | on[a-z]+\s*= | javascript\s*:",
    re.IGNORECASE | re.VERBOSE,
)
REGISTRATION_EMAIL_PATTERN = re.compile(r"\A[^@\s]+@[^@\s]+\.[^@\s]+\Z")


def sanitize_photo_url(value) -> str | None:
    """Return an approved avatar value, or None for invalid legacy data."""
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > PHOTO_URL_MAX_LENGTH:
        return None
    if value in APPROVED_AVATAR_EMOJIS:
        return value
    if value.startswith("https://"):
        if len(value) > 2_048 or any(char in value for char in "\"'<>`\\"):
            return None
        if any(ord(char) < 32 or char.isspace() for char in value):
            return None
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            _port = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        return value
    match = DATA_IMAGE_PATTERN.fullmatch(value)
    if not match:
        return None
    try:
        decoded = base64.b64decode(match.group(1), validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    return value if decoded else None


def _validate_coupon_text(value: str | None) -> str | None:
    if value is None:
        return None
    if UNSAFE_COUPON_TEXT_PATTERN.search(value):
        raise ValueError("unsafe coupon text")
    return value


class ClaimedCouponUpdate(BaseModel):
    """Validated stored shape for a claimed reward coupon."""

    model_config = ConfigDict(extra="forbid")

    code: CouponCode
    id: CouponId = None
    title: CouponLabel = None
    provider: CouponLabel = None
    cost: BoundedPoint = None
    image: CouponImage = None
    category: CouponLabel = None
    description: CouponDescription = None
    claimedDate: CouponLabel = None
    expiry: CouponLabel = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not COUPON_CODE_PATTERN.fullmatch(value):
            raise ValueError("invalid coupon code")
        return value

    @field_validator(
        "id",
        "title",
        "provider",
        "image",
        "category",
        "description",
        "claimedDate",
        "expiry",
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_coupon_text(value)


class CurrentAccountUpdate(BaseModel):
    """Strict allowlisted update accepted for the current session account."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    photo_url: PhotoUrl | None = Field(
        default=None,
        validation_alias=AliasChoices("photo_url", "photoUrl"),
    )
    spent_points: BoundedPoint = Field(
        default=None,
        validation_alias=AliasChoices("spent_points", "spentPoints"),
    )
    earned_points: BoundedPoint = Field(
        default=None,
        validation_alias=AliasChoices("earned_points", "earnedPoints"),
    )
    claimed_coupons: Annotated[
        list[ClaimedCouponUpdate],
        Field(max_length=100),
    ] = Field(
        default=None,
        validation_alias=AliasChoices("claimed_coupons", "claimedCoupons"),
    )

    @field_validator("photo_url")
    @classmethod
    def validate_photo_url(cls, value: str | None) -> str | None:
        sanitized = sanitize_photo_url(value)
        if value is not None and sanitized is None:
            raise ValueError("invalid avatar")
        return sanitized

    @model_validator(mode="after")
    def validate_claimed_coupon_bytes(self):
        if "claimed_coupons" not in self.model_fields_set:
            return self
        compact_json = json.dumps(
            [
                coupon.model_dump(exclude_unset=True)
                for coupon in self.claimed_coupons
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(compact_json) > CLAIMED_COUPONS_JSON_MAX_BYTES:
            raise ValueError("claimed coupons exceed the storage size limit")
        return self


def _normalize_claimed_coupons(value) -> list[dict]:
    normalized: list[dict] = []
    for item in _safe_list(value):
        if len(normalized) >= 100:
            break
        try:
            coupon = ClaimedCouponUpdate.model_validate(item)
        except ValidationError:
            continue
        payload = coupon.model_dump(exclude_unset=True)
        candidate = normalized + [payload]
        compact_size = len(json.dumps(
            candidate,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"))
        if compact_size > CLAIMED_COUPONS_JSON_MAX_BYTES:
            continue
        normalized.append(payload)
    return normalized


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
    if not AUTH_CODE_SECRET:
        raise RuntimeError("AUTH_CODE_SECRET is required")
    normalized_email = (email or "").strip().lower()
    payload = f"{purpose}:{normalized_email}:{code}".encode("utf-8")
    return hmac.new(
        AUTH_CODE_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def _generate_code() -> str:
    return str(100_000 + secrets.randbelow(900_000))


def _effective_auth_code_max_attempts() -> int:
    return min(5, max(1, int(AUTH_CODE_MAX_ATTEMPTS)))


def _expiry_timestamp(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            return None
        try:
            timestamp = parsed.timestamp()
        except (OverflowError, OSError, ValueError):
            return None
    else:
        return None
    return timestamp if math.isfinite(timestamp) else None


def normalize_user_row(row: dict | None) -> dict | None:
    """Return the public user API shape without sensitive fields such as password_hash.

    Mutable public values are copied so callers cannot mutate the stored user row.
    """
    if not row:
        return None
    claimed = _normalize_claimed_coupons(
        row.get("claimed_coupons") or row.get("claimedCoupons")
    )
    display_name = row.get("display_name") or row.get("displayName") or ""
    public_id = row.get("public_id") or row.get("userId") or row.get("_key")
    photo_url = sanitize_photo_url(row.get("photo_url") or row.get("photoUrl"))
    result = {
        "id": row.get("id"),
        "public_id": public_id,
        "userId": public_id,
        "_key": public_id,
        "displayName": display_name,
        "display_name": display_name,
        "email": row.get("email"),
        "photoUrl": photo_url,
        "photo_url": photo_url,
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
        "id": uuid.uuid4().hex,
        "purpose": purpose,
        "email": email,
        "user_id": user_id,
        "code_hash": _code_digest(purpose, email, code),
        "expires_at": _utc_now().timestamp() + VERIFICATION_CODE_EXPIRY_SECONDS,
        "attempts": 0,
        "consumed_at": None,
    }
    _pending_verifications[key] = row
    return row


def _memory_get_code(purpose: str, email: str) -> dict | None:
    return _pending_verifications.get(f"{purpose}:{email}")


def _valid_code_row_id(row_id) -> bool:
    return (
        not isinstance(row_id, bool)
        and isinstance(row_id, (int, str))
        and bool(str(row_id).strip())
    )


async def _store_code_row(
    purpose: str,
    email: str,
    code: str,
    *,
    user_id: int | None = None,
) -> dict:
    if supabase_enabled():
        await supabase_delete("auth_codes", filters={"purpose": purpose, "email": email})
        inserted = await supabase_insert(
            "auth_codes",
            {
                "purpose": purpose,
                "email": email,
                "user_id": user_id,
                "code_hash": _code_digest(purpose, email, code),
                "expires_at": _utc_iso(VERIFICATION_CODE_EXPIRY_SECONDS),
                "attempts": 0,
                "consumed_at": None,
            },
            returning=True,
        )
        if (
            not isinstance(inserted, list)
            or len(inserted) != 1
            or not isinstance(inserted[0], dict)
        ):
            raise AuthDependencyUnavailable(
                "Authentication code storage did not return a row handle"
        )
        row = inserted[0]
        row_id = row.get("id")
        if not _valid_code_row_id(row_id):
            raise AuthDependencyUnavailable(
                "Authentication code storage returned an invalid row handle"
            )
        return row
    return _memory_store_code(purpose, email, code, user_id=user_id)


async def _fetch_code_row(purpose: str, email: str) -> dict | None:
    if supabase_enabled():
        return await supabase_select_one(
            "auth_codes",
            filters={"purpose": purpose, "email": email},
        )
    return _memory_get_code(purpose, email)


async def _delete_code_row_if_current(
    purpose: str,
    email: str,
    row_id,
) -> None:
    if not _valid_code_row_id(row_id):
        raise AuthDependencyUnavailable(
            "Authentication code cleanup requires a valid row handle"
        )
    if supabase_enabled():
        await supabase_delete(
            "auth_codes",
            filters={"id": row_id, "purpose": purpose, "email": email},
            returning=True,
        )
        return
    key = f"{purpose}:{email}"
    current = _pending_verifications.get(key)
    if isinstance(current, dict) and current.get("id") == row_id:
        _pending_verifications.pop(key, None)


async def consume_code(purpose: str, email: str, code: str) -> bool:
    """Atomically consume one valid verification or reset code."""
    if not all(isinstance(value, str) for value in (purpose, email, code)):
        return False
    purpose = purpose.strip().lower()
    email = email.strip().lower()
    code = code.strip()
    if purpose not in {"verify", "reset"} or not email:
        return False
    if not re.fullmatch(r"[0-9]{6}", code):
        return False

    row = await _fetch_code_row(purpose, email)
    if not isinstance(row, dict):
        return False
    if row.get("purpose") != purpose:
        return False
    row_email = row.get("email")
    if not isinstance(row_email, str) or row_email.strip().lower() != email:
        return False
    if "consumed_at" not in row or row.get("consumed_at") is not None:
        return False

    expires_at = _expiry_timestamp(row.get("expires_at"))
    if expires_at is None or time.time() >= expires_at:
        return False

    attempts = row.get("attempts")
    max_attempts = _effective_auth_code_max_attempts()
    if (
        isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or attempts < 0
        or attempts >= max_attempts
    ):
        return False

    stored_digest = row.get("code_hash")
    if not isinstance(stored_digest, str):
        return False
    try:
        valid = hmac.compare_digest(
            stored_digest,
            _code_digest(purpose, email, code),
        )
    except (TypeError, ValueError):
        return False

    next_attempts = attempts + 1
    values = {"attempts": next_attempts}
    if valid or next_attempts >= max_attempts:
        values["consumed_at"] = _utc_iso()

    if supabase_enabled():
        row_id = row.get("id")
        if row_id is None or isinstance(row_id, bool):
            return False
        updated = await supabase_update(
            "auth_codes",
            values,
            filters={"id": row_id, "attempts": attempts},
            returning=True,
        )
        return valid and bool(updated)

    row.update(values)
    return valid


async def _send_code_email(email: str, subject: str, intro: str, code: str) -> bool:
    if not RESEND_API_KEY:
        raise EmailDeliveryUnavailable("Email delivery is unavailable")

    expiry_minutes = max(1, math.ceil(VERIFICATION_CODE_EXPIRY_SECONDS / 60))
    text = f"{intro}\n\nVerification code: {code}\n\nThis code expires in {expiry_minutes} minutes."
    html = (
        '<!doctype html><html><body style="margin:0;padding:0;background:#f6f9f6;'
        'font-family:Arial,Helvetica,sans-serif;color:#0f172a;">'
        '<div style="max-width:560px;margin:0 auto;padding:24px;">'
        f'<div style="font-size:22px;line-height:1.35;font-weight:700;margin:0 0 16px;">{html_escape(subject)}</div>'
        f'<div style="font-size:16px;line-height:1.6;margin:0 0 20px;color:#334155;">{html_escape(intro)}</div>'
        f'<div style="display:inline-block;padding:14px 20px;border-radius:12px;background:#e8f5ec;'
        'font-size:28px;font-weight:700;letter-spacing:6px;color:#0f172a;">'
        f'{html_escape(code)}</div>'
        f'<div style="font-size:13px;line-height:1.5;margin:18px 0 0;color:#64748b;">This code expires in {expiry_minutes} minutes.</div>'
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
            raise EmailDeliveryUnavailable("Email delivery is unavailable")
        return True
    except EmailDeliveryUnavailable:
        raise
    except Exception as exc:
        raise EmailDeliveryUnavailable("Email delivery is unavailable") from exc


async def _deliver_stored_code(
    purpose: str,
    email: str,
    subject: str,
    intro: str,
    code: str,
    row_id,
) -> str | None:
    delivery_cause = None
    try:
        delivered = await _send_code_email(email, subject, intro, code)
    except EmailDeliveryUnavailable as exc:
        delivery_error = exc
    except Exception as exc:
        delivery_error = EmailDeliveryUnavailable(
            "Email delivery is unavailable"
        )
        delivery_cause = exc
    else:
        if delivered:
            return None
        delivery_error = EmailDeliveryUnavailable(
            "Email delivery is unavailable"
        )

    if IS_DEVELOPMENT and ALLOW_DEV_AUTH_CODES:
        return code

    try:
        await _delete_code_row_if_current(purpose, email, row_id)
    except Exception as exc:
        raise AuthDependencyUnavailable(
            "Authentication code storage is unavailable"
        ) from exc
    if delivery_cause is not None:
        raise delivery_error from delivery_cause
    raise delivery_error


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

def _safe_rate_limit_key(key: str) -> str:
    return (
        key.replace(":", "_")
        .replace("/", "_")
        .replace(".", "_")
        .replace("|", "_")
    )


def _rate_limit_keys(request, subject: str = "") -> list[str]:
    # Proxy headers are attacker-controlled unless the ASGI server has already
    # validated and applied them. Rate limits therefore use its client identity.
    ip = request.client.host if request.client else "unknown"
    route = request.url.path
    keys = [_safe_rate_limit_key(f"rl:{ip}:{route}")]

    normalized_subject = subject.strip().lower() if isinstance(subject, str) else ""
    if normalized_subject:
        subject_hash = hashlib.sha256(normalized_subject.encode("utf-8")).hexdigest()
        keys.append(_safe_rate_limit_key(f"rl:subject:{route}:{subject_hash}"))
    return keys


async def _kv_rate_count(key: str, window_sec: int) -> int:
    created = await _kv_command("SET", key, "1", "EX", str(window_sec), "NX")
    if created == "OK":
        return 1
    return int(await _kv_command("INCR", key) or 0)


async def _enforce_rate_limit_counts(
    keys: list[str],
    max_requests: int,
    counter,
) -> None:
    from fastapi import HTTPException

    for key in keys:
        count = await counter(key)
        if count > max_requests:
            raise HTTPException(status_code=429, detail="Too many requests — slow down")


async def check_rate_limit(
    request,
    max_requests: int = 5,
    window_sec: int = 60,
    subject: str = "",
):
    from fastapi import HTTPException

    keys = _rate_limit_keys(request, subject)
    backend_errors: list[Exception] = []

    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        try:
            await _enforce_rate_limit_counts(
                keys,
                max_requests,
                lambda key: _kv_rate_count(key, window_sec),
            )
            return
        except HTTPException:
            raise
        except Exception as exc:
            backend_errors.append(exc)

    if REDIS_URL:
        try:
            await _enforce_rate_limit_counts(
                keys,
                max_requests,
                lambda key: _redis_rate_count(key, window_sec),
            )
            return
        except HTTPException:
            raise
        except Exception as exc:
            backend_errors.append(exc)

    if not IS_DEVELOPMENT:
        cause = backend_errors[-1] if backend_errors else None
        raise RateLimitStoreUnavailable(
            "Durable rate-limit storage is unavailable"
        ) from cause

    now = time.time()
    cutoff = now - window_sec
    for key in keys:
        _rate_limit_store[key] = [
            timestamp
            for timestamp in _rate_limit_store.get(key, [])
            if timestamp > cutoff
        ]
        if len(_rate_limit_store[key]) >= max_requests:
            raise HTTPException(status_code=429, detail="Too many requests — slow down")
        _rate_limit_store[key].append(now)


# ── Email verification ──────────────────────────────────────────────────────

async def send_verification_code(email: str) -> str | None:
    """Generate and send a code, exposing it only in explicitly enabled development."""
    email = (email or "").strip().lower()
    code = _generate_code()
    try:
        stored_row = await _store_code_row("verify", email, code)
    except Exception as exc:
        raise AuthDependencyUnavailable(
            "Authentication code storage is unavailable"
        ) from exc

    return await _deliver_stored_code(
        "verify",
        email,
        "Re-Life — Email Verification Code",
        "Your Re-Life email verification code is ready.",
        code,
        stored_row["id"],
    )


async def verify_code(email: str, code: str) -> bool:
    """Check verification code. Returns True if valid."""
    email = (email or "").strip().lower()
    code = (code or "").strip()
    return await consume_code("verify", email, code)


# ── User helpers ────────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if supabase_enabled():
        return normalize_user_row(await supabase_select_one("app_users", filters={"email": email}))
    for row in _memory_users_by_id.values():
        if row.get("email") == email:
            return normalize_user_row(row)
    return None


async def get_user_by_name(display_name: str) -> dict | None:
    display_name = (display_name or "").strip()
    if supabase_enabled():
        return normalize_user_row(
            await supabase_select_one("app_users", filters={"display_name": display_name})
        )
    for row in _memory_users_by_id.values():
        if row.get("display_name") == display_name:
            return normalize_user_row(row)
    return None


async def get_user_by_id(identifier) -> dict | None:
    row = await _resolve_user_row(identifier)
    return normalize_user_row(row)


async def get_user_by_internal_id(user_id: int) -> dict | None:
    """Return one safe user by internal app_users id without external-id fallback."""
    internal_id = int(user_id)
    if supabase_enabled():
        row = await supabase_select_one(
            "app_users",
            columns=SAFE_USER_COLUMNS,
            filters={"id": internal_id},
        )
    else:
        row = _memory_users_by_id.get(internal_id)
    return normalize_user_row(row)


async def get_all_users() -> list[dict]:
    if supabase_enabled():
        rows = await supabase_select(
            "app_users",
            columns=SAFE_USER_COLUMNS,
            order="created_at.desc",
        )
        return [normalize_user_row(row) for row in rows or []]
    rows = sorted(_memory_users_by_id.values(), key=lambda item: item.get("created_at", ""), reverse=True)
    return [normalize_user_row(row) for row in rows]


async def create_user(
    display_name: str,
    password: str,
    email: str,
    *,
    verification_code: str,
) -> dict:
    display_name = (display_name or "").strip()
    email = (email or "").strip().lower()
    verification_code = (verification_code or "").strip()
    if len(display_name) < 2:
        raise ValueError("USERNAME_TOO_SHORT")
    if not email:
        raise ValueError("EMAIL_REQUIRED")
    if len(email) > 320 or not REGISTRATION_EMAIL_PATTERN.fullmatch(email):
        raise ValueError("INVALID_EMAIL")
    if len(password or "") < 8:
        raise ValueError("PASSWORD_TOO_SHORT")

    if await get_user_by_name(display_name):
        raise ValueError("USERNAME_TAKEN")
    if await get_user_by_email(email):
        raise ValueError("EMAIL_TAKEN")
    if not await consume_code("verify", email, verification_code):
        raise ValueError("INVALID_OR_EXPIRED_CODE")

    password_hash = PASSWORD_HASHER.hash(password)
    payload = {
        "display_name": display_name,
        "email": email,
        "password_hash": password_hash,
        "photo_url": None,
        "spent_points": 0,
        "earned_points": 0,
        "claimed_coupons": [],
        "email_verified": True,
    }

    if supabase_enabled():
        rows = await supabase_insert("app_users", payload)
        user = normalize_user_row(rows[0] if rows else None)
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
            "email_verified": True,
        }
    )
    return normalize_user_row(row)


async def login_user(display_name: str, password: str) -> dict:
    display_name = (display_name or "").strip()
    if supabase_enabled():
        row = await supabase_select_one(
            "app_users",
            filters={"display_name": display_name},
        )
    else:
        row = next(
            (
                candidate
                for candidate in _memory_users_by_id.values()
                if candidate.get("display_name") == display_name
            ),
            None,
        )

    stored_hash = row.get("password_hash") if isinstance(row, dict) else None
    candidate_hash = stored_hash if isinstance(stored_hash, str) and stored_hash else DUMMY_PASSWORD_HASH
    verified = False
    try:
        verified = bool(PASSWORD_HASHER.verify(candidate_hash, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        verified = False

    if not isinstance(row, dict) or not verified:
        raise ValueError("INVALID_CREDENTIALS")

    if PASSWORD_HASHER.check_needs_rehash(candidate_hash):
        password_hash = PASSWORD_HASHER.hash(password)
        if supabase_enabled():
            updated_rows = await supabase_update(
                "app_users",
                {"password_hash": password_hash},
                filters={"id": row.get("id")},
                returning=True,
            )
            if not updated_rows or not isinstance(updated_rows[0], dict):
                raise RuntimeError("PASSWORD_REHASH_FAILED")
            row = updated_rows[0]
        else:
            row["password_hash"] = password_hash
            row["updated_at"] = _utc_iso()

    return normalize_user_row(row)


async def save_user_data(user_id: int, data: dict) -> bool:
    validated = CurrentAccountUpdate.model_validate(
        data if data is not None else {}
    )
    update_payload = validated.model_dump(exclude_unset=True)
    user_id = int(user_id)

    if not update_payload:
        return await get_user_by_internal_id(user_id) is not None

    if supabase_enabled():
        updated_rows = await supabase_update(
            "app_users",
            update_payload,
            filters={"id": user_id},
            returning=True,
        )
        return bool(updated_rows)

    row = _memory_users_by_id.get(user_id)
    if not row:
        return False
    row.update(update_payload)
    row["updated_at"] = _utc_iso()
    return True


# ── Password reset ──────────────────────────────────────────────────────────

async def send_reset_code(email: str) -> str | None:
    email = (email or "").strip().lower()
    try:
        user = await get_user_by_email(email)
    except Exception as exc:
        raise AuthDependencyUnavailable(
            "Authentication account storage is unavailable"
        ) from exc
    code = _generate_code()
    user_id = user.get("id") if user else None
    try:
        stored_row = await _store_code_row(
            "reset",
            email,
            code,
            user_id=user_id,
        )
    except Exception as exc:
        raise AuthDependencyUnavailable(
            "Authentication code storage is unavailable"
        ) from exc

    return await _deliver_stored_code(
        "reset",
        email,
        "Re-Life — Password Reset Request",
        (
            "If this email is registered with Re-Life, use the code below "
            "to continue the password reset request."
        ),
        code,
        stored_row["id"],
    )


async def verify_reset_code(email: str, code: str) -> dict | None:
    email = (email or "").strip().lower()
    code = (code or "").strip()
    row = await _fetch_code_row("reset", email)
    user_id = row.get("user_id") if isinstance(row, dict) else None
    if not await consume_code("reset", email, code):
        return None
    if user_id is None or isinstance(user_id, bool):
        return None
    try:
        user = await get_user_by_internal_id(int(user_id))
    except (TypeError, ValueError):
        return None
    if not user or (user.get("email") or "").strip().lower() != email:
        return None
    return user


async def update_password(email: str, new_password: str) -> bool:
    email = (email or "").strip().lower()
    if len(new_password or "") < 8:
        return False

    user = await get_user_by_email(email)
    if not user:
        return False

    password_hash = PASSWORD_HASHER.hash(new_password)
    if supabase_enabled():
        updated = await supabase_update(
            "app_users",
            {"password_hash": password_hash},
            filters={"id": user["id"]},
            returning=True,
        )
        return bool(updated)

    row = _memory_find_user(user["id"] or user["public_id"])
    if not row:
        return False
    row["password_hash"] = password_hash
    row["updated_at"] = _utc_iso()
    return True
