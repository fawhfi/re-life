# Supabase 與瀏覽器平台強化實作計畫

> **給代理工作者：** 必須逐項使用 `superpowers:subagent-driven-development`（建議）或 `superpowers:executing-plans` 執行本計畫。每個資料庫、Origin、CSP 或錯誤處理控制都先建立會因控制缺失而失敗的測試。

**目標：** 把 Supabase 收斂為只經 FastAPI service role 存取的後端資料層，並強制正式環境設定、同源請求、可信 Host、CSP、安全 headers 及不洩漏秘密的錯誤與日誌。

**架構：** SQL 啟用 RLS 並撤銷瀏覽器角色權限；FastAPI lifespan 驗證正式環境設定；middleware 依次處理 request ID、可信 Host、Origin、Session、CORS 與安全 headers。前端移除所有 inline script 和 inline event handler，讓 CSP 的 `script-src` 不需要 `'unsafe-inline'`。

**技術棧：** PostgreSQL／Supabase RLS、FastAPI lifespan、Starlette middleware、CSP、原生 JavaScript、pytest。

---

## 檔案配置

- 修改 `supabase_schema.sql`、`supabase/config.toml`，刪除未使用 Edge Functions。
- 修改 `config.py`、`template.env`：正式環境 origins、hosts 及啟動驗證。
- 新增 `web_security.py`：Origin 驗證、安全 headers、request ID 與安全日誌 helper。
- 修改 `main.py`：lifespan、middleware、一般錯誤 handler 及公開設定 allowlist。
- 新增 `static/js/auth-theme-boot.js`、`static/js/login.js`、`static/js/register.js`、`static/js/ui-actions.js`。
- 修改三份 HTML template 及前端 JS，移除 inline script／handler。
- 新增 `tests/test_platform_security.py`、`tests/test_csp_frontend.py`。

### 任務 1：啟用 RLS、private bucket 並移除未使用 Edge Functions

**檔案：**
- 修改：`supabase_schema.sql`
- 修改：`supabase/config.toml`
- 刪除：`supabase/functions/admin_users/index.ts`
- 刪除：`supabase/functions/my_records/index.ts`
- 新增測試：`tests/test_platform_security.py`

- [ ] **步驟 1：先寫資料庫權限與 Edge Function 測試**

```python
from pathlib import Path
import unittest


class SupabaseSecurityTests(unittest.TestCase):
    def test_custom_account_tables_are_not_browser_accessible(self):
        schema = Path("supabase_schema.sql").read_text(encoding="utf-8").lower()
        for table in ("app_users", "app_sessions", "auth_codes", "scan_records"):
            self.assertIn(f"alter table public.{table} enable row level security", schema)
            self.assertIn(f"revoke all on table public.{table} from anon, authenticated", schema)
        self.assertIn("values ('scan-images', 'scan-images', false)", schema)

    def test_unused_identity_edge_functions_are_removed(self):
        config = Path("supabase/config.toml").read_text(encoding="utf-8")
        self.assertNotIn("functions.my_records", config)
        self.assertNotIn("functions.admin_users", config)
        self.assertFalse(Path("supabase/functions/my_records/index.ts").exists())
        self.assertFalse(Path("supabase/functions/admin_users/index.ts").exists())
```

- [ ] **步驟 2：確認測試紅燈**

```powershell
python -m pytest tests/test_platform_security.py::SupabaseSecurityTests -v
```

預期：RLS／revoke 尚不存在，bucket 仍為 public，兩個未使用 function 仍存在。

- [ ] **步驟 3：在 schema 套用後端唯一存取模型**

```sql
alter table public.app_users enable row level security;
alter table public.app_sessions enable row level security;
alter table public.auth_codes enable row level security;
alter table public.scan_records enable row level security;

revoke all on table public.app_users from anon, authenticated;
revoke all on table public.app_sessions from anon, authenticated;
revoke all on table public.auth_codes from anon, authenticated;
revoke all on table public.scan_records from anon, authenticated;

grant all on table public.app_users to service_role;
grant all on table public.app_sessions to service_role;
grant all on table public.auth_codes to service_role;
grant all on table public.scan_records to service_role;

insert into storage.buckets (id, name, public)
values ('scan-images', 'scan-images', false)
on conflict (id) do update
set public = false;
```

