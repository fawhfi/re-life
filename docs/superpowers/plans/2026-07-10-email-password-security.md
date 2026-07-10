# 電郵驗證與密碼重設安全實作計畫

> **給代理工作者：** 必須逐項使用 `superpowers:subagent-driven-development`（建議）或 `superpowers:executing-plans` 執行本計畫。每個驗證碼、登入及重設行為都先以失敗測試證明漏洞或缺失，再作最小修復。

**目標：** 讓帳戶只能在成功消耗電郵驗證碼後建立，統一登入錯誤、防止帳戶枚舉，並在密碼重設後撤銷全部 Session。

**架構：** 驗證碼使用密碼學安全亂數及專用 HMAC secret；代碼記錄追蹤期限、嘗試次數及消耗狀態。註冊端點一次完成驗證碼消耗、帳戶建立及 Session 簽發。

**技術棧：** Python `secrets`／`hmac`、Argon2、Supabase、Resend、Redis／Upstash、FastAPI、pytest。

---

## 檔案配置

- 修改 `config.py`、`template.env`：驗證碼 secret、期限、嘗試上限及正式環境開關。
- 修改 `auth.py`：安全代碼產生、HMAC digest、嘗試限制、登入錯誤、Argon2 rehash、重設流程。
- 修改 `main.py`：註冊直接消耗代碼、移除 `/api/verify-code`、統一忘記密碼回應、撤銷 Session。
- 修改 `templates/register.html`、`templates/login.html`、`static/supabase.js`：配合新註冊及登入錯誤語義。
- 修改 `supabase_schema.sql`：限制驗證碼嘗試與消耗查詢索引。
- 新增 `tests/test_email_auth_security.py`：註冊、登入、重設、開發碼與限流測試。

### 任務 1：加入驗證碼安全設定與 HMAC digest

**檔案：**
- 修改：`config.py`
- 修改：`template.env`
- 修改：`auth.py`
- 新增測試：`tests/test_email_auth_security.py`

- [ ] **步驟 1：先寫 HMAC、密碼學亂數及正式環境設定測試**

```python
import hashlib
import hmac
import importlib
import os
import unittest
from unittest.mock import patch

import auth
import config


class VerificationCodeSecurityTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)
        importlib.reload(auth)

    def test_code_digest_uses_dedicated_hmac_secret(self):
        with patch.object(auth, "AUTH_CODE_SECRET", "test-pepper"):
            digest = auth._code_digest("verify", "user@example.com", "123456")
        expected = hmac.new(
            b"test-pepper",
            b"verify:user@example.com:123456",
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(digest, expected)

    def test_code_generation_uses_secrets_module(self):
        with patch.object(auth.secrets, "randbelow", return_value=12345):
            self.assertEqual(auth._generate_code(), "112345")

    def test_production_requires_auth_code_secret(self):
        with patch.dict(os.environ, {"APP_ENV": "production", "AUTH_CODE_SECRET": ""}, clear=False):
            reloaded = importlib.reload(config)
        with self.assertRaisesRegex(RuntimeError, "AUTH_CODE_SECRET"):
            reloaded.validate_auth_security_settings()
```

- [ ] **步驟 2：執行測試並確認紅燈**

```powershell
python -m pytest tests/test_email_auth_security.py::VerificationCodeSecurityTests -v
```

預期：`AUTH_CODE_SECRET`、`_generate_code()` 及設定驗證函式尚不存在；現有 digest 只是未加密 SHA-256。

- [ ] **步驟 3：在 `config.py` 新增設定與驗證函式**

```python
AUTH_CODE_SECRET = os.getenv("AUTH_CODE_SECRET", "") or (
    "re-life-development-only-auth-code-secret" if IS_DEVELOPMENT else ""
)
VERIFICATION_CODE_EXPIRY = max(60, int(os.getenv("VERIFICATION_CODE_EXPIRY_SECONDS", "600")))
AUTH_CODE_MAX_ATTEMPTS = max(1, int(os.getenv("AUTH_CODE_MAX_ATTEMPTS", "5")))


def validate_auth_security_settings() -> None:
    if not IS_PRODUCTION:
        return
    missing = []
    if len(AUTH_CODE_SECRET) < 32:
        missing.append("AUTH_CODE_SECRET")
    if not RESEND_API_KEY:
        missing.append("RESEND_API_KEY")
    if not RESEND_FROM:
        missing.append("RESEND_FROM")
    if missing:
        raise RuntimeError("Missing production auth settings: " + ", ".join(missing))
```

