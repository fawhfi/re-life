# Session 與身份驗證實作計畫

> **給代理工作者：** 必須逐項使用 `superpowers:subagent-driven-development`（建議）或 `superpowers:executing-plans` 執行本計畫。所有步驟以核取方塊追蹤，正式程式碼前必須先看見對應測試因預期原因失敗。

**目標：** 建立資料庫型不透明 Session，讓登入、身份恢復、登出與閒置到期都由伺服器控制。

**架構：** FastAPI middleware 從 HttpOnly Cookie 解析 Session；`sessions.py` 只保存 token 的 SHA-256 雜湊，並把目前使用者放入 `request.state`。正式環境必須使用 Supabase，開發環境才可使用記憶體替代。

**技術棧：** Python 3、FastAPI、Starlette middleware、Supabase REST、Argon2、pytest／unittest。

---

## 檔案配置

- 新增 `sessions.py`：Session token、持久化、撤銷、閒置期限與 Cookie helper。
- 修改 `config.py`：應用環境及 Session 設定。
- 修改 `main.py`：正確載入 `.env`、註冊 middleware、登入 Cookie、`/api/auth/me`、登出及頁面重新導向。
- 修改 `auth.py`：把使用者標準化 helper 改為可供 Session 邊界重用。
- 修改 `supabase_schema.sql`：新增 `app_sessions`。
- 修改 `static/supabase.js`、`static/app.js`、`templates/login.html`、`templates/register.html`：只依靠伺服器 Session 恢復身份。
- 新增 `tests/test_session_auth.py`、`tests/test_security_config.py`：安全回歸測試。

### 任務 1：建立可預測的環境與 Session 設定

**檔案：**
- 修改：`config.py`
- 修改：`main.py`
- 新增測試：`tests/test_security_config.py`

- [ ] **步驟 1：先寫 `.env` 載入與 Session 設定測試**

```python
import importlib
import os
import unittest
from unittest.mock import patch

import config


class SecurityConfigTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)

    def test_session_defaults_are_secure_and_explicit(self):
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "SESSION_COOKIE_NAME": "rel_session",
            "SESSION_IDLE_DAYS": "30",
        }, clear=False):
            reloaded = importlib.reload(config)

        self.assertEqual(reloaded.APP_ENV, "production")
        self.assertTrue(reloaded.IS_PRODUCTION)
        self.assertFalse(reloaded.IS_DEVELOPMENT)
        self.assertEqual(reloaded.SESSION_COOKIE_NAME, "rel_session")
        self.assertEqual(reloaded.SESSION_IDLE_SECONDS, 30 * 24 * 60 * 60)

    def test_main_loads_dotenv_before_importing_config(self):
        source = open("main.py", encoding="utf-8").read()
        load_index = source.index('load_dotenv(root_dir / ".env")')
        config_index = source.index("from config import")
        self.assertLess(load_index, config_index)
```

- [ ] **步驟 2：執行測試並確認紅燈原因正確**

執行：

```powershell
python -m pytest tests/test_security_config.py -v
```

預期：第一個測試因 `APP_ENV`／`SESSION_IDLE_SECONDS` 尚未定義而失敗；第二個測試因 `load_dotenv()` 位於本機 import 後方而失敗。

- [ ] **步驟 3：在 `config.py` 新增明確設定**

```python
def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_DEVELOPMENT = APP_ENV == "development"
IS_PRODUCTION = APP_ENV == "production"
ALLOW_DEV_AUTH_CODES = IS_DEVELOPMENT and _env_bool("ALLOW_DEV_AUTH_CODES")

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "rel_session").strip() or "rel_session"
SESSION_IDLE_DAYS = max(1, int(os.getenv("SESSION_IDLE_DAYS", "30")))
SESSION_IDLE_SECONDS = SESSION_IDLE_DAYS * 24 * 60 * 60
SESSION_TOUCH_INTERVAL_SECONDS = max(60, int(os.getenv("SESSION_TOUCH_INTERVAL_SECONDS", "900")))
```