不要建立 `anon` 或 `authenticated` policy；自建帳戶沒有 Supabase JWT 可供 RLS 判定身份。

- [ ] **步驟 4：刪除第二套身份路徑**

從 `supabase/config.toml` 移除：

```toml
[functions.my_records]
verify_jwt = true

[functions.admin_users]
verify_jwt = false
```

刪除兩個對應 `index.ts`，保留 `health` 與 `public_config`。

- [ ] **步驟 5：執行 Supabase 安全測試**

```powershell
python -m pytest tests/test_platform_security.py::SupabaseSecurityTests tests/test_schema.py tests/test_supabase_server_sdk.py -v
```

預期：新安全測試通過；舊 Edge Function 文字 assertion 更新為只檢查仍支援的 functions。

- [ ] **步驟 6：提交 Supabase 邊界**

```powershell
git add supabase_schema.sql supabase/config.toml tests/test_platform_security.py tests/test_schema.py tests/test_supabase_server_sdk.py
git add -u -- supabase/functions/admin_users/index.ts supabase/functions/my_records/index.ts
git commit -m "fix: restrict Supabase data to backend service role"
```

### 任務 2：正式環境啟動驗證與公開設定 allowlist

**檔案：**
- 修改：`config.py`
- 修改：`template.env`
- 修改：`main.py`
- 修改測試：`tests/test_platform_security.py`
- 修改測試：`tests/test_config_route.py`

- [ ] **步驟 1：先寫缺少正式設定拒絕啟動與公開設定不洩密測試**

```python
import importlib
import os
from unittest.mock import patch

import config


class ProductionStartupTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)

    def test_production_settings_fail_closed(self):
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "AUTH_CODE_SECRET": "",
            "ALLOWED_ORIGINS": "",
            "ALLOWED_HOSTS": "",
        }, clear=False):
            reloaded = importlib.reload(config)
        with self.assertRaisesRegex(RuntimeError, "SUPABASE_URL"):
            reloaded.validate_production_settings()

    def test_public_config_never_contains_supabase_keys(self):
        from fastapi.testclient import TestClient
        from main import app
        payload = TestClient(app).get("/api/config").json()
        serialized = str(payload).lower()
        self.assertNotIn("supabase", serialized)
        self.assertNotIn("service_role", serialized)
        self.assertNotIn("anonkey", serialized)
```

- [ ] **步驟 2：確認設定測試紅燈**

```powershell
python -m pytest tests/test_platform_security.py::ProductionStartupTests -v
```

預期：`validate_production_settings()` 尚不存在，`/api/config` 仍回傳 Supabase URL／publishable key。

- [ ] **步驟 3：在 `config.py` 解析 origins 與 hosts**

```python
def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


ALLOWED_ORIGINS = _csv_env(
    "ALLOWED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000,http://testserver" if IS_DEVELOPMENT else "",
)
ALLOWED_HOSTS = _csv_env(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost,testserver" if IS_DEVELOPMENT else "",
)


def validate_production_settings() -> None:
    validate_auth_security_settings()
    if not IS_PRODUCTION:
        return
    required = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        "ALLOWED_ORIGINS": ALLOWED_ORIGINS,
        "ALLOWED_HOSTS": ALLOWED_HOSTS,
        "REDIS_OR_UPSTASH": (
            (UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN) or REDIS_URL
        ),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing production security settings: " + ", ".join(missing))


def get_public_config() -> dict[str, object]:
    return {
        "appName": "Re-Life",
        "maxUploadBytes": MAX_UPLOAD_BYTES,
        "supportedLanguages": ["en", "zh_simplified", "zh_traditional"],
    }
```

`SUPABASE_URL` 與 key 直接從環境讀入內部常數，不再經 `PUBLIC_CONFIG` 間接取得。

- [ ] **步驟 4：在 FastAPI lifespan 驗證設定**

```python
from contextlib import asynccontextmanager
from config import validate_production_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_settings()
    yield


app = FastAPI(title="Re-Life API", lifespan=lifespan)
```

`template.env` 加入中文註解的 `ALLOWED_ORIGINS`、`ALLOWED_HOSTS` 範例；不得填入真實秘密。

- [ ] **步驟 5：執行啟動與公開設定測試**

```powershell
python -m pytest tests/test_platform_security.py::ProductionStartupTests tests/test_config_route.py -v
```

預期：全部通過。

