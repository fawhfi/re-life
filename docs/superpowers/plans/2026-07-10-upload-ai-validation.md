# 圖片上傳與 AI 驗證實作計畫

> **給代理工作者：** 必須逐項使用 `superpowers:subagent-driven-development`（建議）或 `superpowers:executing-plans` 執行本計畫。每種惡意輸入先建立真實邊界的失敗測試，確認紅燈後才實作驗證。

**目標：** 對掃描圖片、紀錄圖片、頭像及 AI 回傳建立嚴格伺服器驗證，阻止偽造 MIME、超大檔案、解壓縮炸彈、惡意頭像和無效 AI 資料進入系統。

**架構：** `image_security.py` 負責有界讀取、Pillow 解碼、像素限制與重新編碼；`api_models.py` 負責 Pydantic request／response schema；掃描 service 只接收已驗證圖片與已驗證 AI 結果。

**技術棧：** FastAPI UploadFile、Pillow、Pydantic v2、httpx、Supabase Storage、pytest。

---

## 檔案配置

- 新增 `image_security.py`：共用圖片讀取、驗證、重新編碼與安全檔名。
- 新增 `api_models.py`：帳戶、紀錄、掃描、獎勵與 AI 結果 model。
- 修改 `main.py`、`data.py`、`models.py`、`scan_service.py`：接入安全邊界。
- 修改 `auth.py`：頭像只接受白名單 emoji 或伺服器產生 URL。
- 修改 `static/supabase.js`、`static/app.js`：頭像與紀錄圖片改用 multipart 上傳。
- 修改 `config.py`、`template.env`：圖片尺寸、AI endpoint 及回應大小設定。
- 新增 `tests/test_image_security.py`、`tests/test_ai_validation.py`：對抗性輸入回歸測試。

### 任務 1：建立共用圖片驗證器

**檔案：**
- 新增：`image_security.py`
- 修改：`config.py`
- 新增測試：`tests/test_image_security.py`

- [ ] **步驟 1：先寫真實格式、有界讀取、重新編碼及像素限制測試**

```python
from io import BytesIO
import unittest

from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from image_security import ImageValidationError, read_and_sanitize_upload, sanitize_image_bytes


def make_image(fmt="PNG", size=(16, 16), with_exif=False):
    buffer = BytesIO()
    image = Image.new("RGB", size, "green")
    save_args = {"format": fmt}
    if with_exif:
        exif = Image.Exif()
        exif[0x010E] = "secret metadata"
        save_args["exif"] = exif
    image.save(buffer, **save_args)
    return buffer.getvalue()


class ImageSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_claimed_mime_does_not_override_real_format(self):
        upload = UploadFile(filename="fake.jpg", file=BytesIO(b"not-an-image"), headers=Headers({"content-type": "image/jpeg"}))
        with self.assertRaisesRegex(ImageValidationError, "INVALID_IMAGE"):
            await read_and_sanitize_upload(upload)

    async def test_upload_is_rejected_before_exceeding_byte_limit(self):
        upload = UploadFile(filename="large.png", file=BytesIO(b"x" * 1025), headers=Headers({"content-type": "image/png"}))
        with self.assertRaisesRegex(ImageValidationError, "IMAGE_TOO_LARGE"):
            await read_and_sanitize_upload(upload, max_bytes=1024)

    def test_accepted_image_is_reencoded_as_jpeg_without_metadata(self):
        sanitized = sanitize_image_bytes(make_image("JPEG", with_exif=True))
        self.assertEqual(sanitized.content_type, "image/jpeg")
        self.assertTrue(sanitized.filename.endswith(".jpg"))
        with Image.open(BytesIO(sanitized.contents)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertFalse(image.getexif())

    def test_unreasonable_pixel_count_is_rejected(self):
        with self.assertRaisesRegex(ImageValidationError, "IMAGE_DIMENSIONS_TOO_LARGE"):
            sanitize_image_bytes(make_image(size=(200, 200)), max_pixels=10_000)
```

- [ ] **步驟 2：確認測試因模組不存在而紅燈**

```powershell
python -m pytest tests/test_image_security.py::ImageSecurityTests -v
```

預期：collection 時出現 `ModuleNotFoundError: image_security`。

- [ ] **步驟 3：在 `config.py` 新增圖片限制**