把 `main.py` 開頭改成先載入 `.env`，再匯入任何本機模組：

```python
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent
load_dotenv(root_dir / ".env")

from auth import (
    check_rate_limit,
    create_user,
    get_all_users,
    get_user_by_email,
    get_user_by_id,
    get_user_by_name,
    login_user,
    normalize_user_row,
    save_user_data,
    send_reset_code,
    send_verification_code,
    update_password,
    verify_code,
    verify_reset_code,
)
from config import ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES, SUPABASE_STORAGE_BUCKET, get_public_config
```

刪除原本位於本機 import 之後的 `load_dotenv()` 區塊。

- [ ] **步驟 4：重新執行設定測試**

```powershell
python -m pytest tests/test_security_config.py -v
```

預期：全部通過。

- [ ] **步驟 5：提交設定修復**

```powershell
git add config.py main.py tests/test_security_config.py
git commit -m "fix: load security settings before app imports"
```

### 任務 2：新增 `app_sessions` schema

**檔案：**
- 修改：`supabase_schema.sql`
- 新增測試：`tests/test_session_auth.py`

- [ ] **步驟 1：先寫 schema 失敗測試**

```python
from pathlib import Path
import unittest


class SessionSchemaTests(unittest.TestCase):
    def test_schema_stores_only_session_token_hashes(self):
        schema = Path("supabase_schema.sql").read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.app_sessions", schema)
        self.assertIn("token_hash text not null unique", schema)
        self.assertIn("last_seen_at timestamptz not null default now()", schema)
        self.assertIn("revoked_at timestamptz", schema)
        self.assertNotIn("session_token text", schema)
        self.assertIn("app_sessions_token_hash_idx", schema)
        self.assertIn("app_sessions_user_id_idx", schema)
```

- [ ] **步驟 2：確認 schema 測試紅燈**

```powershell
python -m pytest tests/test_session_auth.py::SessionSchemaTests -v
```

預期：因 `app_sessions` 尚不存在而失敗。

- [ ] **步驟 3：在 `supabase_schema.sql` 加入資料表與索引**

```sql
create table if not exists public.app_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id bigint not null references public.app_users(id) on delete cascade,
  token_hash text not null unique,
  user_agent text not null default '' check (char_length(user_agent) <= 256),
  request_ip_hash text not null default '' check (char_length(request_ip_hash) <= 64),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  revoked_at timestamptz
);

create index if not exists app_sessions_token_hash_idx
on public.app_sessions (token_hash);

create index if not exists app_sessions_user_id_idx
on public.app_sessions (user_id);

create index if not exists app_sessions_last_seen_idx
on public.app_sessions (last_seen_at);

comment on table public.app_sessions is
'Opaque server-side sessions for the custom app_users account system.';
```

- [ ] **步驟 4：重新執行 schema 測試**

```powershell
python -m pytest tests/test_session_auth.py::SessionSchemaTests -v
```

預期：通過。

- [ ] **步驟 5：提交 schema**

```powershell
git add supabase_schema.sql tests/test_session_auth.py
git commit -m "feat: add database-backed app sessions"
```

### 任務 3：實作不透明 Session service

**檔案：**
- 新增：`sessions.py`
- 修改：`auth.py`
- 修改測試：`tests/test_session_auth.py`

- [ ] **步驟 1：加入 token 雜湊、建立、解析及撤銷測試**