- [ ] **步驟 6：提交正式設定驗證**

```powershell
git add config.py template.env main.py tests/test_platform_security.py tests/test_config_route.py
git commit -m "fix: validate production security configuration"
```

### 任務 3：強制可信 Host、同源 CORS 與 Origin 驗證

**檔案：**
- 新增：`web_security.py`
- 修改：`main.py`
- 修改測試：`tests/test_platform_security.py`

- [ ] **步驟 1：先寫 Host、CORS 與 CSRF Origin 測試**

```python
from fastapi.testclient import TestClient
from main import app


class RequestBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://testserver")

    def test_untrusted_host_is_rejected(self):
        response = self.client.get("/api/config", headers={"host": "evil.example"})
        self.assertEqual(response.status_code, 400)

    def test_state_change_requires_allowed_origin(self):
        response = self.client.post(
            "/api/auth/logout",
            headers={"origin": "https://evil.example"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "INVALID_ORIGIN"})

    def test_allowed_origin_reaches_route(self):
        response = self.client.post(
            "/api/auth/logout",
            headers={"origin": "http://testserver"},
        )
        self.assertNotEqual(response.status_code, 403)

    def test_cors_does_not_reflect_unknown_origin(self):
        response = self.client.options(
            "/api/auth/login",
            headers={
                "origin": "https://evil.example",
                "access-control-request-method": "POST",
            },
        )
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "https://evil.example")
```

- [ ] **步驟 2：確認請求邊界測試紅燈**

```powershell
python -m pytest tests/test_platform_security.py::RequestBoundaryTests -v
```

預期：Host 未限制，unsafe method 未驗證 Origin，CORS 清單仍硬編碼於 `main.py`。

- [ ] **步驟 3：新增 `web_security.py` Origin middleware**

```python
"""Browser and request-boundary security middleware."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class OriginValidationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, allowed_origins: tuple[str, ...]):
        super().__init__(app)
        self.allowed_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)

    async def dispatch(self, request, call_next):
        if request.method not in SAFE_METHODS:
            origin = (request.headers.get("origin") or "").rstrip("/")
            if origin not in self.allowed_origins:
                return JSONResponse({"error": "INVALID_ORIGIN"}, status_code=403)
        return await call_next(request)
```

- [ ] **步驟 4：在 `main.py` 使用設定清單**

```python
from starlette.middleware.trustedhost import TrustedHostMiddleware
from config import ALLOWED_HOSTS, ALLOWED_ORIGINS
from web_security import OriginValidationMiddleware

app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ALLOWED_HOSTS))
app.add_middleware(OriginValidationMiddleware, allowed_origins=ALLOWED_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)
```

刪除硬編碼 localhost origins 及 `allow_headers=["*"]`。

- [ ] **步驟 5：讓所有測試中的修改請求明確提供同源 Origin**

在 `tests/test_session_auth.py`、`tests/test_account_authorization.py`、`tests/test_record_authorization.py`、`tests/test_email_auth_security.py`、`tests/test_image_security.py` 及其他使用 `TestClient` 的修改請求加入：

```python
SAME_ORIGIN = {"origin": "http://testserver"}

response = self.client.post(
    "/api/auth/logout",
    headers=SAME_ORIGIN,
    cookies={"rel_session": "token"},
)
```

`PATCH`、`DELETE` 及 multipart `POST` 同樣加入 `headers=SAME_ORIGIN`。不要在 production middleware 為測試加入跳過分支；測試必須走真實 Origin 邊界。

- [ ] **步驟 6：執行請求邊界與既有安全測試**

```powershell
python -m pytest tests/test_platform_security.py::RequestBoundaryTests tests/test_session_auth.py tests/test_account_authorization.py tests/test_record_authorization.py tests/test_email_auth_security.py tests/test_image_security.py -v
```

預期：全部通過。

- [ ] **步驟 7：提交 Host／Origin／CORS 防護**

```powershell
git add web_security.py main.py tests/test_platform_security.py tests/test_session_auth.py tests/test_account_authorization.py tests/test_record_authorization.py tests/test_email_auth_security.py tests/test_image_security.py
git commit -m "fix: enforce trusted hosts and same-origin mutations"
```

### 任務 4：把登入與註冊頁 inline JavaScript 移至外部檔案

