"""Re-Life auth — email verification, password reset, rate limiting, DB helpers."""
import time, random, httpx
from collections import defaultdict
from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM,
    VERIFICATION_CODE_EXPIRY, FIREBASE_DB_URL,
)

# ── In-memory fallback ──────────────────────────────────────────────────────
_pending_verifications: dict[str, dict] = {}
_ratelimit_store: dict[str, list[float]] = defaultdict(list)
_cleanup_counter = 0

# ── Firebase DB helpers ─────────────────────────────────────────────────────

async def db_put(path: str, data):
    # Sanitize path to prevent path traversal
    if ".." in path or path.startswith("/"):
        raise ValueError("Invalid database path")
    if not FIREBASE_DB_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.put(f"{FIREBASE_DB_URL}/{path}.json", json=data)
            if r.status_code >= 400:
                print(f"[DB] Put {path} → {r.status_code} {r.text[:100]}")
                raise Exception(f"HTTP {r.status_code}")
    except Exception as e:
        print(f"[DB] Put failed: {e}")
        raise

async def db_get(path: str):
    # Sanitize path to prevent path traversal
    if ".." in path or path.startswith("/"):
        raise ValueError("Invalid database path")
    if not FIREBASE_DB_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            res = await c.get(f"{FIREBASE_DB_URL}/{path}.json")
            if res.status_code == 200:
                return res.json()
            print(f"[DB] Get {path} → {res.status_code}")
            return None
    except Exception as e:
        print(f"[DB] Get failed: {e}")
        raise

async def db_del(path: str):
    # Sanitize path to prevent path traversal
    if ".." in path or path.startswith("/"):
        raise ValueError("Invalid database path")
    if not FIREBASE_DB_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.delete(f"{FIREBASE_DB_URL}/{path}.json")
    except Exception as e:
        print(f"[DB] Del failed: {e}")

# ── Rate Limiter ────────────────────────────────────────────────────────────

async def check_rate_limit(request, max_requests: int = 5, window_sec: int = 60):
    from fastapi import HTTPException
    global _cleanup_counter
    _cleanup_counter += 1

    # Periodically clean up expired rate limit entries from DB (every 200 requests)
    if FIREBASE_DB_URL and _cleanup_counter % 200 == 0:
        try:
            all_data = await db_get("rate_limit")
            if all_data and isinstance(all_data, dict):
                now = time.time()
                deleted = 0
                for key, val in list(all_data.items()):
                    if isinstance(val, dict) and val.get("expires", 0) < now:
                        await db_del(f"rate_limit/{key}")
                        deleted += 1
                if deleted:
                    print(f"[RateLimit] Cleaned up {deleted} expired entries")
        except Exception as e:
            print(f"[RateLimit] Cleanup failed: {e}")

    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"
    # Combine IP + User-Agent to make VPN bypass harder
    ua = (request.headers.get("user-agent", "") or "")[:64]
    fingerprint = f"{ip}|{ua}"
    route = request.url.path
    key = f"rl:{fingerprint}:{route}"
    safe_key = key.replace(":", "_").replace("/", "_").replace(".", "_").replace("|", "_")

    if FIREBASE_DB_URL:
        now = time.time()
        try:
            data = await db_get(f"rate_limit/{safe_key}")
        except:
            data = None
        if data and isinstance(data, dict):
            count = data.get("count", 0)
            expires = data.get("expires", 0)
            if now < expires and count >= max_requests:
                raise HTTPException(status_code=429, detail="Too many requests — slow down")
            if now >= expires:
                # Delete expired entry from DB
                try: await db_del(f"rate_limit/{safe_key}")
                except: pass
                count = 0
        else:
            count = 0
        try:
            await db_put(f"rate_limit/{safe_key}", {"count": count + 1, "expires": now + window_sec})
        except:
            _ratelimit_store[key] = [t for t in _ratelimit_store.get(key, []) if t > now - window_sec]
            if len(_ratelimit_store[key]) >= max_requests:
                raise HTTPException(status_code=429, detail="Too many requests — slow down")
            _ratelimit_store[key].append(now)
    else:
        now = time.time()
        cutoff = now - window_sec
        _ratelimit_store[key] = [t for t in _ratelimit_store.get(key, []) if t > cutoff]
        if len(_ratelimit_store[key]) >= max_requests:
            raise HTTPException(status_code=429, detail="Too many requests — slow down")
        _ratelimit_store[key].append(now)

# ── Email verification ──────────────────────────────────────────────────────