```python
MAX_UPLOAD_BYTES = max(1024, int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))))
MAX_IMAGE_PIXELS = max(1, int(os.getenv("MAX_IMAGE_PIXELS", "25000000")))
MAX_IMAGE_DIMENSION = max(64, int(os.getenv("MAX_IMAGE_DIMENSION", "8192")))
IMAGE_JPEG_QUALITY = min(95, max(60, int(os.getenv("IMAGE_JPEG_QUALITY", "85"))))
```

- [ ] **步驟 4：新增 `image_security.py` 完整最小實作**

```python
"""Bounded image decoding and re-encoding for untrusted uploads."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import secrets
import warnings

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from config import IMAGE_JPEG_QUALITY, MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS, MAX_UPLOAD_BYTES


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class SanitizedImage:
    contents: bytes
    content_type: str
    filename: str
    width: int
    height: int


async def read_upload_limited(upload: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ImageValidationError("IMAGE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


def sanitize_image_bytes(
    contents: bytes,
    *,
    max_pixels: int = MAX_IMAGE_PIXELS,
    max_dimension: int = MAX_IMAGE_DIMENSION,
) -> SanitizedImage:
    if not contents:
        raise ImageValidationError("EMPTY_IMAGE")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ImageValidationError("UNSUPPORTED_IMAGE_FORMAT")
                source.load()
                width, height = source.size
                if width < 1 or height < 1 or width > max_dimension or height > max_dimension:
                    raise ImageValidationError("IMAGE_DIMENSIONS_TOO_LARGE")
                if width * height > max_pixels:
                    raise ImageValidationError("IMAGE_DIMENSIONS_TOO_LARGE")
                normalized = ImageOps.exif_transpose(source).convert("RGB")
                output = BytesIO()
                normalized.save(output, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError("INVALID_IMAGE") from exc

    return SanitizedImage(
        contents=output.getvalue(),
        content_type="image/jpeg",
        filename=f"{secrets.token_hex(16)}.jpg",
        width=width,
        height=height,
    )


async def read_and_sanitize_upload(
    upload: UploadFile,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> SanitizedImage:
    contents = await read_upload_limited(upload, max_bytes=max_bytes)
    return sanitize_image_bytes(contents)
```

- [ ] **步驟 5：執行圖片驗證測試**

```powershell
python -m pytest tests/test_image_security.py::ImageSecurityTests -v
```

預期：全部通過。

- [ ] **步驟 6：提交圖片安全邊界**

```powershell
git add image_security.py config.py tests/test_image_security.py
git commit -m "feat: validate and sanitize uploaded images"
```

### 任務 2：接入掃描與紀錄圖片上傳

**檔案：**
- 修改：`main.py`
- 修改：`data.py`
- 修改：`static/supabase.js`
- 修改測試：`tests/test_image_security.py`
- 修改測試：`tests/test_storage_upload_timing.py`

- [ ] **步驟 1：先寫掃描及紀錄上傳整合測試**

```python
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from sessions import SessionContext


class ProtectedImageRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.context = SessionContext("s1", {"id": 42, "public_id": "usr_alice"}, "token", False)

    def test_record_upload_uses_session_partition_and_sanitized_bytes(self):
        sanitized = type("Image", (), {
            "contents": b"sanitized-jpeg",
            "content_type": "image/jpeg",
            "filename": "safe.jpg",
        })()
        with patch("sessions.resolve_session", new=AsyncMock(return_value=self.context)), \
             patch("main.read_and_sanitize_upload", new=AsyncMock(return_value=sanitized)), \
             patch("main.persist_record_image", new=AsyncMock(return_value="/api/storage/url")) as persist:
            response = self.client.post(
                "/api/records/image",
                files={"file": ("evil.png", b"payload", "image/png")},
                cookies={"rel_session": "token"},
            )
        self.assertEqual(response.status_code, 200)
        persist.assert_awaited_once_with(
            b"sanitized-jpeg",
            "safe.jpg",
            "image/jpeg",
            owner_key="usr_alice",
        )

    def test_scan_receives_only_sanitized_image(self):
        sanitized = type("Image", (), {
            "contents": b"sanitized-jpeg",
            "content_type": "image/jpeg",
            "filename": "safe.jpg",
        })()
        with patch("sessions.resolve_session", new=AsyncMock(return_value=self.context)), \
             patch("main.read_and_sanitize_upload", new=AsyncMock(return_value=sanitized)), \
             patch("main.analyze_scan_image", new=AsyncMock(return_value={"name": "Bottle"})) as analyze:
            response = self.client.post(
                "/api/scan/ai",
                files={"file": ("evil.png", b"payload", "image/png")},
                cookies={"rel_session": "token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analyze.await_args.kwargs["contents"], b"sanitized-jpeg")
        self.assertEqual(analyze.await_args.kwargs["filename"], "safe.jpg")
```