**檔案：**
- 新增：`static/js/auth-theme-boot.js`
- 新增：`static/js/login.js`
- 新增：`static/js/register.js`
- 修改：`templates/login.html`
- 修改：`templates/register.html`
- 新增測試：`tests/test_csp_frontend.py`

- [ ] **步驟 1：先寫 auth page 無 inline script／handler 測試**

```python
from pathlib import Path
import re
import unittest


class AuthPageCspTests(unittest.TestCase):
    def test_auth_pages_have_no_inline_scripts_or_event_handlers(self):
        for name in ("login.html", "register.html"):
            html = Path("templates", name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.I))
            self.assertIsNone(re.search(r"\son[a-z]+\s*=", html, re.I))

    def test_auth_logic_is_loaded_from_self_hosted_files(self):
        login = Path("templates/login.html").read_text(encoding="utf-8")
        register = Path("templates/register.html").read_text(encoding="utf-8")
        self.assertIn('/static/js/login.js', login)
        self.assertIn('/static/js/register.js', register)
        self.assertIn('/static/js/auth-theme-boot.js', login)
        self.assertIn('/static/js/auth-theme-boot.js', register)
```

- [ ] **步驟 2：確認 auth CSP 測試紅燈**

```powershell
python -m pytest tests/test_csp_frontend.py::AuthPageCspTests -v
```

預期：兩頁均有 inline `<script>`、`onclick`、`onchange` 或 `onsubmit`。

- [ ] **步驟 3：移動 theme boot script**

把兩頁頂部讀取主題的 inline script 移到 `static/js/auth-theme-boot.js`：

```javascript
(() => {
    const theme = localStorage.getItem('RE_LIFE_THEME') || 'light';
    document.documentElement.dataset.theme = theme;
})();
```

HTML 以阻塞式 self-hosted script 載入，避免主題閃爍：

```html
<script src="/static/js/auth-theme-boot.js"></script>
```

- [ ] **步驟 4：把登入頁 inline script 完整移至 `static/js/login.js`**

移動原有翻譯、登入、忘記密碼與重設流程函式，不改變其 DOM ID；在檔案底部以事件監聽器連接：

```javascript
document.getElementById('login-form')?.addEventListener('submit', handleLogin);
document.getElementById('forgot-link')?.addEventListener('click', showForgotForm);
document.getElementById('forgot-btn')?.addEventListener('click', handleForgotStep);
document.getElementById('login-lang-select')?.addEventListener('change', event => setLoginLang(event.target.value));
document.querySelector('[data-auth-theme-select]')?.addEventListener('change', event => applyAuthTheme(event.target.value));
applyLoginLanguage();
```

從 HTML 刪除對應 inline script 與所有 `onclick`／`onchange`，加入：

```html
<script src="/static/supabase.js" defer></script>
<script src="/static/js/auth-theme.js" defer></script>
<script src="/static/js/auth-lang.js" defer></script>
<script src="/static/js/login.js" defer></script>
```

- [ ] **步驟 5：把註冊頁 inline script 完整移至 `static/js/register.js`**

移動原有變數及 `handleRegister()`、`handleVerify()`、`goBack()`、語言函式；底部連接：

```javascript
document.getElementById('register-form')?.addEventListener('submit', handleRegister);
document.getElementById('verify-form')?.addEventListener('submit', handleVerify);
document.getElementById('verify-back-btn')?.addEventListener('click', goBack);
document.getElementById('register-lang-select')?.addEventListener('change', event => setRegisterLang(event.target.value));
document.querySelector('[data-auth-theme-select]')?.addEventListener('change', event => applyAuthTheme(event.target.value));
applyRegisterLanguage();
```

為返回按鈕加入 `id="verify-back-btn"`，刪除所有 inline handler，載入 `register.js`。

- [ ] **步驟 6：執行 auth CSP 與既有 auth UI 測試**

```powershell
python -m pytest tests/test_csp_frontend.py::AuthPageCspTests tests/test_auth_theme.py tests/test_perf_mode.py -v
```

預期：全部通過。

- [ ] **步驟 7：提交 auth page 外部 script**

```powershell
git add static/js/auth-theme-boot.js static/js/login.js static/js/register.js templates/login.html templates/register.html tests/test_csp_frontend.py tests/test_auth_theme.py tests/test_perf_mode.py
git commit -m "fix: remove inline scripts from auth pages"
```