在 `template.env` 加入中文註解與空值：

```dotenv
# 正式環境使用至少 32 個隨機字元；不可與 Supabase key 共用
AUTH_CODE_SECRET=
VERIFICATION_CODE_EXPIRY_SECONDS=600
AUTH_CODE_MAX_ATTEMPTS=5
APP_ENV=development
ALLOW_DEV_AUTH_CODES=false
```

- [ ] **步驟 4：在 `auth.py` 改用 HMAC 及 `secrets`**

```python
import secrets

from config import AUTH_CODE_MAX_ATTEMPTS, AUTH_CODE_SECRET, IS_DEVELOPMENT


class AuthDependencyUnavailable(RuntimeError):
    pass


def _generate_code() -> str:
    return f"{100000 + secrets.randbelow(900000):06d}"


def _code_digest(purpose: str, email: str, code: str) -> str:
    if not AUTH_CODE_SECRET:
        raise RuntimeError("AUTH_CODE_SECRET is required")
    payload = f"{purpose}:{email}:{code}".encode("utf-8")
    return hmac.new(AUTH_CODE_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
```

把 `random.randint()` 產生驗證碼的所有位置改成 `_generate_code()`。

- [ ] **步驟 5：重新執行安全設定測試**

```powershell
python -m pytest tests/test_email_auth_security.py::VerificationCodeSecurityTests -v
```

預期：全部通過。

- [ ] **步驟 6：提交驗證碼基礎設定**

```powershell
git add config.py template.env auth.py tests/test_email_auth_security.py
git commit -m "fix: protect auth codes with dedicated HMAC secret"
```

### 任務 2：限制驗證碼嘗試並明確消耗代碼

**檔案：**
- 修改：`auth.py`
- 修改：`supabase_schema.sql`
- 修改測試：`tests/test_email_auth_security.py`

- [ ] **步驟 1：先寫過期、五次錯誤、重用及重送測試**

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock


class VerificationAttemptTests(unittest.IsolatedAsyncioTestCase):
    async def test_fifth_wrong_attempt_consumes_code(self):
        row = {
            "id": 1,
            "purpose": "verify",
            "email": "user@example.com",
            "code_hash": "wrong",
            "attempts": 4,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "consumed_at": None,
        }
        with patch.object(auth, "AUTH_CODE_SECRET", "x" * 32), \
             patch.object(auth, "_fetch_code_row", new=AsyncMock(return_value=row)), \
             patch.object(auth, "supabase_enabled", return_value=True), \
             patch.object(auth, "supabase_update", new=AsyncMock()) as update:
            result = await auth.consume_code("verify", "user@example.com", "123456")

        self.assertFalse(result)
        values = update.await_args.args[1]
        self.assertEqual(values["attempts"], 5)
        self.assertIsNotNone(values["consumed_at"])

    async def test_valid_code_is_consumed_once(self):
        email = "user@example.com"
        with patch.object(auth, "AUTH_CODE_SECRET", "x" * 32):
            digest = auth._code_digest("verify", email, "123456")
        row = {
            "id": 1,
            "purpose": "verify",
            "email": email,
            "code_hash": digest,
            "attempts": 0,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "consumed_at": None,
        }
        with patch.object(auth, "AUTH_CODE_SECRET", "x" * 32), \
             patch.object(auth, "_fetch_code_row", new=AsyncMock(side_effect=[row, {**row, "consumed_at": "now"}])), \
             patch.object(auth, "supabase_enabled", return_value=True), \
             patch.object(auth, "supabase_update", new=AsyncMock()):
            self.assertTrue(await auth.consume_code("verify", email, "123456"))
            self.assertFalse(await auth.consume_code("verify", email, "123456"))