- [ ] **步驟 2：確認整合測試紅燈**

```powershell
python -m pytest tests/test_image_security.py::ProtectedImageRouteTests -v
```

預期：路由仍信任 MIME、直接 `file.read()`，`persist_record_image()` 沒有 owner 分區。

- [ ] **步驟 3：讓 `persist_record_image()` 使用 owner 分區**

```python
async def persist_record_image(
    contents: bytes,
    filename: str,
    content_type: str,
    *,
    owner_key: str,
) -> str:
    safe_owner = re.sub(r"[^a-zA-Z0-9_-]", "", owner_key)[:64]
    if not safe_owner:
        raise ValueError("INVALID_IMAGE_OWNER")
    path = f"scan-records/{safe_owner}/{uuid.uuid4().hex}.jpg"
    if not (supabase_enabled() and SUPABASE_STORAGE_BUCKET and SUPABASE_URL):
        if IS_DEVELOPMENT:
            return _image_data_url(contents, "image/jpeg")
        raise RuntimeError("Persistent image storage unavailable")
    await supabase_storage_upload(
        SUPABASE_STORAGE_BUCKET,
        path,
        contents,
        "image/jpeg",
    )
    return supabase_storage_signed_url(SUPABASE_STORAGE_BUCKET, path)
```

- [ ] **步驟 4：在兩個 FastAPI 路由接入驗證器**

```python
from image_security import ImageValidationError, read_and_sanitize_upload


@app.post("/api/records/image")
async def upload_record_image(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 30, 60)
    try:
        image = await read_and_sanitize_upload(file)
        image_url = await persist_record_image(
            image.contents,
            image.filename,
            image.content_type,
            owner_key=str(user.get("public_id") or user["id"]),
        )
    except ImageValidationError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    return {"image_url": image_url}
```

`/api/scan/ai` 同樣先取得 `image = await read_and_sanitize_upload(file)`，並把 `image.contents`、`image.filename` 傳給 `analyze_scan_image()`；刪除原本 MIME 與 `len(contents)` 分支。

- [ ] **步驟 5：更新前端紀錄圖片表單**

`static/supabase.js` 的 `uploadRecordImageIfNeeded()` 只保留：

```javascript
const form = new FormData();
form.append("file", blob, `scan-record${imageExtensionForMime(mime)}`);
const data = await requestFormJson("/api/records/image", { body: form });
```

不得再附加任何 owner 欄位。

- [ ] **步驟 6：執行圖片路由與既有上傳測試**

```powershell
python -m pytest tests/test_image_security.py::ProtectedImageRouteTests tests/test_storage_upload_timing.py -v
```

預期：全部通過；既有測試更新為驗證 sanitized bytes 與 Session owner 分區。

- [ ] **步驟 7：提交掃描與紀錄上傳修復**

```powershell
git add main.py data.py static/supabase.js tests/test_image_security.py tests/test_storage_upload_timing.py
git commit -m "fix: sanitize scan and record images before use"
```

### 任務 3：建立安全頭像更新端點

**檔案：**
- 修改：`auth.py`
- 修改：`main.py`
- 修改：`static/supabase.js`
- 修改：`static/app.js`
- 修改測試：`tests/test_image_security.py`

- [ ] **步驟 1：先寫任意頭像字串與安全上傳測試**

```python
class AvatarSecurityTests(unittest.TestCase):
    def test_profile_patch_rejects_arbitrary_photo_url(self):
        context = SessionContext("s1", {"id": 42}, "token", False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=context)):
            response = self.client.patch(
                "/api/users/me",
                json={"photoUrl": '\" onerror=\"alert(1)'},
                cookies={"rel_session": "token"},
            )
        self.assertEqual(response.status_code, 422)

    def test_avatar_upload_persists_server_generated_url(self):
        context = SessionContext("s1", {"id": 42, "public_id": "usr_alice"}, "token", False)
        sanitized = type("Image", (), {
            "contents": b"jpeg",
            "content_type": "image/jpeg",
            "filename": "safe.jpg",
        })()
        with patch("sessions.resolve_session", new=AsyncMock(return_value=context)), \
             patch("main.read_and_sanitize_upload", new=AsyncMock(return_value=sanitized)), \
             patch("main.persist_avatar_image", new=AsyncMock(return_value="/api/storage/avatar")), \
             patch("main.save_user_data", new=AsyncMock(return_value=True)):
            response = self.client.post(
                "/api/users/me/avatar",
                files={"file": ("avatar.png", b"payload", "image/png")},
                cookies={"rel_session": "token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["photo_url"], "/api/storage/avatar")
```