### 任務 5：移除主頁與動態內容的 inline event handler

**檔案：**
- 新增：`static/js/ui-actions.js`
- 修改：`templates/index.html`
- 修改：`static/app.js`
- 修改：`static/js/app-records.js`
- 修改：`static/js/app-weather.js`
- 修改：`static/js/app-recycling.js`
- 修改測試：`tests/test_csp_frontend.py`

- [ ] **步驟 1：先寫整個前端無 inline handler 測試**

```python
class MainPageCspTests(unittest.TestCase):
    def test_templates_and_generated_markup_have_no_inline_handlers(self):
        files = [
            Path("templates/index.html"),
            Path("static/app.js"),
            Path("static/js/app-records.js"),
            Path("static/js/app-weather.js"),
            Path("static/js/app-recycling.js"),
        ]
        pattern = re.compile(r"\bon(?:click|change|submit|input|error)\s*=", re.I)
        for path in files:
            self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), str(path))

    def test_main_template_loads_action_dispatcher(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")
        self.assertIn('/static/js/ui-actions.js', html)
```

- [ ] **步驟 2：確認主頁 CSP 測試紅燈**

```powershell
python -m pytest tests/test_csp_frontend.py::MainPageCspTests -v
```

預期：template 與多個動態 HTML 字串含 inline handler。

- [ ] **步驟 3：新增集中事件分派器**

`static/js/ui-actions.js`：

```javascript
const UI_ACTIONS = {
    'avatar': () => handleAvatarClick(),
    'weather-toggle': () => toggleWeatherDetails(),
    'weather-close': () => closeWeatherDetails(),
    'scan-mode': element => startScanningMode(element.dataset.mode),
    'upload-zone': () => zoneTap(),
    'upload-trigger': () => triggerUpload(),
    'preview-clear': () => clearPreview(),
    'recycling-refresh': () => refreshNearbyRecyclingPoints(),
    'swap-complete': () => completeSwapFlow(),
    'scan-reset': () => resetScan(),
    'record-add': () => addScanToRecord(),
    'tip-next': () => nextTip(),
    'record-clear': () => clearAllRecords(),
    'sound-toggle': () => toggleSound(),
    'policy-open': () => openPolicy(),
    'debug-toggle': () => toggleDebug(),
    'logout': () => handleLogout(),
    'navigate': element => navigateTo(element.dataset.tab),
    'camera-close': () => closeCamera(),
    'camera-capture': () => capturePhoto(),
    'camera-flip': () => flipCamera(),
    'modal-close': () => closeModal(),
    'reward-redeem': element => redeemReward(element.dataset.rewardId),
    'coupon-show': element => showCouponTicket(element.dataset.couponCode),
    'record-view': element => viewRecordDetail(element.dataset.recordId),
    'record-delete': element => deleteRecord(element.dataset.recordId),
};

document.addEventListener('click', event => {
    const element = event.target.closest('[data-action]');
    if (!element) return;
    const action = UI_ACTIONS[element.dataset.action];
    if (!action) return;
    if (element.dataset.stopPropagation === 'true') event.stopPropagation();
    action(element, event);
});

document.addEventListener('change', event => {
    const element = event.target;
    if (element.matches('#file-input')) handleFileSelect(event);
    else if (element.matches('#swap-proof-input')) handleSwapProof(event);
    else if (element.matches('#theme-select')) applyTheme(element.value);
    else if (element.matches('#lang-select')) setLang(element.value);
});
```

- [ ] **步驟 4：把 template handler 改成 `data-action`**

逐一替換，例如：

```html
<div class="header-avatar" id="hdr-avatar" data-action="avatar">👤</div>
<button class="scan-btn scan-btn--dispose" data-action="scan-mode" data-mode="dispose">
<input type="file" id="file-input" accept="image/*" capture="environment">
<button id="nav-home" class="nav-btn is-active" data-action="navigate" data-tab="home">
<button class="camera-btn camera-btn--capture" data-action="camera-capture">
<button class="btn btn--primary btn--full" data-action="modal-close">Close</button>
```

對 weather overlay 使用獨立 close button 與 overlay listener；panel 本身不需要 inline `stopPropagation`，由 `ui-actions.js` 檢查 `event.target === overlay`。

- [ ] **步驟 5：把動態 HTML 的 handler 改成 data attribute**