```

- [ ] **步驟 2：確認測試紅燈**

```powershell
python -m pytest tests/test_email_auth_security.py::VerificationAttemptTests -v
```

預期：`consume_code()` 尚不存在，現有錯誤嘗試沒有在第五次使代碼失效。

- [ ] **步驟 3：實作共用代碼消耗函式**

```python
def _code_expired(row: dict) -> bool:
    expires_at = row.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()
    return not expires_at or time.time() >= float(expires_at)


async def consume_code(purpose: str, email: str, code: str) -> bool:
    email = (email or "").strip().lower()
    code = (code or "").strip()
    row = await _fetch_code_row(purpose, email)
    if not row or row.get("consumed_at") or _code_expired(row):
        return False
    attempts = int(row.get("attempts") or 0)
    if attempts >= AUTH_CODE_MAX_ATTEMPTS:
        return False

    valid = hmac.compare_digest(
        str(row.get("code_hash") or ""),
        _code_digest(purpose, email, code),
    )
    if valid:
        values = {"consumed_at": _utc_iso()}
    else:
        attempts += 1
        values = {"attempts": attempts}
        if attempts >= AUTH_CODE_MAX_ATTEMPTS:
            values["consumed_at"] = _utc_iso()

    if supabase_enabled():
        await supabase_update(
            "auth_codes",
            values,
            filters={"id": row["id"]},
            returning=False,
        )
    else:
        row.update(values)
    return valid
```

`_fetch_code_row()` 必須讀取 `id`；記憶體 row 建立時加入：

```python
row = {
    "id": uuid.uuid4().hex,
    "purpose": purpose,
    "email": email,
    "user_id": user_id,
    "code_hash": _code_digest(purpose, email, code),
    "expires_at": _utc_now().timestamp() + VERIFICATION_CODE_EXPIRY,
    "attempts": 0,
    "consumed_at": None,
}
```

`verify_code()` 與 `verify_reset_code()` 改為呼叫 `consume_code()`，不要刪除 row，讓消耗狀態可稽核及阻止重用。

- [ ] **步驟 4：強化 schema constraint 與清理索引**

```sql
alter table public.auth_codes
drop constraint if exists auth_codes_attempts_check;

alter table public.auth_codes
add constraint auth_codes_attempts_check
check (attempts between 0 and 5);

create index if not exists auth_codes_active_lookup_idx
on public.auth_codes (purpose, email, expires_at)
where consumed_at is null;
```

- [ ] **步驟 5：執行嘗試與重用測試**

```powershell
python -m pytest tests/test_email_auth_security.py::VerificationAttemptTests -v
```

預期：全部通過。

- [ ] **步驟 6：提交代碼生命週期修復**

```powershell
git add auth.py supabase_schema.sql tests/test_email_auth_security.py
git commit -m "fix: expire and consume verification codes safely"
```

### 任務 3：註冊端點直接驗證並消耗電郵碼

**檔案：**
- 修改：`auth.py`
- 修改：`main.py`
- 修改：`static/supabase.js`
- 修改：`templates/register.html`
- 修改測試：`tests/test_email_auth_security.py`

- [ ] **步驟 1：先寫註冊繞過回歸測試**

```python
from fastapi.testclient import TestClient
from main import app


class RegistrationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_register_without_code_is_rejected(self):
        response = self.client.post("/api/auth/register", json={
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "correct-pass",
        })
        self.assertEqual(response.status_code, 422)

    def test_invalid_code_cannot_create_account(self):
        with patch("main.consume_code", new=AsyncMock(return_value=False)), \
             patch("main.create_user", new=AsyncMock()) as create:
            response = self.client.post("/api/auth/register", json={
                "display_name": "Alice",
                "email": "alice@example.com",
                "password": "correct-pass",
                "code": "000000",
            })
        self.assertEqual(response.status_code, 400)
        create.assert_not_awaited()

    def test_verified_registration_creates_session(self):
        user = {"id": 7, "displayName": "Alice", "email": "alice@example.com"}
        with patch("main.consume_code", new=AsyncMock(return_value=True)), \
             patch("main.create_user", new=AsyncMock(return_value=user)), \
             patch("main.create_session", new=AsyncMock(return_value="token")):
            response = self.client.post("/api/auth/register", json={
                "display_name": "Alice",
                "email": "alice@example.com",
                "password": "correct-pass",
                "code": "123456",
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn("rel_session=token", response.headers.get("set-cookie", ""))
```

- [ ] **步驟 2：確認註冊測試紅燈**

```powershell
python -m pytest tests/test_email_auth_security.py::RegistrationBoundaryTests -v
```

預期：無 code 仍可建立帳戶，`/api/verify-code` 與建立帳戶仍分開。

- [ ] **步驟 3：讓 `create_user()` 只能建立已驗證電郵帳戶**

把簽名改為必須提供 email，並統一八字元密碼：

```python
async def create_user(display_name: str, password: str, email: str) -> dict:
    display_name = (display_name or "").strip()
    email = (email or "").strip().lower()
    if len(display_name) < 2:
        raise ValueError("USERNAME_TOO_SHORT")
    if len(password or "") < 8:
        raise ValueError("PASSWORD_TOO_SHORT")
    if not email or "@" not in email:
        raise ValueError("EMAIL_REQUIRED")
    if await get_user_by_name(display_name):
        raise ValueError("USERNAME_TAKEN")
    if await get_user_by_email(email):
        raise ValueError("EMAIL_TAKEN")
    payload = {
        "display_name": display_name,
        "email": email,
        "password_hash": PASSWORD_HASHER.hash(password),
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
    if not IS_DEVELOPMENT:
        raise AuthDependencyUnavailable("Persistent user storage unavailable")
    return normalize_user_row(_memory_store_user(payload))
```

- [ ] **步驟 4：重寫 `/api/auth/register` 並移除 `/api/verify-code`**

```python
@app.post("/api/auth/register")
async def auth_register(request: Request, data: dict):
    await check_rate_limit(request, 5, 60, subject=(data.get("email") or "").strip().lower())
    display_name = (data.get("display_name") or data.get("displayName") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    code = (data.get("code") or "").strip()
    if not display_name or not email or len(password) < 8 or len(code) != 6:
        return JSONResponse({"error": "INVALID_REGISTRATION_INPUT"}, 422)
    if await get_user_by_name(display_name):
        return JSONResponse({"error": "USERNAME_TAKEN"}, 400)
    if await get_user_by_email(email):
        return JSONResponse({"error": "EMAIL_TAKEN"}, 400)
    if not await consume_code("verify", email, code):
        return JSONResponse({"error": "INVALID_OR_EXPIRED_CODE"}, 400)
    try:
        user = await create_user(display_name, password, email)
        token = await create_session(
            user,
            user_agent=request.headers.get("user-agent", ""),
            request_ip=_request_ip(request),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    response = JSONResponse({"ok": True, "user": user})
    set_session_cookie(response, token)
    return response
```

完全刪除 `/api/verify-code` 路由及未再使用的 import。

- [ ] **步驟 5：更新前端註冊請求**

`static/supabase.js`：

```javascript
async createUser(displayName, password, email, code) {
    const data = await requestJson("/api/auth/register", {
        method: "POST",
        body: { display_name: displayName, email, password, code },
    });
    return normalizeUser(data.user);
},
```

`templates/register.html` 的 `handleVerify()` 不再先呼叫 `/api/verify-code`，直接：

```javascript
const user = await window.FB.createUser(
    pendingUsername,
    pendingPassword,
    pendingEmail,
    code,
);
window.location.replace('/');
```

- [ ] **步驟 6：執行註冊安全測試**

```powershell
python -m pytest tests/test_email_auth_security.py::RegistrationBoundaryTests -v
```

預期：全部通過。

- [ ] **步驟 7：提交不可繞過的註冊邊界**

```powershell
git add auth.py main.py static/supabase.js templates/register.html tests/test_email_auth_security.py
git commit -m "fix: require email code during account creation"
```

### 任務 4：統一登入錯誤並更新 Argon2 hash

**檔案：**
- 修改：`auth.py`
- 修改：`main.py`
- 修改：`templates/login.html`
- 修改測試：`tests/test_email_auth_security.py`

- [ ] **步驟 1：先寫帳戶枚舉與 rehash 測試**

```python
class LoginSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_user_and_wrong_password_share_error(self):
        with patch.object(auth, "get_user_by_name", new=AsyncMock(return_value=None)):
            with self.assertRaisesRegex(ValueError, "INVALID_CREDENTIALS"):
                await auth.login_user("missing", "password")

        row = {"id": 7, "display_name": "Alice", "password_hash": auth.PASSWORD_HASHER.hash("right-password")}
        with patch.object(auth, "get_user_by_name", new=AsyncMock(return_value={"id": 7})), \
             patch.object(auth, "_resolve_user_row", new=AsyncMock(return_value=row)):
            with self.assertRaisesRegex(ValueError, "INVALID_CREDENTIALS"):
                await auth.login_user("Alice", "wrong-password")

    async def test_successful_login_rehashes_when_needed(self):
        row = {"id": 7, "display_name": "Alice", "password_hash": "old-hash"}
        with patch.object(auth, "get_user_by_name", new=AsyncMock(return_value={"id": 7})), \
             patch.object(auth, "_resolve_user_row", new=AsyncMock(return_value=row)), \
             patch.object(auth.PASSWORD_HASHER, "verify", return_value=True), \
             patch.object(auth.PASSWORD_HASHER, "check_needs_rehash", return_value=True), \
             patch.object(auth.PASSWORD_HASHER, "hash", return_value="new-hash"), \
             patch.object(auth, "supabase_enabled", return_value=True), \
             patch.object(auth, "supabase_update", new=AsyncMock()) as update:
            await auth.login_user("Alice", "right-password")
        update.assert_awaited_once_with("app_users", {"password_hash": "new-hash"}, filters={"id": 7})
```

- [ ] **步驟 2：確認登入測試紅燈**

```powershell
python -m pytest tests/test_email_auth_security.py::LoginSecurityTests -v
```

預期：現有錯誤分別為 `USER_NOT_FOUND`／`WRONG_PASSWORD`，且沒有 rehash。

- [ ] **步驟 3：修正 `login_user()`**

```python
async def login_user(display_name: str, password: str) -> dict:
    display_name = (display_name or "").strip()
    public_user = await get_user_by_name(display_name)
    row = await _resolve_user_row(public_user["id"]) if public_user else None
    stored_hash = (row or {}).get("password_hash")
    if not stored_hash:
        raise ValueError("INVALID_CREDENTIALS")
    try:
        PASSWORD_HASHER.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError):
        raise ValueError("INVALID_CREDENTIALS") from None
    if PASSWORD_HASHER.check_needs_rehash(stored_hash):
        new_hash = PASSWORD_HASHER.hash(password)
        if supabase_enabled():
            await supabase_update("app_users", {"password_hash": new_hash}, filters={"id": row["id"]})
        else:
            row["password_hash"] = new_hash
    return normalize_user_row(row)
```

`main.py` 對 `INVALID_CREDENTIALS` 回傳 `401`；`templates/login.html` 只顯示同一個一般錯誤訊息，不再分辨帳戶不存在或密碼錯誤。

- [ ] **步驟 4：重新執行登入測試**

```powershell
python -m pytest tests/test_email_auth_security.py::LoginSecurityTests -v
```

預期：全部通過。

- [ ] **步驟 5：提交登入防枚舉修復**

```powershell
git add auth.py main.py templates/login.html tests/test_email_auth_security.py
git commit -m "fix: prevent login account enumeration"
```

### 任務 5：重設密碼後撤銷全部 Session

**檔案：**
- 修改：`auth.py`
- 修改：`main.py`
- 修改測試：`tests/test_email_auth_security.py`

- [ ] **步驟 1：先寫忘記密碼一致回應與撤銷測試**

```python
class PasswordResetSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_forgot_password_response_does_not_enumerate_accounts(self):
        with patch("main.send_reset_code", new=AsyncMock(return_value=None)):
            known = self.client.post("/api/forgot-password", json={"email": "known@example.com"})
            unknown = self.client.post("/api/forgot-password", json={"email": "unknown@example.com"})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())

    def test_successful_reset_revokes_all_user_sessions(self):
        user = {"id": 7, "email": "user@example.com"}
        with patch("main.verify_reset_code", new=AsyncMock(return_value=user)), \
             patch("main.update_password", new=AsyncMock(return_value=True)), \
             patch("main.revoke_all_user_sessions", new=AsyncMock()) as revoke:
            response = self.client.post("/api/reset-password", json={
                "email": "user@example.com",
                "code": "123456",
                "password": "new-password",
            })
        self.assertEqual(response.status_code, 200)
        revoke.assert_awaited_once_with(7)
```

- [ ] **步驟 2：確認重設測試紅燈**

```powershell
python -m pytest tests/test_email_auth_security.py::PasswordResetSecurityTests -v
```

預期：成功重設後沒有撤銷 Session；已知與未知帳戶可能走不同內部分支或輸出。

- [ ] **步驟 3：統一忘記密碼路由**

```python
@app.post("/api/forgot-password")
async def forgot_password(request: Request, data: dict):
    email = (data.get("email") or "").strip().lower()
    await check_rate_limit(request, 3, 120, subject=email)
    if email and "@" in email:
        await send_reset_code(email)
    return JSONResponse({"ok": True})
```

`send_reset_code()` 在帳戶不存在時直接回傳 `None`，但不得向 route 洩漏差異。正式環境寄送失敗由共用安全錯誤轉成 `503`。

- [ ] **步驟 4：重設成功後撤銷全部 Session**

```python
@app.post("/api/reset-password")
async def reset_password(request: Request, data: dict):
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    password = data.get("password") or ""
    await check_rate_limit(request, 5, 60, subject=email)
    if not email or len(code) != 6 or len(password) < 8:
        return JSONResponse({"error": "INVALID_RESET_INPUT"}, 422)
    user = await verify_reset_code(email, code)
    if not user:
        return JSONResponse({"error": "INVALID_OR_EXPIRED_CODE"}, 400)
    if not await update_password(email, password):
        return JSONResponse({"error": "PASSWORD_UPDATE_FAILED"}, 503)
    await revoke_all_user_sessions(int(user["id"]))
    request.state.suppress_session_refresh = True
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response
```

- [ ] **步驟 5：執行密碼重設測試**

```powershell
python -m pytest tests/test_email_auth_security.py::PasswordResetSecurityTests -v
```

預期：全部通過。

- [ ] **步驟 6：提交密碼重設撤銷**

```powershell
git add auth.py main.py tests/test_email_auth_security.py
git commit -m "fix: revoke sessions after password reset"
```

### 任務 6：限制開發碼並讓正式限流安全失敗

**檔案：**
- 修改：`auth.py`
- 修改：`main.py`
- 修改測試：`tests/test_email_auth_security.py`

- [ ] **步驟 1：先寫正式環境不洩漏代碼及限流故障測試**

```python
class ProductionAuthFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_production_never_returns_dev_code(self):
        with patch.object(auth, "ALLOW_DEV_AUTH_CODES", False), \
             patch.object(auth, "_send_code_email", new=AsyncMock(return_value=False)), \
             patch.object(auth, "_store_code_row", new=AsyncMock()), \
             patch.object(auth, "_generate_code", return_value="123456"):
            with self.assertRaises(auth.AuthDependencyUnavailable):
                await auth.send_verification_code("user@example.com")

    async def test_production_rate_limit_does_not_fall_back_to_memory(self):
        request = type("Request", (), {
            "headers": {"user-agent": "pytest"},
            "client": type("Client", (), {"host": "127.0.0.1"})(),
            "url": type("URL", (), {"path": "/api/auth/login"})(),
        })()
        with patch.object(auth, "IS_PRODUCTION", True), \
             patch.object(auth, "UPSTASH_REDIS_REST_URL", "https://kv.example"), \
             patch.object(auth, "UPSTASH_REDIS_REST_TOKEN", "token"), \
             patch.object(auth, "_kv_command", new=AsyncMock(side_effect=RuntimeError("down"))):
            with self.assertRaises(auth.AuthDependencyUnavailable):
                await auth.check_rate_limit(request, subject="alice")
```

- [ ] **步驟 2：確認正式環境安全失敗測試紅燈**

```powershell
python -m pytest tests/test_email_auth_security.py::ProductionAuthFailureTests -v
```

預期：現有流程回傳 `dev_code` 並退回記憶體限流。

- [ ] **步驟 3：實作一般依賴故障與 subject 限流**

```python
async def check_rate_limit(request, max_requests: int = 5, window_sec: int = 60, subject: str = ""):
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"
    route = request.url.path
    normalized_subject = hashlib.sha256(subject.strip().lower().encode()).hexdigest()[:24] if subject else "none"
    key = f"rl:{ip}:{route}:{normalized_subject}"
    safe_key = key.replace(":", "_").replace("/", "_").replace(".", "_")
    try:
        if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
            created = await _kv_command("SET", safe_key, "1", "EX", str(window_sec), "NX")
            if created == "OK":
                return
            count = int(await _kv_command("INCR", safe_key) or 0)
            if count > max_requests:
                raise HTTPException(status_code=429, detail="RATE_LIMITED")
            return
        if REDIS_URL:
            count = await _redis_rate_count(safe_key, window_sec)
            if count > max_requests:
                raise HTTPException(status_code=429, detail="RATE_LIMITED")
            return
    except HTTPException:
        raise
    except Exception as exc:
        if IS_PRODUCTION:
            raise AuthDependencyUnavailable("Rate limiter unavailable") from exc
    if IS_PRODUCTION:
        raise AuthDependencyUnavailable("Distributed rate limiter is required")
    now = time.time()
    cutoff = now - window_sec
    _rate_limit_store[key] = [seen for seen in _rate_limit_store.get(key, []) if seen > cutoff]
    if len(_rate_limit_store[key]) >= max_requests:
        raise HTTPException(status_code=429, detail="RATE_LIMITED")
    _rate_limit_store[key].append(now)
```

`send_verification_code()`／`send_reset_code()` 只有 `ALLOW_DEV_AUTH_CODES` 為真時回傳代碼；否則寄信失敗便拋出 `AuthDependencyUnavailable`。路由捕捉後統一回傳 `503 {"error":"AUTH_SERVICE_UNAVAILABLE"}`。

- [ ] **步驟 4：執行正式環境安全失敗測試**

```powershell
python -m pytest tests/test_email_auth_security.py::ProductionAuthFailureTests tests/test_rate_limit_kv.py tests/test_email_resend.py -v
```

預期：新安全測試通過；既有測試明確設定開發模式後保持通過。

- [ ] **步驟 5：提交開發碼與限流修復**

```powershell
git add auth.py main.py tests/test_email_auth_security.py tests/test_rate_limit_kv.py tests/test_email_resend.py
git commit -m "fix: fail closed for production auth dependencies"
```

### 任務 7：完成第三階段驗證

**檔案：**
- 不新增正式程式碼；只修正本階段引入的問題。

- [ ] **步驟 1：執行完整認證安全測試**

```powershell
python -m pytest tests/test_session_auth.py tests/test_email_auth_security.py tests/test_rate_limit_kv.py tests/test_email_resend.py -v
```

預期：全部通過。

- [ ] **步驟 2：確認舊繞過字串及公開端點已消失**

```powershell
rg -n "@app.post\(\"/api/verify-code\"|random\.randint\(|USER_NOT_FOUND|WRONG_PASSWORD|returning dev_code fallback" auth.py main.py templates static
```

預期：無正式程式碼命中；測試可保留用於確認舊行為不存在的字串。

- [ ] **步驟 3：執行完整測試**

```powershell
python -m pytest tests -v
```

預期：沒有新增失敗；既有天氣 baseline 獨立報告。

- [ ] **步驟 4：提交驗證調整**

```powershell
git add auth.py config.py main.py template.env templates/login.html templates/register.html static/supabase.js supabase_schema.sql tests/test_email_auth_security.py tests/test_session_auth.py tests/test_rate_limit_kv.py tests/test_email_resend.py
git commit -m "test: verify secure email authentication flows"
```
