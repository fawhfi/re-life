# 帳戶與紀錄授權實作計畫

> **給代理工作者：** 必須逐項使用 `superpowers:subagent-driven-development`（建議）或 `superpowers:executing-plans` 執行本計畫。所有正式改動遵守測試先行，先證明越權路徑存在，再關閉該路徑。

**目標：** 移除公開帳戶探索與客戶端身份控制，確保帳戶、紀錄、圖片及獎勵操作只能作用於目前 Session 使用者。

**架構：** FastAPI 路由使用 `Depends(require_current_user)` 取得唯一身份；資料層接收由後端提供的 `owner_id`，不再自行解析任何客戶端識別碼。跨帳戶資源統一回傳 `404`。

**技術棧：** FastAPI dependency、Supabase REST、原生 JavaScript、pytest／unittest。

---

## 檔案配置

- 修改 `main.py`：移除公開使用者端點，新增 `/api/users/me`，保護掃描、紀錄與兌換路由。
- 修改 `auth.py`：只允許以已驗證內部 ID 更新目前使用者，限制可修改欄位。
- 修改 `data.py`：所有紀錄函式顯式接收 `owner_id`，刪除時檢查擁有權。
- 修改 `static/supabase.js`：移除使用者識別參數及公開帳戶 API wrapper。
- 修改 `static/app.js`、`static/js/app-records.js`：移除免密碼帳戶選擇與客戶端身份來源。
- 新增 `tests/test_account_authorization.py`、`tests/test_record_authorization.py`：API 與資料層 exploit 回歸測試。

### 任務 1：以 `/api/users/me` 取代公開帳戶端點

**檔案：**
- 修改：`main.py`
- 修改：`auth.py`
- 新增測試：`tests/test_account_authorization.py`

- [ ] **步驟 1：先寫公開帳戶探索及自助帳戶測試**

```python
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import app
from sessions import SessionContext


class AccountAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_public_account_discovery_routes_are_removed(self):
        self.assertEqual(self.client.get("/api/users").status_code, 404)
        self.assertEqual(self.client.get("/api/users/by-name/Alice").status_code, 404)
        self.assertEqual(self.client.get("/api/users/by-email/alice@example.com").status_code, 404)
        self.assertEqual(self.client.get("/api/users/by-id/1").status_code, 404)

    def test_me_requires_authentication(self):
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)

    def test_patch_me_uses_session_user_id(self):
        user = {"id": 42, "display_name": "Alice", "email": "alice@example.com"}
        context = SessionContext("s1", user, "token", False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=context)), \
             patch("main.save_user_data", new=AsyncMock(return_value=True)) as save:
            response = self.client.patch(
                "/api/users/me",
                json={"photoUrl": "🌿", "user_id": 999},
                cookies={"rel_session": "token"},
            )

        self.assertEqual(response.status_code, 200)
        save.assert_awaited_once()
        self.assertEqual(save.await_args.args[0], 42)
```

- [ ] **步驟 2：確認測試紅燈**

```powershell
python -m pytest tests/test_account_authorization.py -v
```

預期：公開路由仍回傳成功、`/api/users/me` 不存在，越權 payload 尚未被忽略。

- [ ] **步驟 3：收窄 `auth.save_user_data()` 的輸入**

保留函式，但第一個參數只接受後端取得的內部 ID，刪除 `_fallbackName` 邏輯：

```python
async def save_user_data(user_id: int, data: dict) -> bool:
    row = await _resolve_user_row(int(user_id))
    if not row:
        return False

    update_payload: dict[str, object] = {}
    if "photoUrl" in data or "photo_url" in data:
        update_payload["photo_url"] = data.get("photoUrl", data.get("photo_url"))
    if "spent_points" in data or "spentPoints" in data:
        update_payload["spent_points"] = max(0, int(data.get("spent_points", data.get("spentPoints", 0)) or 0))
    if "earned_points" in data or "earnedPoints" in data:
        update_payload["earned_points"] = max(0, int(data.get("earned_points", data.get("earnedPoints", 0)) or 0))
    if "claimed_coupons" in data or "claimedCoupons" in data:
        update_payload["claimed_coupons"] = _safe_list(data.get("claimed_coupons", data.get("claimedCoupons")))[:100]

    if not update_payload:
        return True
    if supabase_enabled():
        await supabase_update("app_users", update_payload, filters={"id": int(user_id)})
        return True
    memory_row = _memory_find_user(int(user_id))
    if not memory_row:
        return False
    memory_row.update(update_payload)
    memory_row["updated_at"] = _utc_iso()
    return True
```