```python
from datetime import datetime, timedelta, timezone
import hashlib
import unittest
from unittest.mock import AsyncMock, patch

import sessions


class SessionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_session_persists_hash_not_raw_token(self):
        captured = {}

        async def fake_insert(table, values, *, returning=True):
            captured.update(values)
            return [{"id": "session-1", **values}]

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_insert", new=fake_insert), \
             patch.object(sessions.secrets, "token_urlsafe", return_value="raw-secret-token"):
            token = await sessions.create_session({"id": 7}, user_agent="pytest", request_ip="127.0.0.1")

        self.assertEqual(token, "raw-secret-token")
        self.assertEqual(captured["token_hash"], hashlib.sha256(b"raw-secret-token").hexdigest())
        self.assertNotIn("raw-secret-token", captured.values())

    async def test_resolve_rejects_session_idle_for_30_days(self):
        stale = (datetime.now(timezone.utc) - timedelta(days=30, seconds=1)).isoformat()
        row = {"id": "s1", "user_id": 7, "token_hash": "hash", "last_seen_at": stale, "revoked_at": None}

        with patch.object(sessions, "_token_hash", return_value="hash"), \
             patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=AsyncMock(return_value=row)), \
             patch.object(sessions, "supabase_update", new=AsyncMock()) as update:
            resolved = await sessions.resolve_session("token")

        self.assertIsNone(resolved)
        update.assert_awaited_once()

    async def test_revoke_all_sessions_filters_by_user(self):
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_update", new=AsyncMock(return_value=[])) as update:
            await sessions.revoke_all_user_sessions(42)

        self.assertEqual(update.await_args.kwargs["filters"], {"user_id": 42})
        self.assertIsNotNone(update.await_args.args[1]["revoked_at"])
```

- [ ] **步驟 2：確認測試因 `sessions.py` 不存在而失敗**

```powershell
python -m pytest tests/test_session_auth.py::SessionServiceTests -v
```

預期：collection 時出現 `ModuleNotFoundError: sessions`。

- [ ] **步驟 3：新增 `sessions.py` 的最小完整實作**

```python
"""Opaque database-backed sessions for Re-Life."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets

from config import IS_DEVELOPMENT, SESSION_IDLE_SECONDS, SESSION_TOUCH_INTERVAL_SECONDS
from storage import supabase_enabled, supabase_insert, supabase_select_one, supabase_update


class SecurityStoreUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    user: dict
    token: str
    refresh_cookie: bool


_memory_sessions: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat()


def _parse_time(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ip_hash(request_ip: str) -> str:
    return hashlib.sha256(request_ip.encode("utf-8")).hexdigest() if request_ip else ""


async def create_session(user: dict, *, user_agent: str = "", request_ip: str = "") -> str:
    token = secrets.token_urlsafe(32)
    row = {
        "user_id": int(user["id"]),
        "token_hash": _token_hash(token),
        "user_agent": user_agent[:256],
        "request_ip_hash": _ip_hash(request_ip),
        "last_seen_at": _iso_now(),
        "revoked_at": None,
    }
    if supabase_enabled():
        await supabase_insert("app_sessions", row)
    elif IS_DEVELOPMENT:
        _memory_sessions[row["token_hash"]] = {"id": secrets.token_hex(16), "user": dict(user), **row}
    else:
        raise SecurityStoreUnavailable("Persistent session storage unavailable")
    return token


async def _load_session_row(token_hash: str) -> dict | None:
    if supabase_enabled():
        return await supabase_select_one("app_sessions", filters={"token_hash": token_hash})
    if IS_DEVELOPMENT:
        return _memory_sessions.get(token_hash)
    raise SecurityStoreUnavailable("Persistent session storage unavailable")


async def _load_user(row: dict) -> dict | None:
    if row.get("user"):
        return dict(row["user"])
    return await supabase_select_one("app_users", filters={"id": int(row["user_id"])})


async def resolve_session(token: str | None) -> SessionContext | None:
    if not token:
        return None
    token_hash = _token_hash(token)
    row = await _load_session_row(token_hash)
    if not row or row.get("revoked_at"):
        return None
    idle_seconds = (_now() - _parse_time(row["last_seen_at"])).total_seconds()
    if idle_seconds >= SESSION_IDLE_SECONDS:
        await revoke_session(token)
        return None
    user = await _load_user(row)
    if not user:
        await revoke_session(token)
        return None
    refresh = idle_seconds >= SESSION_TOUCH_INTERVAL_SECONDS
    if refresh:
        await _touch_session(token_hash)
    return SessionContext(str(row["id"]), user, token, refresh)


async def _touch_session(token_hash: str) -> None:
    values = {"last_seen_at": _iso_now()}
    if supabase_enabled():
        await supabase_update("app_sessions", values, filters={"token_hash": token_hash}, returning=False)
    elif token_hash in _memory_sessions:
        _memory_sessions[token_hash].update(values)


async def revoke_session(token: str | None) -> None:
    if not token:
        return
    token_hash = _token_hash(token)
    values = {"revoked_at": _iso_now()}
    if supabase_enabled():
        await supabase_update("app_sessions", values, filters={"token_hash": token_hash}, returning=False)
    elif IS_DEVELOPMENT and token_hash in _memory_sessions:
        _memory_sessions[token_hash].update(values)
    elif not IS_DEVELOPMENT:
        raise SecurityStoreUnavailable("Persistent session storage unavailable")


async def revoke_all_user_sessions(user_id: int) -> None:
    values = {"revoked_at": _iso_now()}
    if supabase_enabled():
        await supabase_update("app_sessions", values, filters={"user_id": int(user_id)}, returning=False)
    elif IS_DEVELOPMENT:
        for row in _memory_sessions.values():
            if int(row["user_id"]) == int(user_id):
                row.update(values)
    else:
        raise SecurityStoreUnavailable("Persistent session storage unavailable")
```