- [ ] **步驟 2：確認頭像測試紅燈**

```powershell
python -m pytest tests/test_image_security.py::AvatarSecurityTests -v
```

預期：任意 `photoUrl` 仍可保存，頭像上傳端點不存在。

- [ ] **步驟 3：限制 profile patch 的 emoji 白名單**

在 `image_security.py` 定義唯一白名單與正規化 helper：

```python
ALLOWED_AVATAR_EMOJI = {
    "🌿", "♻️", "🌱", "🍃", "🌳", "💚", "🌍", "🪴", "🐼", "🐨",
    "🦊", "🐸", "🌺", "🍀", "🌊", "🔥", "⭐", "🌈", "🦋", "🐝",
}


def normalize_avatar_value(value: object) -> str:
    avatar = str(value or "")
    if avatar not in ALLOWED_AVATAR_EMOJI:
        raise ValueError("INVALID_AVATAR")
    return avatar
```

`auth.py` 從 `image_security` 匯入 `normalize_avatar_value`；`save_user_data()` 的一般 JSON profile 更新只接受上述 emoji。伺服器產生的圖片 URL 只由專用內部參數寫入，不接受客戶端 URL。

- [ ] **步驟 4：新增頭像保存與路由**

`data.py` 從 `config` 匯入 `IS_DEVELOPMENT`，並加入圖片持久化 helper：

```python
async def persist_avatar_image(image: SanitizedImage, *, owner_key: str) -> str:
    safe_owner = re.sub(r"[^a-zA-Z0-9_-]", "", owner_key)[:64]
    if not safe_owner:
        raise ValueError("INVALID_IMAGE_OWNER")
    if not supabase_enabled():
        if IS_DEVELOPMENT:
            return _image_data_url(image.contents, image.content_type)
        raise RuntimeError("Persistent image storage unavailable")
    path = f"avatars/{safe_owner}/{uuid.uuid4().hex}.jpg"
    await supabase_storage_upload(
        SUPABASE_STORAGE_BUCKET,
        path,
        image.contents,
        image.content_type,
    )
    return supabase_storage_signed_url(SUPABASE_STORAGE_BUCKET, path)
```

`auth.py` 從 `config` 匯入 `IS_DEVELOPMENT`，並加入只供後端使用的 URL 更新 helper：

```python
async def save_user_avatar_url(user_id: int, photo_url: str) -> None:
    if supabase_enabled():
        await supabase_update(
            "app_users",
            {"photo_url": photo_url},
            filters={"id": int(user_id)},
            returning=False,
        )
        return
    if not IS_DEVELOPMENT:
        raise RuntimeError("Persistent user storage unavailable")
    row = _memory_find_user(int(user_id))
    if not row:
        raise ValueError("USER_NOT_FOUND")
    row["photo_url"] = photo_url
    row["updated_at"] = _utc_iso()
```

`main.py` 加入：

```python
@app.post("/api/users/me/avatar")
async def upload_current_user_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(require_current_user),
):
    try:
        image = await read_and_sanitize_upload(file)
        photo_url = await persist_avatar_image(
            image,
            owner_key=str(user.get("public_id") or user["id"]),
        )
        await save_user_avatar_url(int(user["id"]), photo_url)
    except ImageValidationError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    return {"ok": True, "photo_url": photo_url}
```

`save_user_avatar_url()` 只供後端呼叫，客戶端不能提交 URL。

- [ ] **步驟 5：更新前端頭像 DOM 與上傳**

`static/supabase.js` 新增 `uploadAvatar(file)` multipart wrapper。`static/app.js` 不再使用 FileReader data URL 保存頭像；圖片顯示使用 DOM API：