- [ ] **步驟 4：替換 `main.py` 帳戶路由**

刪除五個公開／帶 identifier 的路由，新增：

```python
@app.get("/api/users/me")
async def current_user_profile(user: dict = Depends(require_current_user)):
    return normalize_user_row(user)


@app.patch("/api/users/me")
async def update_current_user(
    request: Request,
    data: dict,
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 30, 60)
    if not await save_user_data(int(user["id"]), data or {}):
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    refreshed = await get_user_by_id(int(user["id"]))
    return {"ok": True, "user": refreshed}
```

- [ ] **步驟 5：重新執行帳戶授權測試**

```powershell
python -m pytest tests/test_account_authorization.py -v
```

預期：全部通過。

- [ ] **步驟 6：提交帳戶 API 收斂**

```powershell
git add main.py auth.py tests/test_account_authorization.py
git commit -m "fix: restrict account access to current session"
```

### 任務 2：讓資料層只接受後端 owner ID

**檔案：**
- 修改：`data.py`
- 新增測試：`tests/test_record_authorization.py`

- [ ] **步驟 1：先寫資料層擁有權測試**

```python
import unittest
from unittest.mock import AsyncMock, patch

import data


class RecordDataAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_item_overrides_forged_user_fields(self):
        captured = {}

        async def fake_insert(table, values, *, returning=True):
            captured.update(values)
            return [{"id": 88}]

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_insert", new=fake_insert):
            await data.add_item({"name": "Bottle", "mode": "dispose", "schema_id": "food_new", "userId": 999}, owner_id=42)

        self.assertEqual(captured["user_id"], 42)

    async def test_delete_item_filters_by_record_and_owner(self):
        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_delete", new=AsyncMock(return_value=[{"id": 7}])) as delete:
            deleted = await data.delete_item(7, owner_id=42)

        self.assertTrue(deleted)
        self.assertEqual(delete.await_args.kwargs["filters"], {"id": 7, "user_id": 42})
        self.assertTrue(delete.await_args.kwargs["returning"])

    async def test_clear_records_ignores_other_accounts(self):
        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_delete", new=AsyncMock(return_value=[])) as delete:
            await data.clear_all_items(owner_id=42)

        self.assertEqual(delete.await_args.kwargs["filters"], {"user_id": 42})
```

- [ ] **步驟 2：確認測試紅燈**

```powershell
python -m pytest tests/test_record_authorization.py::RecordDataAuthorizationTests -v
```

預期：現有函式不接受 `owner_id`，刪除只以紀錄 ID 過濾。

- [ ] **步驟 3：重寫紀錄函式簽名與 owner 綁定**

刪除 `_resolve_user_id()`，把函式改為：