在 `auth.py` 把 `_normalize_user_row` 改名為 `normalize_user_row`，並更新檔案內所有呼叫，讓 Session 路由能使用同一輸出格式。

- [ ] **步驟 4：執行 Session service 測試**

```powershell
python -m pytest tests/test_session_auth.py::SessionServiceTests -v
```

預期：全部通過。

- [ ] **步驟 5：提交 Session service**

```powershell
git add sessions.py auth.py tests/test_session_auth.py
git commit -m "feat: implement opaque session service"
```

### 任務 4：接入 FastAPI middleware、登入、`/me` 與登出

**檔案：**
- 修改：`sessions.py`
- 修改：`main.py`
- 修改測試：`tests/test_session_auth.py`

- [ ] **步驟 1：先寫受保護身份流程測試**

```python
from fastapi.testclient import TestClient
import unittest
from unittest.mock import AsyncMock, patch

from main import app
from sessions import SessionContext


class SessionRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_me_rejects_missing_session(self):
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_login_sets_httponly_session_cookie(self):
        user = {"id": 7, "displayName": "Alice", "email_verified": True}
        with patch("main.login_user", new=AsyncMock(return_value=user)), \
             patch("main.create_session", new=AsyncMock(return_value="raw-token")):
            response = self.client.post("/api/auth/login", json={"display_name": "Alice", "password": "correct-pass"})

        cookie = response.headers.get("set-cookie", "")
        self.assertEqual(response.status_code, 200)
        self.assertIn("rel_session=raw-token", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)

    def test_logout_revokes_cookie_session(self):
        context = SessionContext("s1", {"id": 7}, "raw-token", False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=context)), \
             patch("main.revoke_session", new=AsyncMock()) as revoke:
            response = self.client.post("/api/auth/logout", cookies={"rel_session": "raw-token"})

        self.assertEqual(response.status_code, 200)
        revoke.assert_awaited_once_with("raw-token")
        self.assertIn("rel_session=", response.headers.get("set-cookie", ""))
```

- [ ] **步驟 2：確認路由測試紅燈**

```powershell
python -m pytest tests/test_session_auth.py::SessionRouteTests -v
```

預期：`/api/auth/me` 不存在，登入不設定 Cookie，登出端點不存在。

- [ ] **步驟 3：在 `sessions.py` 加入 middleware 與 Cookie helper**