```javascript
function renderAvatar(container, value) {
    container.replaceChildren();
    if (typeof value === 'string' && value.startsWith('/api/storage/')) {
        const image = document.createElement('img');
        image.src = value;
        image.alt = '';
        image.decoding = 'async';
        image.className = 'avatar-image';
        container.append(image);
        return;
    }
    container.textContent = value || '👤';
}
```

- [ ] **步驟 6：執行頭像安全測試**

```powershell
python -m pytest tests/test_image_security.py::AvatarSecurityTests -v
```

預期：全部通過。

- [ ] **步驟 7：提交頭像安全修復**

```powershell
git add auth.py main.py data.py static/supabase.js static/app.js tests/test_image_security.py
git commit -m "fix: replace arbitrary avatar URLs with safe uploads"
```

### 任務 4：以 Pydantic model 約束 API 輸入

**檔案：**
- 新增：`api_models.py`
- 修改：`main.py`
- 新增測試：`tests/test_ai_validation.py`

- [ ] **步驟 1：先寫 request model 範圍測試**

```python
import unittest
from pydantic import ValidationError

from api_models import AccountUpdate, RecordCreate, RewardRedeem, ScanForm


class ApiModelTests(unittest.TestCase):
    def test_account_update_bounds_simulated_reward_data(self):
        with self.assertRaises(ValidationError):
            AccountUpdate(spent_points=-1)
        with self.assertRaises(ValidationError):
            AccountUpdate(claimed_coupons=[{"code": str(i)} for i in range(101)])

    def test_record_rejects_invalid_enum_and_score(self):
        with self.assertRaises(ValidationError):
            RecordCreate(name="Bottle", mode="admin", schema_id="food_new")
        with self.assertRaises(ValidationError):
            RecordCreate(name="Bottle", mode="dispose", schema_id="food_new", overall_score=101)

    def test_scan_form_bounds_prompt_and_language(self):
        with self.assertRaises(ValidationError):
            ScanForm(prompt="x" * 1001)
        with self.assertRaises(ValidationError):
            ScanForm(lang="unknown")
```

- [ ] **步驟 2：確認 model 測試紅燈**

```powershell
python -m pytest tests/test_ai_validation.py::ApiModelTests -v
```

預期：`api_models.py` 尚不存在。

- [ ] **步驟 3：新增 `api_models.py`**

```python
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from image_security import ALLOWED_AVATAR_EMOJI


class ClaimedCoupon(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9-]+$")
    title: str = Field(min_length=1, max_length=120)
    image: str = Field(default="", max_length=2048)
    cost: int = Field(default=0, ge=0, le=1_000_000)
    claimed_date: str = Field(default="", max_length=40)
    expiry: str = Field(default="", max_length=80)


class AccountUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    photoUrl: str | None = Field(default=None, max_length=8)
    spent_points: int | None = Field(default=None, ge=0, le=1_000_000, validation_alias=AliasChoices("spent_points", "spentPoints"))
    earned_points: int | None = Field(default=None, ge=0, le=1_000_000, validation_alias=AliasChoices("earned_points", "earnedPoints"))
    claimed_coupons: list[ClaimedCoupon] | None = Field(default=None, max_length=100, validation_alias=AliasChoices("claimed_coupons", "claimedCoupons"))

    @field_validator("photoUrl")
    @classmethod
    def validate_avatar(cls, value):
        if value is not None and value not in ALLOWED_AVATAR_EMOJI:
            raise ValueError("invalid avatar")
        return value


class RecordCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: Literal["dispose", "purchase"] = "dispose"
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    image_url: str | None = Field(default=None, max_length=2048)
    dealt_with_method: str = Field(default="", max_length=1000, validation_alias=AliasChoices("dealt_with_method", "dealtWithMethod", "disposal_guide"))
    eco_rate: int = Field(default=3, ge=0, le=5)
    recycle_rate: int = Field(default=4, ge=0, le=5)
    overall_score: int = Field(default=0, ge=0, le=100)
    material: str = Field(default="", max_length=40)
    grade: str = Field(default="", max_length=80)
    brand: str = Field(default="", max_length=120)
    category: str = Field(default="", max_length=80)
    weighted_scores: dict[str, int] = Field(default_factory=dict, validation_alias=AliasChoices("weighted_scores", "weightedScores"))
    schema_id: Literal["food_new", "food_expire", "item_new", "item_expire"] = Field(validation_alias=AliasChoices("schema_id", "schemaId"))
    alternative: dict | None = None
    precaution: str = Field(default="", max_length=1000)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value):
        if value and not value.startswith("/api/storage/"):
            raise ValueError("record image must be a server-generated storage URL")
        return value


class RewardRedeem(BaseModel):
    reward_id: str = Field(min_length=1, max_length=64)


class ScanForm(BaseModel):
    mode: Literal["dispose", "purchase"] = "dispose"
    item_type: Literal["food", "general"] = "food"
    item_state: Literal["new", "expire"] = "new"
    prompt: str = Field(default="", max_length=1000)
    lang: Literal["en", "zh_simplified", "zh_traditional"] = "en"
    debug: bool = False
```