```python
async def add_item(item: dict, *, owner_id: int) -> dict:
    record = {
        "user_id": int(owner_id),
        "mode": item.get("mode") or "dispose",
        "name": item.get("name") or "Scanned Item",
        "description": item.get("description") or "",
        "image_url": await _persist_record_image_url(item.get("image_url")),
        "dealt_with_method": item.get("dealt_with_method") or item.get("dealtWithMethod") or item.get("disposal_guide") or "",
        "eco_rate": int(item.get("eco_rate") or 3),
        "recycle_rate": int(item.get("recycle_rate") or 4),
        "overall_score": int(item.get("overall_score") or item.get("overallScore") or 0),
        "material": item.get("material") or "",
        "grade": item.get("grade") or "",
        "brand": item.get("brand") or "",
        "category": item.get("category") or "",
        "weighted_scores": item.get("weighted_scores") or item.get("weightedScores") or {},
        "schema_id": item.get("schema_id") or item.get("schemaId") or "food_new",
        "alternative": item.get("alternative"),
        "precaution": item.get("precaution") or "",
    }
    if supabase_enabled():
        rows = await supabase_insert("scan_records", record)
        return {"id": rows[0]["id"] if rows else None}
    stored = _memory_store_record(record)
    return {"id": stored["id"]}


async def get_items(*, owner_id: int) -> list[dict]:
    if supabase_enabled():
        rows = await supabase_select(
            "scan_records",
            filters={"user_id": int(owner_id)},
            order="created_at.desc",
        )
    else:
        rows = [row for row in _memory_records_by_id.values() if int(row["user_id"]) == int(owner_id)]
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return [_normalize_record_row(row) for row in rows or []]


async def delete_item(item_id, *, owner_id: int) -> bool:
    if supabase_enabled():
        rows = await supabase_delete(
            "scan_records",
            filters={"id": item_id, "user_id": int(owner_id)},
            returning=True,
        )
        return bool(rows)
    row = _memory_records_by_id.get(str(item_id)) or _memory_records_by_id.get(item_id)
    if not row or int(row.get("user_id") or 0) != int(owner_id):
        return False
    _memory_records_by_id.pop(row["id"], None)
    return True


async def clear_all_items(*, owner_id: int) -> None:
    if supabase_enabled():
        await supabase_delete("scan_records", filters={"user_id": int(owner_id)})
        return
    doomed = [rid for rid, row in _memory_records_by_id.items() if int(row.get("user_id") or 0) == int(owner_id)]
    for rid in doomed:
        _memory_records_by_id.pop(rid, None)
```

保持 `_normalize_record_row()` 的對外欄位相容，不再以 display name 補足 owner。

- [ ] **步驟 4：執行資料層授權測試**

```powershell
python -m pytest tests/test_record_authorization.py::RecordDataAuthorizationTests -v
```

預期：全部通過。

- [ ] **步驟 5：提交資料層 owner 邊界**

```powershell
git add data.py tests/test_record_authorization.py
git commit -m "fix: bind record storage to authenticated owner"
```

### 任務 3：保護紀錄與掃描 API

**檔案：**
- 修改：`main.py`
- 修改測試：`tests/test_record_authorization.py`

- [ ] **步驟 1：先寫未登入與跨帳戶 API 測試**

```python
from fastapi.testclient import TestClient
from main import app
from sessions import SessionContext


class RecordRouteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_record_and_scan_routes_require_session(self):
        self.assertEqual(self.client.get("/api/records").status_code, 401)
        self.assertEqual(self.client.post("/api/records", json={"name": "Bottle"}).status_code, 401)
        self.assertEqual(self.client.delete("/api/records/7").status_code, 401)
        self.assertEqual(
            self.client.post(
                "/api/scan/ai",
                files={"file": ("bottle.jpg", b"image", "image/jpeg")},
            ).status_code,
            401,
        )

    def test_list_records_uses_session_owner_not_query_string(self):
        context = SessionContext("s1", {"id": 42}, "token", False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=context)), \
             patch("main.get_items", new=AsyncMock(return_value=[])) as get_items:
            response = self.client.get("/api/records?user_id=999", cookies={"rel_session": "token"})

        self.assertEqual(response.status_code, 200)
        get_items.assert_awaited_once_with(owner_id=42)

    def test_deleting_another_users_record_returns_404(self):
        context = SessionContext("s1", {"id": 42}, "token", False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=context)), \
             patch("main.delete_item", new=AsyncMock(return_value=False)):
            response = self.client.delete("/api/records/777", cookies={"rel_session": "token"})

        self.assertEqual(response.status_code, 404)
```

- [ ] **步驟 2：確認 API 測試紅燈**

```powershell
python -m pytest tests/test_record_authorization.py::RecordRouteAuthorizationTests -v
```

預期：未登入請求仍可進入路由，query string 仍決定 owner，跨帳戶刪除仍回傳成功。

- [ ] **步驟 3：把 Session user 注入所有紀錄與掃描路由**