```python
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from config import IS_PRODUCTION, SESSION_COOKIE_NAME, SESSION_IDLE_SECONDS


def set_session_cookie(response: Response, token: str) -> None:
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
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax")


class SessionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        request.state.session = await resolve_session(token)
        request.state.suppress_session_refresh = False
        response = await call_next(request)
        context = request.state.session
        if context and context.refresh_cookie and not request.state.suppress_session_refresh:
            set_session_cookie(response, context.token)
        return response


def optional_current_user(request: Request) -> dict | None:
    context = getattr(request.state, "session", None)
    return context.user if context else None


def require_current_user(request: Request) -> dict:
    user = optional_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="AUTHENTICATION_REQUIRED")
    return user
```

- [ ] **步驟 4：在 `main.py` 註冊 middleware 與身份端點**

```python
from fastapi import Depends
from fastapi.responses import RedirectResponse
from sessions import (
    SecurityStoreUnavailable,
    SessionMiddleware,
    clear_session_cookie,
    create_session,
    optional_current_user,
    require_current_user,
    revoke_session,
    set_session_cookie,
)

app.add_middleware(SessionMiddleware)


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else ""


@app.post("/api/auth/login")
async def auth_login(request: Request, data: dict):
    await check_rate_limit(request, 5, 60)
    try:
        user = await login_user((data.get("display_name") or "").strip(), data.get("password") or "")
        token = await create_session(
            user,
            user_agent=request.headers.get("user-agent", ""),
            request_ip=_request_ip(request),
        )
    except SecurityStoreUnavailable:
        return JSONResponse({"error": "AUTH_SERVICE_UNAVAILABLE"}, 503)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    response = JSONResponse({"ok": True, "user": normalize_user_row(user)})
    set_session_cookie(response, token)
    return response


@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(require_current_user)):
    return {"ok": True, "user": normalize_user_row(user)}


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    await revoke_session(token)
    request.state.suppress_session_refresh = True
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response
```

把 `/` 改成未登入重新導向：

```python
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    await check_rate_limit(request, 60, 60)
    if not optional_current_user(request):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_page("index.html"))
```

- [ ] **步驟 5：執行路由與 smoke 測試**

```powershell
python -m pytest tests/test_session_auth.py::SessionRouteTests tests/test_smoke.py -v
```

預期：Session 路由測試通過；原 smoke test 的首頁未登入預期需要在本任務調整為 `303 /login`，其餘既有天氣 baseline 可獨立保留。

- [ ] **步驟 6：提交 FastAPI Session 邊界**

```powershell
git add sessions.py main.py tests/test_session_auth.py tests/test_smoke.py
git commit -m "feat: issue and resolve secure session cookies"
```

### 任務 5：前端只從伺服器恢復身份

**檔案：**
- 修改：`static/supabase.js`
- 修改：`static/app.js`
- 修改：`templates/login.html`
- 修改：`templates/register.html`
- 修改測試：`tests/test_session_auth.py`

- [ ] **步驟 1：先寫前端身份來源測試**

```python
class FrontendSessionTests(unittest.TestCase):
    def test_frontend_restores_identity_only_from_auth_me(self):
        backend = Path("static/supabase.js").read_text(encoding="utf-8")
        app_js = Path("static/app.js").read_text(encoding="utf-8")
        login = Path("templates/login.html").read_text(encoding="utf-8")
        register = Path("templates/register.html").read_text(encoding="utf-8")

        self.assertIn('requestJson("/api/auth/me")', backend)
        self.assertIn('requestJson("/api/auth/logout", { method: "POST" })', backend)
        self.assertIn("await FB.getCurrentUser()", app_js)
        self.assertIn("await FB.logout()", app_js)
        self.assertNotIn("RE_LIFE_CURRENT_USER", login)
        self.assertNotIn("RE_LIFE_CURRENT_USER", register)
```

- [ ] **步驟 2：確認前端測試紅燈**

```powershell
python -m pytest tests/test_session_auth.py::FrontendSessionTests -v
```

預期：因 `/api/auth/me`、登出呼叫尚未接入，以及登入／註冊仍寫入身份 `localStorage` 而失敗。