例如紀錄按鈕：

```javascript
`<button class="btn btn--danger"
         data-action="record-delete"
         data-record-id="${esc(String(r.id))}"
         data-stop-propagation="true">🗑️</button>`
```

獎勵、coupon、tips、modal 及 avatar button 使用相同模式；所有資料值先經現有 `esc()` 或改用 `document.createElement()` 與 `dataset` 設定。刪除 `element.onclick = handler`，改用 `addEventListener()`。

- [ ] **步驟 6：載入 dispatcher 並執行 CSP UI 測試**

在依賴的功能 script 之後載入：

```html
<script src="/static/js/ui-actions.js" defer></script>
```

執行：

```powershell
python -m pytest tests/test_csp_frontend.py::MainPageCspTests tests/test_records_scope.py tests/test_smoke.py -v
```

預期：無 inline handler；既有互動 wiring assertion 更新為 `data-action`／dispatcher。

- [ ] **步驟 7：提交主頁事件重構**

```powershell
git add static/js/ui-actions.js templates/index.html static/app.js static/js/app-records.js static/js/app-weather.js static/js/app-recycling.js tests/test_csp_frontend.py tests/test_records_scope.py tests/test_smoke.py
git commit -m "fix: remove inline event handlers from main UI"
```

### 任務 6：加入 CSP 與一致安全 headers

**檔案：**
- 修改：`web_security.py`
- 修改：`main.py`
- 修改測試：`tests/test_platform_security.py`
- 修改測試：`tests/test_csp_frontend.py`

- [ ] **步驟 1：先寫 CSP 與 header 測試**

```python
class SecurityHeaderTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_html_has_strict_script_policy(self):
        response = self.client.get("/login")
        csp = response.headers.get("content-security-policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self' https://cdnjs.cloudflare.com", csp)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("base-uri 'none'", csp)
        self.assertIn("form-action 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_security_headers_do_not_use_obsolete_xss_header(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertNotIn("x-xss-protection", response.headers)
```

- [ ] **步驟 2：確認 header 測試紅燈**

```powershell
python -m pytest tests/test_platform_security.py::SecurityHeaderTests -v
```

預期：CSP 尚不存在，舊 `X-XSS-Protection` 仍存在。

- [ ] **步驟 3：新增安全 header middleware**

```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=self, microphone=(), geolocation=(self)"
        response.headers["Content-Security-Policy"] = "; ".join([
            "default-src 'self'",
            "script-src 'self' https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "media-src 'self' blob:",
            "worker-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ])
        if IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
```

刪除 `X-XSS-Protection`。CSP 的 `style-src` 暫時保留 `'unsafe-inline'` 以支援現有 inline style；`script-src` 不允許 inline script。

- [ ] **步驟 4：執行 header 與 CSP 前端測試**

```powershell
python -m pytest tests/test_platform_security.py::SecurityHeaderTests tests/test_csp_frontend.py -v
```

預期：全部通過。

- [ ] **步驟 5：提交 CSP 與 headers**

```powershell
git add web_security.py main.py tests/test_platform_security.py tests/test_csp_frontend.py
git commit -m "fix: enforce content security policy and headers"
```

### 任務 7：加入 request ID、安全日誌及一般錯誤回應

**檔案：**
- 修改：`web_security.py`
- 修改：`main.py`
- 修改測試：`tests/test_platform_security.py`

- [ ] **步驟 1：先寫 request ID、一般錯誤及秘密遮蔽測試**

```python
class SecurityLoggingTests(unittest.TestCase):
    def test_every_response_has_request_id(self):
        response = TestClient(app).get("/api/config")
        self.assertRegex(response.headers.get("x-request-id", ""), r"^[0-9a-f-]{36}$")

    def test_unhandled_exception_returns_generic_body(self):
        async def explode():
            raise RuntimeError("service-role-secret-value")

        app.add_api_route("/_test/security-error", explode)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/_test/security-error")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], "INTERNAL_SERVER_ERROR")
        self.assertNotIn("service-role-secret-value", response.text)
```

- [ ] **步驟 2：確認日誌與一般錯誤測試紅燈**

```powershell
python -m pytest tests/test_platform_security.py::SecurityLoggingTests -v
```

預期：回應沒有 request ID，一般例外可能由預設錯誤頁處理。