```python
@app.get("/api/records")
async def list_records(
    request: Request,
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 60, 60)
    return await get_items(owner_id=int(user["id"]))


@app.post("/api/records")
async def create_record(
    request: Request,
    data: dict,
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 30, 60)
    try:
        result = await add_item(data or {}, owner_id=int(user["id"]))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    return {"ok": True, **result}


@app.delete("/api/records")
async def clear_records(
    request: Request,
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 30, 60)
    await clear_all_items(owner_id=int(user["id"]))
    return {"ok": True}


@app.delete("/api/records/{item_id}")
async def delete_record(
    request: Request,
    item_id: str,
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 30, 60)
    if not await delete_item(item_id, owner_id=int(user["id"])):
        return JSONResponse({"error": "NOT_FOUND"}, 404)
    return {"ok": True}
```

在 `/api/records/image` 與 `/api/scan/ai` 的參數列加入：

```python
user: dict = Depends(require_current_user)
```

紀錄圖片路徑使用 `user["public_id"]` 或內部 ID；刪除 `user_id`、`display_name`、`user_key` Form 參數。掃描端點在讀取檔案前先完成 dependency 驗證。

- [ ] **步驟 4：保護兌換路由但保留模擬規則**

```python
@app.post("/api/rewards/redeem")
async def redeem(
    request: Request,
    data: dict,
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 30, 60)
    reward = next((item for item in REWARDS_CATALOG if item["id"] == data.get("reward_id")), None)
    if not reward:
        return JSONResponse({"error": "NOT_FOUND"}, 404)
    code = "RL-" + uuid.uuid4().hex[:6].upper() + "-" + str(reward["cost"])
    return {
        "ok": True,
        "coupon": {
            "code": code,
            "title": reward["title"],
            "image": reward["image"],
            "cost": reward["cost"],
            "claimed_date": "Just now",
            "expiry": "Valid 30 days",
        },
    }
```

`user` 在本階段只用於強制身份邊界，不改變積分模擬規則。

- [ ] **步驟 5：重新執行 API 授權測試**

```powershell
python -m pytest tests/test_record_authorization.py::RecordRouteAuthorizationTests -v
```

預期：全部通過。

- [ ] **步驟 6：提交受保護路由**

```powershell
git add main.py tests/test_record_authorization.py
git commit -m "fix: enforce session ownership on protected APIs"
```

### 任務 4：移除前端識別參數及免密碼帳戶選擇器

**檔案：**
- 修改：`static/supabase.js`
- 修改：`static/app.js`
- 修改：`static/js/app-records.js`
- 修改測試：`tests/test_account_authorization.py`

- [ ] **步驟 1：先寫前端漏洞移除測試**

```python
from pathlib import Path


class FrontendAuthorizationTests(unittest.TestCase):
    def test_passwordless_picker_and_client_owner_fields_are_removed(self):
        backend = Path("static/supabase.js").read_text(encoding="utf-8")
        app_js = Path("static/app.js").read_text(encoding="utf-8")

        for forbidden in (
            "getAllUsers", "showUserPicker", "loginAs(",
            "fallbackUserId", "fallbackUserName",
            'form.append("user_id"', 'form.append("display_name"', 'form.append("user_key"',
            'async getItems(userId', 'user_id: userId', 'user_key: userKey',
        ):
            self.assertNotIn(forbidden, backend + app_js)

        self.assertIn('requestJson("/api/users/me")', backend)
        self.assertIn('requestJson("/api/records")', backend)
```

- [ ] **步驟 2：確認前端測試紅燈**

```powershell
python -m pytest tests/test_account_authorization.py::FrontendAuthorizationTests -v
```

預期：仍可找到使用者選擇器、帳戶清單 wrapper 及 client owner 欄位。

- [ ] **步驟 3：收窄 `static/supabase.js` API wrapper**

刪除 `fallbackUserId()`、`fallbackUserName()`、`getAllUsers()`、`getUserById()`、`getUserByName()`、`getUserByEmail()`。保留：