- [ ] **步驟 3：在 `static/supabase.js` 加入 Session 方法**

所有 fetch 明確使用同源 credential：

```javascript
const init = {
    method,
    credentials: "same-origin",
    headers: { Accept: "application/json" },
};
```

`requestFormJson()` 的 fetch 同樣加入 `credentials: "same-origin"`。在 `FB` 新增：

```javascript
async getCurrentUser() {
    const data = await requestJson("/api/auth/me");
    return normalizeUser(data.user);
},

async logout() {
    await requestJson("/api/auth/logout", { method: "POST" });
},
```

- [ ] **步驟 4：把 `initAccounts()` 改為只依靠 `/api/auth/me`**

```javascript
async function initAccounts() {
    if (typeof FB === 'undefined') {
        setTimeout(initAccounts, 500);
        return;
    }
    try {
        const user = await FB.getCurrentUser();
        state.currentUser = user.displayName;
        state.userId = user.id;
        state.userKey = user.public_id || user.userId || null;
        state.spentPoints = user.spent_points || 0;
        state.earnedPoints = user.earned_points || 0;
        state.claimedCoupons = user.claimed_coupons || [];
        state.userAvatar = user.photoUrl || '👤';
    } catch (error) {
        if (error.status === 401) {
            window.location.replace('/login');
            return;
        }
        throw error;
    }
    updateHeaderUI();
}
```

登出確認 callback 改為：

```javascript
showConfirm(tr('confirmLogout'), async () => {
    try {
        await FB.logout();
    } finally {
        resetSessionState();
        window.location.replace('/login');
    }
});
```

登入與註冊模板刪除所有 `RE_LIFE_CURRENT_USER*` 寫入，成功後直接 `window.location.replace('/')`。

- [ ] **步驟 5：重新執行前端身份測試**

```powershell
python -m pytest tests/test_session_auth.py::FrontendSessionTests -v
```

預期：全部通過。

- [ ] **步驟 6：提交前端 Session 恢復**

```powershell
git add static/supabase.js static/app.js templates/login.html templates/register.html tests/test_session_auth.py
git commit -m "fix: restore browser identity from server session"
```

### 任務 6：完成第一階段驗證

**檔案：**
- 不新增正式程式碼；只在失敗時修正本計畫涉及的檔案。

- [ ] **步驟 1：執行聚焦安全測試**

```powershell
python -m pytest tests/test_security_config.py tests/test_session_auth.py -v
```

預期：全部通過，沒有 warning 或未處理例外。

- [ ] **步驟 2：執行相關既有測試**

```powershell
python -m pytest tests/test_rate_limit_kv.py tests/test_email_resend.py tests/test_records_scope.py -v
```

預期：與新 Session 邊界相容；任何因舊 `localStorage` 身份 assertion 失敗的測試必須更新為 `/api/auth/me` 的新安全行為。

- [ ] **步驟 3：執行完整測試並記錄 baseline**

```powershell
python -m pytest tests -v
```

預期：沒有新增失敗；既有天氣 UI assertion 如仍失敗，明確標記為本階段前已存在且無關安全工作。

- [ ] **步驟 4：檢查差異與秘密洩漏**

```powershell
git diff --check
rg -n "raw-secret-token|rel_session=.*token|password.*print|cookie.*print" . --glob '!node_modules/**' --glob '!.git/**'
```

預期：`git diff --check` 無輸出；搜尋只命中測試 fixture，不命中正式日誌或回應。

- [ ] **步驟 5：提交第一階段驗證調整**

```powershell
git add sessions.py config.py auth.py main.py static/supabase.js static/app.js templates/login.html templates/register.html supabase_schema.sql tests/test_security_config.py tests/test_session_auth.py tests/test_smoke.py tests/test_rate_limit_kv.py tests/test_email_resend.py tests/test_records_scope.py
git commit -m "test: verify secure session authentication"
```