若目前環境沒有 `email-validator`，不要使用 `EmailStr`；改為 Pydantic `str` 加 `field_validator`，避免引入未列出的隱藏依賴。

- [ ] **步驟 4：在路由邊界使用 model**

JSON 路由把 `data: dict` 改成對應 model，例如：

```python
@app.patch("/api/users/me")
async def update_current_user(
    payload: AccountUpdate,
    user: dict = Depends(require_current_user),
):
    updates = payload.model_dump(exclude_none=True)
    if not await save_user_data(int(user["id"]), updates):
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    refreshed = await get_user_by_id(int(user["id"]))
    return {"ok": True, "user": refreshed}
```

Form 路由在進入 service 前建立 `ScanForm(...)`；Pydantic 驗證錯誤由 FastAPI 統一回傳 `422`。

- [ ] **步驟 5：執行 model 與相關路由測試**

```powershell
python -m pytest tests/test_ai_validation.py::ApiModelTests tests/test_account_authorization.py tests/test_record_authorization.py -v
```

預期：全部通過。

- [ ] **步驟 6：提交 API schema**

```powershell
git add api_models.py main.py tests/test_ai_validation.py tests/test_account_authorization.py tests/test_record_authorization.py
git commit -m "fix: validate security-sensitive API payloads"
```

### 任務 5：驗證 AI 結果並限制自訂 endpoint

**檔案：**
- 修改：`api_models.py`
- 修改：`scan_service.py`
- 修改：`models.py`
- 修改：`config.py`
- 修改：`template.env`
- 修改測試：`tests/test_ai_validation.py`

- [ ] **步驟 1：先寫無效 AI 結果及不安全 endpoint 測試**

```python
import math

from api_models import AIScanResult


class AiResultValidationTests(unittest.TestCase):
    def test_invalid_material_and_score_are_rejected(self):
        payload = {
            "name": "Bottle",
            "material": "<script>",
            "eco_rate": 3,
            "recycle_rate": 4,
            "weighted_scores": {"a": 200, "b": 70, "c": 70, "d": 70, "e": 70},
        }
        with self.assertRaises(ValidationError):
            AIScanResult.model_validate(payload)

    def test_non_finite_score_is_rejected(self):
        with self.assertRaises(ValidationError):
            AIScanResult.model_validate({
                "name": "Bottle",
                "material": "plastic",
                "eco_rate": 3,
                "recycle_rate": 4,
                "weighted_scores": {"a": math.inf, "b": 70, "c": 70, "d": 70, "e": 70},
            })

    def test_production_custom_endpoint_requires_https(self):
        with patch.object(models, "IS_PRODUCTION", True):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                models.validate_custom_endpoint("http://example.com/v1")
```

- [ ] **步驟 2：確認 AI 驗證測試紅燈**

```powershell
python -m pytest tests/test_ai_validation.py::AiResultValidationTests -v
```

預期：`AIScanResult` 與 `validate_custom_endpoint()` 尚不存在。

- [ ] **步驟 3：新增嚴格 AI 結果 model**

```python
class AIScanResult(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand: str = Field(default="", max_length=120)
    category: str = Field(default="", max_length=80)
    standard_type: Literal["food", "general"] = "general"
    description: str = Field(default="", max_length=2000)
    material: Literal["plastic", "pp_plastic", "paper", "metal", "glass", "compostable", "wood"]
    disposal_guide: str = Field(default="", max_length=1500)
    reuse_tip: str = Field(default="", max_length=1000)
    precaution: str = Field(default="", max_length=1000)
    eco_rate: int = Field(ge=0, le=5)
    recycle_rate: int = Field(ge=0, le=5)
    weighted_scores: dict[Literal["a", "b", "c", "d", "e"], int]
    alternative: dict | None = None

    @field_validator("weighted_scores")
    @classmethod
    def validate_scores(cls, value):
        if set(value) != {"a", "b", "c", "d", "e"}:
            raise ValueError("weighted score keys must be a-e")
        if any(not isinstance(score, int) or score < 0 or score > 100 for score in value.values()):
            raise ValueError("weighted scores must be integers from 0 to 100")
        return value
```