```javascript
async getCurrentUser() {
    const data = await requestJson("/api/users/me");
    return normalizeUser(data);
},

async saveUserData(data) {
    const result = await requestJson("/api/users/me", {
        method: "PATCH",
        body: data || {},
    });
    return normalizeUser(result.user);
},

async getItems() {
    const data = await requestJson("/api/records");
    return safeArray(data).map(normalizeItem);
},

async clearAllItems() {
    await requestJson("/api/records", { method: "DELETE" });
},
```

`uploadRecordImageIfNeeded()` 只附加 `file`；`buildRecordPayload()` 完全移除 `userId`、`userName`、`userKey`。

- [ ] **步驟 4：移除 `static/app.js` 的 picker 與本地身份 fallback**

刪除 `showUserPicker()`、`loginAs()`。未登入時的 avatar／login 操作直接導向登入頁：

```javascript
function handleAvatarClick() {
    if (!state.currentUser) {
        window.location.assign('/login');
        return;
    }
    openAvatarPicker();
}

function toggleLogin() {
    if (!state.currentUser) {
        window.location.assign('/login');
        return;
    }
    requestLogout();
}
```

更新 `static/js/app-records.js`，呼叫 `FB.getItems()`、`FB.clearAllItems()` 時不傳任何 owner 參數。

- [ ] **步驟 5：重新執行前端授權測試與紀錄 UI 測試**

```powershell
python -m pytest tests/test_account_authorization.py::FrontendAuthorizationTests tests/test_records_scope.py -v
```

預期：安全測試通過；原本要求 client owner query 的 assertion 更新為無參數 Session API。

- [ ] **步驟 6：提交前端身份移除**

```powershell
git add static/supabase.js static/app.js static/js/app-records.js tests/test_account_authorization.py tests/test_records_scope.py
git commit -m "fix: remove client-controlled account identity"
```

### 任務 5：加入完整跨帳戶 exploit 回歸測試

**檔案：**
- 修改測試：`tests/test_account_authorization.py`
- 修改測試：`tests/test_record_authorization.py`

- [ ] **步驟 1：加入兩個不同 Session 的端到端擁有權測試**

```python
class CrossAccountExploitTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_forged_identifiers_cannot_select_another_account(self):
        alice = SessionContext("alice-session", {"id": 1, "display_name": "Alice"}, "alice-token", False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=alice)), \
             patch("main.add_item", new=AsyncMock(return_value={"id": 5})) as add:
            response = self.client.post(
                "/api/records",
                json={"name": "Bottle", "userId": 2, "userName": "Bob", "userKey": "usr_bob"},
                cookies={"rel_session": "alice-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(add.await_args.kwargs["owner_id"], 1)

    def test_other_users_record_is_indistinguishable_from_missing_record(self):
        alice = SessionContext("alice-session", {"id": 1}, "alice-token", False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=alice)), \
             patch("main.delete_item", new=AsyncMock(return_value=False)):
            foreign = self.client.delete("/api/records/200", cookies={"rel_session": "alice-token"})
            missing = self.client.delete("/api/records/999", cookies={"rel_session": "alice-token"})

        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(foreign.json(), missing.json())
```

- [ ] **步驟 2：暫時反轉 owner 過濾，確認測試能抓到漏洞**

在本機工作樹暫時讓 `delete_item()` 只以 `id` 過濾並執行：

```powershell
python -m pytest tests/test_record_authorization.py::CrossAccountExploitTests -v
```

預期：測試失敗。立即還原這個暫時變更，再繼續。

- [ ] **步驟 3：執行完整第二階段安全測試**

```powershell
python -m pytest tests/test_session_auth.py tests/test_account_authorization.py tests/test_record_authorization.py -v
```

預期：全部通過。

- [ ] **步驟 4：執行相關與完整測試**

```powershell
python -m pytest tests/test_records_scope.py tests/test_storage_upload_timing.py tests/test_scan_ui_requirements.py -v
python -m pytest tests -v
```

預期：沒有新增安全或紀錄回歸；既有天氣 baseline 獨立記錄。

- [ ] **步驟 5：提交 exploit 測試**

```powershell
git add tests/test_account_authorization.py tests/test_record_authorization.py
git commit -m "test: prevent cross-account record access"
```
