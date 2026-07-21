"""Opaque server-side session service."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import secrets
import uuid

from backend import auth
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from backend.config import (
    IS_DEVELOPMENT,
    IS_PRODUCTION,
    SESSION_CLOCK_SKEW_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_IDLE_SECONDS,
    SESSION_MAX_PER_USER,
    SESSION_METADATA_HASH_KEY,
    SESSION_TOUCH_INTERVAL_SECONDS,
)
from backend.storage import (
    supabase_enabled,
    supabase_insert,
    supabase_select,
    supabase_select_one,
    supabase_update,
)

SAFE_USER_COLUMNS = (
    "id,public_id,display_name,email,photo_url,spent_points,earned_points,"
    "claimed_coupons,email_verified,created_at,updated_at"
)
SESSION_COLUMNS = "id,user_id,last_seen_at,revoked_at"
SESSION_MANAGEMENT_COLUMNS = (
    "id,user_agent,request_ip_hash,created_at"
)


class SecurityStoreUnavailable(RuntimeError):
    """Raised when the durable security store is required but unavailable."""


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Verified session data safe to pass to request handlers."""

    session_id: str
    user: dict
    refresh_cookie: bool


def set_session_cookie(response: Response, token: str) -> None:
    """Set the opaque session token with the shared security attributes."""
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_IDLE_SECONDS,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Expire the session cookie using attributes that overwrite the original."""
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=IS_PRODUCTION,
        httponly=True,
        samesite="lax",
    )


class SessionMiddleware(BaseHTTPMiddleware):
    """Resolve an opaque request cookie into a safe request session context."""

    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        request.state.suppress_session_refresh = False
        try:
            request.state.session = await resolve_session(token)
        except SecurityStoreUnavailable:
            response = JSONResponse(
                {"error": "AUTH_SERVICE_UNAVAILABLE"},
                status_code=503,
            )
            if (
                request.method == "POST"
                and request.url.path == "/api/auth/logout"
            ):
                clear_session_cookie(response)
            return response

        response = await call_next(request)
        context = request.state.session
        if (
            context
            and context.refresh_cookie
            and not request.state.suppress_session_refresh
            and token
        ):
            set_session_cookie(response, token)
        return response


def optional_current_user(request: Request) -> dict | None:
    """Return the current public user when the request has a valid session."""
    context = getattr(request.state, "session", None)
    return context.user if context else None


def require_current_user(request: Request) -> dict:
    """FastAPI dependency requiring a valid application session."""
    user = optional_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="AUTHENTICATION_REQUIRED")
    return user


_memory_sessions_by_hash: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat()


def _parse_time(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError("invalid session timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _ip_hash(request_ip: str) -> str:
    if not request_ip:
        return ""
    if not SESSION_METADATA_HASH_KEY:
        raise _store_unavailable()
    canonical_ip = ipaddress.ip_address(str(request_ip).strip()).compressed
    return hmac.new(
        SESSION_METADATA_HASH_KEY.encode("utf-8"),
        canonical_ip.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _store_unavailable(exc: Exception | None = None) -> SecurityStoreUnavailable:
    error = SecurityStoreUnavailable("durable session store unavailable")
    if exc is not None:
        error.__cause__ = exc
    return error


async def create_session(
    user: dict,
    user_agent: str = "",
    request_ip: str = "",
) -> str:
    """Create an opaque session and return its raw cookie token once."""
    try:
        user_id = int(user.get("id"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("session user requires an integer id") from exc

    token = secrets.token_urlsafe(32)
    token_hash = _token_hash(token)
    now = _iso_now()
    normalized_user_agent = str(user_agent or "")[:256]
    request_ip_hash = _ip_hash(request_ip)
    row = {
        "user_id": user_id,
        "token_hash": token_hash,
        "user_agent": normalized_user_agent,
        "request_ip_hash": request_ip_hash,
        "last_seen_at": now,
        "revoked_at": None,
    }

    if supabase_enabled():
        try:
            existing_rows = list(
                await supabase_select(
                    "app_sessions",
                    columns=SESSION_MANAGEMENT_COLUMNS,
                    filters={"user_id": user_id},
                    order="created_at.asc,id.asc",
                    limit=SESSION_MAX_PER_USER,
                )
                or []
            )
            reusable = next(
                (
                    existing
                    for existing in existing_rows
                    if existing.get("user_agent") == normalized_user_agent
                    and existing.get("request_ip_hash") == request_ip_hash
                ),
                None,
            )
            if reusable is None and len(existing_rows) >= SESSION_MAX_PER_USER:
                reusable = existing_rows[0]

            if reusable is not None:
                session_id = reusable.get("id")
                if not session_id:
                    raise RuntimeError("stored session is missing its id")
                await supabase_update(
                    "app_sessions",
                    {
                        "token_hash": token_hash,
                        "user_agent": normalized_user_agent,
                        "request_ip_hash": request_ip_hash,
                        "created_at": now,
                        "last_seen_at": now,
                        "revoked_at": None,
                    },
                    filters={"id": session_id},
                    returning=False,
                )
            else:
                await supabase_insert("app_sessions", row, returning=False)
        except Exception as exc:
            raise _store_unavailable(exc)
        return token

    if not IS_DEVELOPMENT:
        raise _store_unavailable()

    user_sessions = [
        (stored_hash, stored)
        for stored_hash, stored in _memory_sessions_by_hash.items()
        if stored.get("user_id") == user_id
    ]
    reusable_entry = next(
        (
            entry
            for entry in user_sessions
            if entry[1].get("user_agent") == normalized_user_agent
            and entry[1].get("request_ip_hash") == request_ip_hash
        ),
        None,
    )
    if reusable_entry is None and len(user_sessions) >= SESSION_MAX_PER_USER:
        reusable_entry = min(
            user_sessions,
            key=lambda entry: (
                str(entry[1].get("created_at") or ""),
                str(entry[1].get("id") or ""),
            ),
        )

    if reusable_entry is not None:
        old_hash, reusable = reusable_entry
        _memory_sessions_by_hash.pop(old_hash, None)
        _memory_sessions_by_hash[token_hash] = {
            **reusable,
            **row,
            "created_at": now,
        }
    else:
        _memory_sessions_by_hash[token_hash] = {
            "id": str(uuid.uuid4()),
            "created_at": now,
            **row,
        }
    return token


async def _load_session_row(token_hash: str) -> dict | None:
    if supabase_enabled():
        try:
            row = await supabase_select_one(
                "app_sessions",
                columns=SESSION_COLUMNS,
                filters={"token_hash": token_hash},
            )
        except Exception as exc:
            raise _store_unavailable(exc)
        return dict(row) if row else None

    if not IS_DEVELOPMENT:
        raise _store_unavailable()

    row = _memory_sessions_by_hash.get(token_hash)
    return dict(row) if row else None


async def _load_user(user_id: object) -> dict | None:
    try:
        integer_user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    if supabase_enabled():
        try:
            row = await supabase_select_one(
                "app_users",
                columns=SAFE_USER_COLUMNS,
                filters={"id": integer_user_id},
            )
        except Exception as exc:
            raise _store_unavailable(exc)
        return auth.normalize_user_row(dict(row)) if row else None

    if not IS_DEVELOPMENT:
        raise _store_unavailable()

    row = auth._memory_users_by_id.get(integer_user_id)
    return auth.normalize_user_row(deepcopy(row)) if row else None


async def _touch_session(token_hash: str, last_seen_at: str | None = None) -> None:
    timestamp = last_seen_at or _iso_now()
    if supabase_enabled():
        try:
            await supabase_update(
                "app_sessions",
                {"last_seen_at": timestamp},
                filters={"token_hash": token_hash},
                returning=False,
            )
        except Exception as exc:
            raise _store_unavailable(exc)
        return

    if not IS_DEVELOPMENT:
        raise _store_unavailable()

    row = _memory_sessions_by_hash.get(token_hash)
    if row:
        row["last_seen_at"] = timestamp


async def revoke_session(token: str) -> None:
    """Revoke the session identified by a raw cookie token."""
    if not token:
        return
    token_hash = _token_hash(token)
    revoked_at = _iso_now()

    if supabase_enabled():
        try:
            await supabase_update(
                "app_sessions",
                {"revoked_at": revoked_at},
                filters={"token_hash": token_hash},
                returning=False,
            )
        except Exception as exc:
            raise _store_unavailable(exc)
        return

    if not IS_DEVELOPMENT:
        raise _store_unavailable()

    row = _memory_sessions_by_hash.get(token_hash)
    if row:
        row["revoked_at"] = revoked_at


async def revoke_all_user_sessions(user_id: int) -> None:
    """Revoke every session belonging to one user."""
    integer_user_id = int(user_id)
    revoked_at = _iso_now()

    if supabase_enabled():
        try:
            await supabase_update(
                "app_sessions",
                {"revoked_at": revoked_at},
                filters={"user_id": integer_user_id},
                returning=True,
            )
        except Exception as exc:
            raise _store_unavailable(exc)
        return

    if not IS_DEVELOPMENT:
        raise _store_unavailable()

    for row in _memory_sessions_by_hash.values():
        if row.get("user_id") == integer_user_id:
            row["revoked_at"] = revoked_at


async def _best_effort_revoke(token: str) -> None:
    try:
        await revoke_session(token)
    except SecurityStoreUnavailable:
        return


async def resolve_session(token: str | None) -> SessionContext | None:
    """Resolve and validate an opaque cookie token, failing closed on bad data."""
    if not token:
        return None

    raw_token = str(token)
    token_hash = _token_hash(raw_token)
    row = await _load_session_row(token_hash)
    if not row or row.get("revoked_at"):
        return None

    try:
        last_seen = _parse_time(row.get("last_seen_at"))
    except (TypeError, ValueError, OverflowError):
        await _best_effort_revoke(raw_token)
        return None

    now = _now()
    if last_seen > now + timedelta(seconds=SESSION_CLOCK_SKEW_SECONDS):
        await _best_effort_revoke(raw_token)
        return None

    idle_seconds = (now - last_seen).total_seconds()
    if idle_seconds >= SESSION_IDLE_SECONDS:
        await _best_effort_revoke(raw_token)
        return None

    user = await _load_user(row.get("user_id"))
    if not user:
        await _best_effort_revoke(raw_token)
        return None

    refresh_cookie = idle_seconds >= SESSION_TOUCH_INTERVAL_SECONDS
    if refresh_cookie:
        await _touch_session(token_hash, now.isoformat())

    session_id = row.get("id")
    if not session_id:
        await _best_effort_revoke(raw_token)
        return None

    return SessionContext(
        session_id=str(session_id),
        user=user,
        refresh_cookie=refresh_cookie,
    )