async def send_verification_code(email: str) -> str | None:
    """Generate + send code. Returns dev_code if SMTP unavailable, None if sent."""
    code = str(random.randint(100000, 999999))
    safe_email = email.replace(".", "_").replace("@", "_")

    if FIREBASE_DB_URL:
        await db_put(f"verify/{safe_email}", {"code": code, "expires": time.time() + VERIFICATION_CODE_EXPIRY})
    else:
        now = time.time()
        _pending_verifications[email] = {"code": code, "expires_at": now + VERIFICATION_CODE_EXPIRY}
        for k in list(_pending_verifications):
            if _pending_verifications[k].get("expires_at", 0) < now:
                del _pending_verifications[k]

    if SMTP_USER and SMTP_PASS:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart()
            msg["From"] = SMTP_FROM; msg["To"] = email
            msg["Subject"] = "Re-Life — Email Verification Code"
            msg.attach(MIMEText(f"Your code: {code}\n\nExpires in 5 minutes.", "plain"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
                s.starttls(); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
            return None
        except Exception as e:
            print(f"[Verify] SMTP failed: {e}")
    # Dev mode: return code
    return code

async def verify_code(email: str, code: str) -> bool:
    """Check verification code. Returns True if valid."""
    safe_email = email.replace(".", "_").replace("@", "_")
    if FIREBASE_DB_URL:
        data = await db_get(f"verify/{safe_email}")
        if data and isinstance(data, dict):
            if time.time() > data.get("expires", 0):
                await db_del(f"verify/{safe_email}")
                return False
            if data.get("code") == code:
                await db_del(f"verify/{safe_email}")
                return True
    else:
        pending = _pending_verifications.get(email)
        if pending:
            if time.time() > pending["expires_at"]:
                del _pending_verifications[email]
                return False
            if pending["code"] == code:
                del _pending_verifications[email]
                return True
    return False

# ── Password reset ──────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> dict | None:
    if not FIREBASE_DB_URL:
        return None
    users = await db_get("users")
    if not users:
        return None
    for key, data in users.items():
        if isinstance(data, dict) and data.get("email") == email:
            return {"key": key, **data}
    return None

async def send_reset_code(email: str) -> str | None:
    user = await get_user_by_email(email)
    if not user:
        return None
    code = str(random.randint(100000, 999999))
    safe_email = email.replace(".", "_").replace("@", "_")
    if FIREBASE_DB_URL:
        await db_put(f"reset/{safe_email}", {"code": code, "expires": time.time() + VERIFICATION_CODE_EXPIRY})
    else:
        _pending_verifications[f"reset:{email}"] = {"code": code, "expires_at": time.time() + VERIFICATION_CODE_EXPIRY}

    if SMTP_USER and SMTP_PASS:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart()
            msg["From"] = SMTP_FROM; msg["To"] = email
            msg["Subject"] = "Re-Life — Password Reset Code"
            msg.attach(MIMEText(f"Your reset code: {code}\n\nExpires in 5 minutes.", "plain"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
                s.starttls(); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
            return None
        except Exception as e:
            print(f"[Reset] SMTP failed: {e}")
    return code

async def verify_reset_code(email: str, code: str) -> dict | None:
    """Verify reset code and return user dict if valid."""
    user = await get_user_by_email(email)
    if not user:
        return None
    safe_email = email.replace(".", "_").replace("@", "_")
    if FIREBASE_DB_URL:
        data = await db_get(f"reset/{safe_email}")
        if data and isinstance(data, dict):
            if time.time() > data.get("expires", 0):
                await db_del(f"reset/{safe_email}")
                return None
            if data.get("code") == code:
                await db_del(f"reset/{safe_email}")
                return user
    else:
        pending = _pending_verifications.get(f"reset:{email}")
        if pending:
            if time.time() > pending["expires_at"]:
                del _pending_verifications[f"reset:{email}"]
                return None
            if pending["code"] == code:
                del _pending_verifications[f"reset:{email}"]
                return user
    return None

async def update_password(email: str, new_password: str) -> bool:
    """Update a user's password by email. Returns True on success."""
    user = await get_user_by_email(email)
    if not user:
        return False
    if FIREBASE_DB_URL:
        try:
            from argon2 import PasswordHasher
            ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)
            password_hash = ph.hash(new_password)
            await db_put(f"users/{user['key']}/passwordHash", password_hash)
            return True
        except Exception as e:
            print(f"[Auth] update_password failed: {e}")
            return False
    return False