- [ ] **步驟 3：新增 request ID middleware 與安全事件 helper**

```python
import logging
import uuid

security_logger = logging.getLogger("rel.security")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def log_security_event(request, event: str, result: str, user_id: int | None = None) -> None:
    security_logger.info(
        "event=%s result=%s request_id=%s route=%s user_id=%s",
        event,
        result,
        getattr(request.state, "request_id", "unknown"),
        request.url.path,
        user_id if user_id is not None else "anonymous",
    )
```

日誌參數只包含固定事件類別、結果、request ID、route 與內部 user ID，不傳 request body、Cookie、email、code 或 token。

- [ ] **步驟 4：加入一般 exception handler**

```python
@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    log_security_event(request, "unhandled_exception", "error")
    return JSONResponse(
        {"error": "INTERNAL_SERVER_ERROR", "request_id": request.state.request_id},
        status_code=500,
    )
```

在登入失敗、無效 Session、Origin 拒絕、限流、跨帳戶 `404`、驗證碼錯誤及上傳拒絕位置呼叫 `log_security_event()`，但不要記錄秘密值。

- [ ] **步驟 5：執行安全日誌測試**

```powershell
python -m pytest tests/test_platform_security.py::SecurityLoggingTests -v
```

預期：全部通過。

- [ ] **步驟 6：提交 request ID 與錯誤處理**

```powershell
git add web_security.py main.py tests/test_platform_security.py
git commit -m "fix: add safe request tracing and error responses"
```

### 任務 8：完成第五階段及整體安全驗證

**檔案：**
- 不新增正式程式碼；只修正本階段引入的問題。

- [ ] **步驟 1：執行平台聚焦測試**

```powershell
python -m pytest tests/test_platform_security.py tests/test_csp_frontend.py tests/test_config_route.py tests/test_schema.py tests/test_supabase_server_sdk.py -v
```

預期：全部通過。

- [ ] **步驟 2：執行五階段全部安全測試**

```powershell
python -m pytest tests/test_session_auth.py tests/test_account_authorization.py tests/test_record_authorization.py tests/test_email_auth_security.py tests/test_image_security.py tests/test_ai_validation.py tests/test_platform_security.py tests/test_csp_frontend.py -v
```

預期：全部通過。

- [ ] **步驟 3：執行靜態安全搜尋**

```powershell
rg -n "@app\.get\(\"/api/users|loginAs\(|showUserPicker\(|RE_LIFE_CURRENT_USER|allow_headers=\[\"\*\"\]|X-XSS-Protection|verify_jwt = true|scan-images', 'scan-images', true|<script(?![^>]*src)|\son[a-z]+=" . --pcre2 --glob '!node_modules/**' --glob '!.git/**' --glob '!docs/**'
```

預期：正式程式碼沒有舊漏洞路徑、任意 CORS header、公開 bucket、未使用身份 function 或 inline script／handler命中。

- [ ] **步驟 4：執行完整測試**

```powershell
python -m pytest tests -v
```

預期：沒有新增失敗；既有天氣 UI baseline 獨立報告。

- [ ] **步驟 5：檢查差異、設定檔與秘密**

```powershell
git diff --check
git status --short
rg -n "SUPABASE_SERVICE_ROLE_KEY=.+|AUTH_CODE_SECRET=.+|RESEND_API_KEY=.+|rel_session=.+" . --glob '!node_modules/**' --glob '!.git/**' --glob '!docs/**'
```

預期：沒有真實秘密被提交；`template.env` 只有空值或說明。

- [ ] **步驟 6：提交整體安全驗證調整**

```powershell
git add supabase_schema.sql supabase/config.toml config.py template.env web_security.py main.py templates/index.html templates/login.html templates/register.html static/js/auth-theme-boot.js static/js/login.js static/js/register.js static/js/ui-actions.js static/app.js static/js/app-records.js static/js/app-weather.js static/js/app-recycling.js tests/test_platform_security.py tests/test_csp_frontend.py tests/test_config_route.py tests/test_schema.py tests/test_supabase_server_sdk.py tests/test_session_auth.py tests/test_account_authorization.py tests/test_record_authorization.py tests/test_email_auth_security.py tests/test_image_security.py tests/test_smoke.py tests/test_auth_theme.py tests/test_perf_mode.py tests/test_records_scope.py
git commit -m "test: complete Re-Life security verification"
```