在 `scan_service.py` 的遠端結果 normalize 後立即：

```python
validated = AIScanResult.model_validate(normalized)
result = validated.model_dump()
```

驗證失敗時，若本地模型可用便走現有 `local_scan_response()`；本地結果也必須通過同一 model。兩者皆失敗時回傳受控 `SCAN_RESULT_INVALID`。

- [ ] **步驟 4：限制自訂 endpoint 與回應大小**

`config.py`：

```python
MAX_AI_RESPONSE_BYTES = max(1024, int(os.getenv("MAX_AI_RESPONSE_BYTES", str(1024 * 1024))))
AI_REQUEST_TIMEOUT_SECONDS = min(180, max(5, int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "60"))))
```

`models.py`：

```python
from config import AI_REQUEST_TIMEOUT_SECONDS, IS_PRODUCTION, MAX_AI_RESPONSE_BYTES


def validate_custom_endpoint(base_url: str) -> str:
    parsed = urlsplit((base_url or "").strip())
    if not parsed.scheme or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Invalid custom AI endpoint")
    if IS_PRODUCTION and parsed.scheme.lower() != "https":
        raise ValueError("Production custom AI endpoint must use HTTPS")
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Invalid custom AI endpoint scheme")
    return parsed.geturl().rstrip("/")


async def read_bounded_response(response: httpx.Response) -> bytes:
    chunks = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_AI_RESPONSE_BYTES:
            raise ValueError("AI_RESPONSE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)
```

自訂 provider 使用 `client.stream()`，先檢查 status，再以 `read_bounded_response()` 讀取；錯誤訊息不得包含完整 endpoint、API key 或上游 body。

- [ ] **步驟 5：執行 AI 驗證與現有掃描測試**

```powershell
python -m pytest tests/test_ai_validation.py::AiResultValidationTests tests/test_cnn_scan.py -v
```

預期：全部通過；現有 provider fixture 如缺少必要欄位，要更新為符合正式 schema 的合法回應。

- [ ] **步驟 6：提交 AI 信任邊界**

```powershell
git add api_models.py scan_service.py models.py config.py template.env tests/test_ai_validation.py tests/test_cnn_scan.py
git commit -m "fix: validate AI results and bound provider responses"
```

### 任務 6：完成第四階段驗證

**檔案：**
- 不新增正式程式碼；只修正本階段引入的問題。

- [ ] **步驟 1：執行聚焦圖片與 AI 測試**

```powershell
python -m pytest tests/test_image_security.py tests/test_ai_validation.py tests/test_storage_upload_timing.py tests/test_cnn_scan.py -v
```

預期：全部通過。

- [ ] **步驟 2：執行原始惡意輸入檢查**

```powershell
python -m pytest tests/test_image_security.py -k "claimed_mime or byte_limit or pixel_count or arbitrary_photo" -v
python -m pytest tests/test_ai_validation.py -k "invalid_material or non_finite or requires_https" -v
```

預期：全部通過，證明原始觸發條件不再可利用。

- [ ] **步驟 3：搜尋仍然直接讀取或信任上傳資料的位置**

```powershell
rg -n "await file\.read\(\)|file\.content_type|photoUrl.*innerHTML|data:image" main.py data.py auth.py static templates
```

預期：正式上傳路由不再直接 `file.read()` 或信任 `content_type`；只保留與受控顯示或測試有關的命中。

- [ ] **步驟 4：執行完整測試**

```powershell
python -m pytest tests -v
```

預期：沒有新增失敗；既有天氣 baseline 獨立報告。

- [ ] **步驟 5：提交驗證調整**

```powershell
git add image_security.py api_models.py main.py data.py auth.py models.py scan_service.py static/supabase.js static/app.js config.py template.env tests/test_image_security.py tests/test_ai_validation.py tests/test_storage_upload_timing.py tests/test_cnn_scan.py tests/test_account_authorization.py tests/test_record_authorization.py
git commit -m "test: verify upload and AI input hardening"
```
