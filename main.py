"""Re-Life API — FastAPI entry point."""
from pathlib import Path
from dotenv import load_dotenv

root_dir = Path(__file__).parent
load_dotenv(root_dir / ".env")

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.middleware.base import BaseHTTPMiddleware
from io import BytesIO
import json
import os, random, re, uuid
from typing import Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator, model_validator

from agent import (
    AgentConsentRequired,
    AgentConversationNotFound,
    AgentInputError,
    AgentNotConfigured,
    AgentProtocolError,
    AgentSafetyViolation,
    AgentSafetyUnavailable,
    AgentSandboxService,
    AgentToolNotAllowed,
    OpenAIAgentMemorySummarizer,
    SupabaseAgentConversationStore,
    SupabaseAgentMemoryStore,
)

from auth import (
    AuthDependencyUnavailable,
    CurrentAccountUpdate,
    check_rate_limit,
    create_user,
    get_user_by_internal_id,
    login_user,
    normalize_user_row,
    save_user_data,
    send_reset_code,
    send_verification_code,
    update_password,
    verify_reset_code,
)
from config import (
    ALLOWED_IMAGE_TYPES,
    ALLOW_DEV_AUTH_CODES,
    IS_DEVELOPMENT,
    MAX_UPLOAD_BYTES,
    SESSION_COOKIE_NAME,
    SUPABASE_STORAGE_BUCKET,
    get_public_config,
)
from data import (
    add_item,
    canonicalize_owner_id,
    clear_all_items,
    delete_item,
    get_items,
    get_news_cached,
    persist_record_image,
)
from models import ai_analyze, local_scan_response
from recycling_points import find_nearby_recycling_points
from scan_service import analyze_scan_image, enrich_scan_result, normalize_scan_payload, parse_bool
from scoring import CRITERIA_LABELS, HK_DISPOSAL, REWARDS_CATALOG, SCHEMA_WEIGHTS
from sessions import (
    SecurityStoreUnavailable,
    SessionMiddleware,
    clear_session_cookie,
    create_session,
    optional_current_user,
    require_current_user,
    revoke_all_user_sessions,
    revoke_session,
    set_session_cookie,
)
from storage import supabase_storage_download, verify_supabase_storage_signature
from weather import get_header_weather


FACTS_CATALOG = (
    {"id": "aluminum-can-energy", "fact": "Recycling a single aluminum can saves enough energy to power a TV for 3 hours."},
    {"id": "hong-kong-daily-waste", "fact": "Hong Kong generates over 15,000 tonnes of municipal solid waste every day."},
    {"id": "tree-carbon-absorption", "fact": "One tree can absorb up to 22kg of CO2 per year."},
    {"id": "plastic-bottle-decomposition", "fact": "Plastic bottles take up to 450 years to decompose."},
    {"id": "hong-kong-food-waste", "fact": "Food waste accounts for 30% of HK municipal solid waste."},
    {"id": "glass-endless-recycling", "fact": "Glass is 100% recyclable endlessly without quality loss."},
)

app = FastAPI(title="Re-Life API")
CURRENT_ACCOUNT_UPDATE_BODY_MAX_BYTES = 1_258_292
CURRENT_ACCOUNT_UPDATE_MAX_TOP_LEVEL_KEYS = 32
CURRENT_ACCOUNT_UPDATE_MAX_VALIDATION_ERRORS = 20
CLAIMED_COUPON_INPUT_FIELDS = frozenset({
    "code",
    "id",
    "title",
    "provider",
    "cost",
    "image",
    "category",
    "description",
    "claimedDate",
    "expiry",
})
INVALID_ACCOUNT_UPDATE_SHAPE_DETAIL = [{
    "type": "invalid_account_update_shape",
    "loc": ["body"],
    "msg": "INVALID_ACCOUNT_UPDATE_SHAPE",
}]
FORGED_RECORD_IDENTITY_FIELDS = frozenset({
    "user_id",
    "userId",
    "userName",
    "user_key",
    "userKey",
    "display_name",
})
MULTIPART_BODY_OVERHEAD_BYTES = 256 * 1024
MAX_MULTIPART_REQUEST_BYTES = MAX_UPLOAD_BYTES + MULTIPART_BODY_OVERHEAD_BYTES
UPLOAD_READ_CHUNK_BYTES = 64 * 1024


@app.exception_handler(AuthDependencyUnavailable)
async def auth_dependency_unavailable_handler(
    request: Request,
    _exc: AuthDependencyUnavailable,
):
    response = JSONResponse(
        {"error": "AUTH_SERVICE_UNAVAILABLE"},
        status_code=503,
    )
    if request.url.path == "/api/reset-password":
        clear_session_cookie(response)
    return response


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: StrictStr = Field(
        min_length=2,
        validation_alias=AliasChoices("display_name", "displayName"),
    )
    email: StrictStr = Field(min_length=3, max_length=320)
    password: StrictStr = Field(min_length=8)
    verification_code: StrictStr = Field(
        pattern=r"^[0-9]{6}$",
        validation_alias=AliasChoices("verification_code", "code"),
    )

    @field_validator("display_name", "email", "verification_code", mode="before")
    @classmethod
    def strip_registration_values(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalize_registration_email(cls, value: str) -> str:
        normalized = value.lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("INVALID_EMAIL")
        return normalized


class AgentLocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100_000)


class AgentApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["read_user_records"]
    request_id: StrictStr = Field(min_length=1, max_length=256)
    approved: bool


class AgentImageAnalysisInput(BaseModel):
    """Bounded visual observations produced by Re-Life's image scanner."""

    model_config = ConfigDict(extra="forbid")

    name: StrictStr | None = Field(default=None, min_length=1, max_length=160)
    brand: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    category: StrictStr | None = Field(default=None, min_length=1, max_length=120)
    material: StrictStr | None = Field(default=None, min_length=1, max_length=160)
    waste_type: StrictStr | None = Field(default=None, min_length=1, max_length=80)
    description: StrictStr | None = Field(default=None, min_length=1, max_length=800)

    @field_validator(
        "name",
        "brand",
        "category",
        "material",
        "waste_type",
        "description",
        mode="before",
    )
    @classmethod
    def strip_image_observations(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_an_image_observation(self):
        if not any((self.name, self.brand, self.category, self.material, self.waste_type, self.description)):
            raise ValueError("image_analysis must include at least one observation")
        return self


class AgentMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: StrictStr | None = Field(default=None, min_length=1, max_length=256)
    message: StrictStr | None = Field(default=None, min_length=1, max_length=2000)
    location: AgentLocationInput | None = None
    location_error: Literal["denied", "unavailable", "timeout"] | None = None
    approval: AgentApprovalInput | None = None
    request_id: StrictStr | None = Field(default=None, min_length=1, max_length=256)
    image_analysis: AgentImageAnalysisInput | None = None
    language: Literal["en", "zh_simplified", "zh_traditional"] = "en"
    data_consent: bool = False

    @field_validator("message", "conversation_id", "request_id", mode="before")
    @classmethod
    def strip_agent_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_agent_turn(self):
        actions = (
            self.message is not None,
            self.location is not None or self.location_error is not None,
            self.approval is not None,
        )
        if sum(actions) != 1:
            raise ValueError("Send one message, location response, or approval response")
        if not self.message and not self.conversation_id:
            raise ValueError("conversation_id is required to resume an agent action")
        if self.image_analysis is not None and self.message is None:
            raise ValueError("image_analysis is only accepted with a message")
        if (self.location is not None or self.location_error is not None) and not self.request_id:
            raise ValueError("request_id is required for a location response")
        return self


class MultipartBodyTooLarge(Exception):
    pass


class InvalidMultipartForm(Exception):
    pass


class ImageFileTooLarge(Exception):
    pass


class InvalidImageFile(Exception):
    pass

# ── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["*"])

app.add_middleware(SessionMiddleware)

# ── Security Headers ────────────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=self, microphone=(), geolocation=(self)"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── Static files ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=root_dir / "static"), name="static")

def _page(path: str) -> str:
    return (root_dir / "templates" / path).read_text(encoding="utf-8")


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _normalized_rate_subject(value) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _session_owner_id(user: dict) -> int:
    try:
        return canonicalize_owner_id(user.get("id"))
    except (AttributeError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail="AUTHENTICATION_REQUIRED",
        ) from exc


_AGENT_RECORD_QUERY_ALIASES = {
    "phone": {"phone", "smartphone", "mobile", "iphone", "android", "handset", "手機", "手机", "電話", "电话"},
    "computer": {"computer", "laptop", "notebook", "macbook", "pc", "電腦", "电脑", "筆電", "笔电"},
    "tablet": {"tablet", "ipad", "平板"},
    "headphones": {"headphone", "headphones", "earbuds", "airpods", "耳機", "耳机"},
    "television": {"tv", "television", "smart tv", "電視", "电视"},
    "washing_machine": {"washing machine", "washer", "laundry machine", "洗衣機", "洗衣机"},
    "refrigerator": {"refrigerator", "fridge", "freezer", "雪櫃", "雪柜", "冰箱"},
    "air_conditioner": {"air conditioner", "air conditioning", "冷氣機", "冷气机", "空調", "空调"},
    "camera": {"camera", "digital camera", "相機", "相机"},
    "watch": {"watch", "smartwatch", "smart watch", "手錶", "手表", "智能手錶", "智能手表"},
    "shoes": {"shoe", "shoes", "sneaker", "sneakers", "trainer", "trainers", "footwear", "鞋", "鞋子"},
    "furniture": {"furniture", "sofa", "couch", "chair", "table", "家具", "沙發", "沙发", "椅", "桌"},
    "bicycle": {"bicycle", "bike", "cycle", "單車", "单车", "自行車", "自行车"},
    "printer": {"printer", "印表機", "打印機", "打印机"},
    "vacuum": {"vacuum", "vacuum cleaner", "hoover", "吸塵機", "吸尘器"},
}
_AGENT_RECORD_QUERY_STOPWORDS = {
    "a", "an", "another", "current", "my", "new", "old", "the", "this",
}


def _agent_record_query_terms(query: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", str(query or "").strip().lower())[:80]
    terms = {
        token
        for token in re.findall(r"[\w\-]+", normalized, flags=re.UNICODE)
        if len(token) > 1 and token not in _AGENT_RECORD_QUERY_STOPWORDS
    }
    for aliases in _AGENT_RECORD_QUERY_ALIASES.values():
        if any(alias in normalized for alias in aliases):
            terms.update(aliases)
    return terms


async def _agent_recent_records(
    *,
    user_id: int,
    limit: int,
    query: str = "",
) -> list[dict]:
    records = await get_items(owner_id=user_id)
    terms = _agent_record_query_terms(query)
    if terms:
        searchable_fields = (
            "name",
            "brand",
            "category",
            "material",
            "description",
            "dealtWithMethod",
        )
        records = [
            record
            for record in records
            if any(
                term in " ".join(
                    str(record.get(field) or "").lower()
                    for field in searchable_fields
                )
                for term in terms
            )
        ]
    return records[: max(1, min(10, int(limit)))]


def _agent_recycling_guide(material: str) -> dict:
    normalized = re.sub(r"[^a-z_]", "", str(material or "").strip().lower().replace("-", "_"))
    aliases = {
        "plastics": "plastic",
        "plasticbottle": "plastic",
        "cardboard": "paper",
        "aluminium": "metal",
        "aluminum": "metal",
        "can": "metal",
        "bottle": "glass",
        "foodwaste": "compostable",
        "organic": "compostable",
        "ewaste": "ewaste",
        "electronic": "ewaste",
    }
    key = aliases.get(normalized, normalized)
    if key == "ewaste":
        return {
            "type": "Electronic waste",
            "method": "Keep batteries safe and separate when practical",
            "location": "GREEN@COMMUNITY or an approved e-waste collection point",
        }
    guidance = HK_DISPOSAL.get(key)
    if guidance:
        return dict(guidance)
    return {
        "error": "No specific local guide is available for that material.",
        "supported_materials": sorted([*HK_DISPOSAL, "ewaste"]),
    }


agent_service = AgentSandboxService(
    recycling_lookup=find_nearby_recycling_points,
    weather_lookup=get_header_weather,
    records_lookup=_agent_recent_records,
    guide_lookup=_agent_recycling_guide,
    conversation_store=SupabaseAgentConversationStore(),
    memory_store=SupabaseAgentMemoryStore(),
    memory_summarizer=OpenAIAgentMemorySummarizer(),
)


def _install_multipart_receive_limit(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = None
        if (
            declared_length is not None
            and declared_length > MAX_MULTIPART_REQUEST_BYTES
        ):
            raise MultipartBodyTooLarge

    original_receive = request._receive
    received_bytes = 0

    async def bounded_receive():
        nonlocal received_bytes
        message = await original_receive()
        if message.get("type") == "http.request":
            received_bytes += len(message.get("body", b""))
            if received_bytes > MAX_MULTIPART_REQUEST_BYTES:
                raise MultipartBodyTooLarge
        return message

    request._receive = bounded_receive


def _matches_declared_image_type(contents: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return contents.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return contents.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return (
            len(contents) >= 12
            and contents.startswith(b"RIFF")
            and contents[8:12] == b"WEBP"
        )
    return False


async def _read_bounded_validated_image(
    request: Request,
) -> tuple[object, StarletteUploadFile, bytes, str]:
    _install_multipart_receive_limit(request)
    try:
        form = await request.form()
    except MultipartBodyTooLarge:
        raise
    except Exception as exc:
        raise InvalidMultipartForm from exc

    file = form.get("file")
    if not isinstance(file, StarletteUploadFile):
        raise InvalidImageFile
    content_type = file.content_type
    if not content_type or content_type not in ALLOWED_IMAGE_TYPES:
        raise InvalidImageFile

    contents = bytearray()
    try:
        while True:
            remaining = MAX_UPLOAD_BYTES - len(contents)
            chunk = await file.read(min(UPLOAD_READ_CHUNK_BYTES, remaining + 1))
            if not chunk:
                break
            contents.extend(chunk)
            if len(contents) > MAX_UPLOAD_BYTES:
                raise ImageFileTooLarge
    except ImageFileTooLarge:
        raise
    except Exception as exc:
        raise InvalidImageFile from exc

    image_bytes = bytes(contents)
    if not _matches_declared_image_type(image_bytes, content_type):
        raise InvalidImageFile
    return form, file, image_bytes, content_type


@app.get("/api/storage/{bucket}/{object_path:path}")
async def storage_object(request: Request, bucket: str, object_path: str, exp: str | None = None, sig: str | None = None):
    bucket_name = bucket.strip("/")
    allowed_buckets = {name for name in {SUPABASE_STORAGE_BUCKET.strip("/") if SUPABASE_STORAGE_BUCKET else "", "imgs", "scan-images"} if name}
    if not bucket_name or bucket_name not in allowed_buckets or not object_path:
        return JSONResponse({"error": "Not found"}, 404)
    if not verify_supabase_storage_signature(bucket_name, object_path, exp, sig):
        return JSONResponse({"error": "Forbidden"}, 403)

    try:
        content, content_type = await supabase_storage_download(bucket_name, object_path)
    except Exception as e:
        message = str(e)
        if any(code in message for code in (" 400", " 403", " 404")):
            return JSONResponse({"error": "Not found"}, 404)
        return JSONResponse({"error": "Storage unavailable"}, 502)

    response = StreamingResponse(BytesIO(content), media_type=content_type)
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    return response

# ── Pages ───────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def public_config():
    return JSONResponse(get_public_config())


@app.get("/api/weather/header")
async def weather_header(request: Request, lat: float | None = None, lon: float | None = None):
    await check_rate_limit(request, 60, 60)
    payload = await get_header_weather(latitude=lat, longitude=lon)
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "private, max-age=300"
    return response

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    await check_rate_limit(request, 60, 60)
    if not optional_current_user(request):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(_page("index.html"))

@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    await check_rate_limit(request, 5, 60)
    return HTMLResponse(_page("login.html"))

@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    await check_rate_limit(request, 5, 60)
    return HTMLResponse(_page("register.html"))

# ── Storage endpoints ──────────────────────────────────────────────────────

@app.post("/api/auth/register")
async def auth_register(request: Request, data: dict):
    request.state.suppress_session_refresh = True
    await check_rate_limit(
        request,
        5,
        60,
        subject=_normalized_rate_subject(data.get("email")),
    )
    try:
        registration = RegistrationRequest.model_validate(data)
    except ValidationError:
        return JSONResponse(
            {"detail": "INVALID_REGISTRATION_INPUT"},
            status_code=422,
        )
    try:
        user = await create_user(
            registration.display_name,
            registration.password,
            registration.email,
            verification_code=registration.verification_code,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 400)
    return {"ok": True, "user": user}


@app.post("/api/auth/login")
async def auth_login(request: Request, data: dict):
    request.state.suppress_session_refresh = True
    rate_subject = data.get("display_name") or data.get("displayName")
    await check_rate_limit(
        request,
        5,
        60,
        subject=_normalized_rate_subject(rate_subject),
    )
    display_name = (data.get("display_name") or data.get("displayName") or "").strip()
    password = data.get("password") or ""
    try:
        user = await login_user(display_name, password)
        token = await create_session(
            user,
            user_agent=request.headers.get("user-agent", ""),
            request_ip=_request_ip(request),
        )
    except SecurityStoreUnavailable:
        return JSONResponse({"error": "AUTH_SERVICE_UNAVAILABLE"}, 503)
    except ValueError as e:
        if str(e) == "INVALID_CREDENTIALS":
            return JSONResponse({"error": "INVALID_CREDENTIALS"}, 401)
        raise
    response = JSONResponse({"ok": True, "user": normalize_user_row(user)})
    set_session_cookie(response, token)
    return response


@app.get("/api/auth/me")
async def auth_me(user: dict = Depends(require_current_user)):
    return {"ok": True, "user": normalize_user_row(user)}


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    request.state.suppress_session_refresh = True
    try:
        await revoke_session(token)
    except SecurityStoreUnavailable:
        response = JSONResponse(
            {"error": "AUTH_SERVICE_UNAVAILABLE"},
            status_code=503,
        )
    else:
        response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response


@app.get("/api/users/me")
async def current_user(user: dict = Depends(require_current_user)):
    return normalize_user_row(user)


def _has_invalid_account_update_shape(raw_data) -> bool:
    if not isinstance(raw_data, dict):
        return False
    if len(raw_data) > CURRENT_ACCOUNT_UPDATE_MAX_TOP_LEVEL_KEYS:
        return True
    for alias in ("claimed_coupons", "claimedCoupons"):
        coupons = raw_data.get(alias)
        if not isinstance(coupons, list):
            continue
        if len(coupons) > 100:
            return True
        for coupon in coupons:
            if not isinstance(coupon, dict):
                continue
            if (
                len(coupon) > len(CLAIMED_COUPON_INPUT_FIELDS)
                or not coupon.keys() <= CLAIMED_COUPON_INPUT_FIELDS
            ):
                return True
    return False


@app.patch("/api/users/me")
async def update_current_user(
    request: Request,
    user: dict = Depends(require_current_user),
):
    await check_rate_limit(request, 30, 60)

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            return JSONResponse({"error": "INVALID_CONTENT_LENGTH"}, 400)
        if declared_length < 0:
            return JSONResponse({"error": "INVALID_CONTENT_LENGTH"}, 400)
        if declared_length > CURRENT_ACCOUNT_UPDATE_BODY_MAX_BYTES:
            return JSONResponse({"error": "PAYLOAD_TOO_LARGE"}, 413)

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > CURRENT_ACCOUNT_UPDATE_BODY_MAX_BYTES:
            return JSONResponse({"error": "PAYLOAD_TOO_LARGE"}, 413)
        body.extend(chunk)

    try:
        raw_data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse({"error": "INVALID_JSON"}, 400)

    if _has_invalid_account_update_shape(raw_data):
        return JSONResponse({"detail": INVALID_ACCOUNT_UPDATE_SHAPE_DETAIL}, 422)

    try:
        data = CurrentAccountUpdate.model_validate(raw_data)
    except ValidationError as exc:
        errors = exc.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )
        detail = [
            {
                "type": error["type"],
                "loc": [
                    "body",
                    *[
                        part
                        if not isinstance(part, str) or (
                            len(part) <= 64
                            and all(ord(char) >= 32 for char in part)
                        )
                        else "<field>"
                        for part in error["loc"]
                    ],
                ],
                "msg": error["msg"][:256],
            }
            for error in errors[:CURRENT_ACCOUNT_UPDATE_MAX_VALIDATION_ERRORS]
        ]
        if len(errors) > CURRENT_ACCOUNT_UPDATE_MAX_VALIDATION_ERRORS:
            detail.append({
                "type": "too_many_validation_errors",
                "loc": ["body"],
                "msg": "TOO_MANY_VALIDATION_ERRORS",
            })
        return JSONResponse({"detail": detail}, 422)

    user_id = int(user["id"])
    update_data = data.model_dump(exclude_unset=True)
    if not await save_user_data(user_id, update_data):
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    refreshed_user = await get_user_by_internal_id(user_id)
    if not refreshed_user:
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    return {"ok": True, "user": refreshed_user}


@app.get("/api/records")
async def list_records(
    request: Request,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 60, 60)
    return await get_items(owner_id=owner_id)


@app.post("/api/records/image")
async def upload_record_image(
    request: Request,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 30, 60)
    try:
        _form, file, contents, content_type = await _read_bounded_validated_image(request)
    except (MultipartBodyTooLarge, ImageFileTooLarge):
        return JSONResponse({"error": "File too large"}, 413)
    except InvalidMultipartForm:
        return JSONResponse({"error": "Invalid upload form"}, 400)
    except InvalidImageFile:
        return JSONResponse({"error": "Invalid image file"}, 400)

    try:
        image_url = await persist_record_image(
            contents,
            file.filename or "scan-record.jpg",
            content_type,
            owner_key=owner_id,
        )
    except Exception:
        return JSONResponse({"error": "Image upload failed"}, 502)
    return JSONResponse({"image_url": image_url})


@app.post("/api/records")
async def create_record(
    request: Request,
    data: dict,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 30, 60)
    record_data = {
        key: value
        for key, value in (data or {}).items()
        if key not in FORGED_RECORD_IDENTITY_FIELDS
    }
    try:
        result = await add_item(record_data, owner_id=owner_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 400)
    except Exception:
        return JSONResponse({"error": "Record save failed"}, 502)
    return {"ok": True, **result}


@app.delete("/api/records")
async def clear_records(
    request: Request,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 30, 60)
    await clear_all_items(owner_id=owner_id)
    return {"ok": True}


@app.delete("/api/records/{item_id}")
async def delete_record(
    request: Request,
    item_id: str,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 30, 60)
    if not await delete_item(item_id, owner_id=owner_id):
        return JSONResponse({"error": "Record not found"}, 404)
    return {"ok": True}

# ── Auth endpoints ──────────────────────────────────────────────────────────

@app.post("/api/send-verification")
async def send_verification(request: Request, data: dict):
    email = _normalized_rate_subject(data.get("email"))
    await check_rate_limit(request, 5, 60, subject=email)
    if not email or "@" not in email:
        return JSONResponse({"error": "Valid email required"}, 400)
    dev_code = await send_verification_code(email)
    include_dev_code = IS_DEVELOPMENT and ALLOW_DEV_AUTH_CODES and dev_code
    return JSONResponse(
        {
            "ok": True,
            **({"dev_code": dev_code} if include_dev_code else {}),
        }
    )

@app.post("/api/forgot-password")
async def forgot_password(request: Request, data: dict):
    email = _normalized_rate_subject(data.get("email"))
    await check_rate_limit(request, 3, 120, subject=email)
    if not email:
        return JSONResponse({"error": "Email required"}, 400)
    try:
        await send_reset_code(email)
    except AuthDependencyUnavailable:
        pass
    return JSONResponse({"ok": True})

@app.post("/api/reset-password")
async def reset_password(request: Request, data: dict):
    request.state.suppress_session_refresh = True
    email = _normalized_rate_subject(data.get("email"))
    await check_rate_limit(request, 5, 60, subject=email)
    code = (data.get("code") or "").strip()
    password = data.get("password", "")
    if not email or not code or len(password) < 8:
        return JSONResponse({"error": "Email, code, and new password (8+ chars) required"}, 400)
    try:
        user = await verify_reset_code(email, code)
        if not user:
            return JSONResponse({"error": "Invalid or expired code"}, 400)
        user_id = canonicalize_owner_id(user.get("id"))
        await revoke_all_user_sessions(user_id)
        if not await update_password(email, password):
            raise AuthDependencyUnavailable("Password update failed")
    except Exception:
        response = JSONResponse({"error": "AUTH_SERVICE_UNAVAILABLE"}, 503)
        clear_session_cookie(response)
        return response
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response

# ── Scan endpoints ──────────────────────────────────────────────────────────

@app.post("/api/scan/ai")
async def scan_item_ai(
    request: Request,
    user: dict = Depends(require_current_user),
):
    _session_owner_id(user)
    await check_rate_limit(request, 15, 60)
    try:
        form, file, contents, _content_type = await _read_bounded_validated_image(request)
    except (MultipartBodyTooLarge, ImageFileTooLarge):
        return JSONResponse({"error": "File too large"}, 413)
    except InvalidMultipartForm:
        return JSONResponse({"error": "Invalid upload form"}, 400)
    except InvalidImageFile:
        return JSONResponse({"error": "Invalid image file"}, 400)

    mode = str(form.get("mode") or "dispose")
    item_type = str(form.get("item_type") or "food")
    item_state = str(form.get("item_state") or "new")
    debug = str(form.get("debug") or "false")
    prompt = str(form.get("prompt") or "")
    lang = str(form.get("lang") or "en")
    sid = f"{item_type}_{item_state}"
    try:
        ai = await analyze_scan_image(
            contents,
            sid,
            mode,
            force_local=parse_bool(debug),
            prompt=prompt.strip() or None,
            language=lang.strip() or "en",
            remote_analyzer=ai_analyze,
            local_analyzer=local_scan_response,
        )
    except Exception:
        return JSONResponse({"error": "Image analysis failed", "mode": mode, "schema_id": sid}, 500)

    ai = await normalize_scan_payload(ai, contents, file.filename, mode, sid)
    ai = enrich_scan_result(ai, sid)
    return JSONResponse(ai)

# ── Data endpoints ──────────────────────────────────────────────────────────

@app.get("/api/news")
async def news(request: Request):
    await check_rate_limit(request, 30, 120)
    return await get_news_cached()

@app.get("/api/schemas")
async def schemas(request: Request):
    await check_rate_limit(request, 60, 60)
    return {"item_types": [{"value": "food", "label": "Food Items"}, {"value": "general", "label": "General Items"}],
            "item_states": [{"value": "new", "label": "New Purchase"}, {"value": "expire", "label": "About to Expire"}],
            "weights": SCHEMA_WEIGHTS, "criteria_labels": CRITERIA_LABELS}

@app.get("/api/rewards")
async def rewards(request: Request):
    await check_rate_limit(request, 60, 60)
    return REWARDS_CATALOG


@app.get("/api/recycling/nearby")
async def nearby_recycling_points(request: Request, lat: float, lon: float, material: str | None = None,
                                  limit: int = 5, distance_km: int = 3):
    await check_rate_limit(request, 30, 60)
    if not (22.0 <= lat <= 22.7 and 113.7 <= lon <= 114.5):
        return JSONResponse({"error": "Valid Hong Kong coordinates required"}, 400)

    safe_limit = min(max(int(limit or 5), 1), 8)
    safe_distance = min(max(int(distance_km or 3), 1), 10)
    try:
        return await find_nearby_recycling_points(lat, lon, material=material, limit=safe_limit, distance_km=safe_distance)
    except Exception:
        return JSONResponse({"error": "Recycling map unavailable"}, 502)


@app.post("/api/agent/messages")
async def agent_messages(
    request: Request,
    data: AgentMessageRequest,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 20, 60, subject=f"agent:{owner_id}")
    try:
        respond_args = {
            "user_id": owner_id,
            "message": data.message,
            "conversation_id": data.conversation_id,
            "location": data.location.model_dump() if data.location else None,
            "location_error": data.location_error,
            "approval": data.approval.model_dump() if data.approval else None,
            "request_id": data.request_id,
            "language": data.language,
            "data_consent": data.data_consent,
        }
        if data.image_analysis is not None:
            respond_args["image_analysis"] = data.image_analysis.model_dump(exclude_none=True)
        payload = await agent_service.respond(
            **respond_args,
        )
    except AgentConsentRequired:
        return JSONResponse({"error": "AGENT_DATA_CONSENT_REQUIRED"}, 403)
    except AgentConversationNotFound:
        return JSONResponse({"error": "AGENT_CONVERSATION_NOT_FOUND"}, 404)
    except AgentInputError as exc:
        return JSONResponse({"error": str(exc)}, 400)
    except AgentSafetyViolation:
        return JSONResponse({"error": "AGENT_SAFETY_BLOCKED"}, 400)
    except AgentSafetyUnavailable:
        return JSONResponse({"error": "AGENT_SAFETY_UNAVAILABLE"}, 503)
    except AgentNotConfigured:
        return JSONResponse({"error": "AGENT_NOT_CONFIGURED"}, 503)
    except (AgentProtocolError, AgentToolNotAllowed):
        return JSONResponse({"error": "AGENT_TOOL_ERROR"}, 502)
    except Exception:
        return JSONResponse({"error": "AGENT_UNAVAILABLE"}, 502)
    return JSONResponse(payload)


@app.get("/api/agent/conversations")
async def list_agent_conversations(
    request: Request,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 30, 60, subject=f"agent:{owner_id}")
    return await agent_service.list_conversations(owner_id)


@app.get("/api/agent/memory")
async def get_agent_memory(
    request: Request,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 30, 60, subject=f"agent:{owner_id}")
    return await agent_service.get_memory(owner_id)


@app.delete("/api/agent/memory")
async def delete_agent_memory(
    request: Request,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 10, 60, subject=f"agent:{owner_id}")
    await agent_service.clear_memory(owner_id)
    return {"ok": True}


@app.get("/api/agent/conversations/{conversation_id}")
async def get_agent_conversation(
    request: Request,
    conversation_id: str,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 30, 60, subject=f"agent:{owner_id}")
    try:
        return await agent_service.get_conversation(owner_id, conversation_id)
    except AgentConversationNotFound:
        return JSONResponse({"error": "AGENT_CONVERSATION_NOT_FOUND"}, 404)


@app.delete("/api/agent/conversations/{conversation_id}")
async def delete_agent_conversation(
    request: Request,
    conversation_id: str,
    user: dict = Depends(require_current_user),
):
    owner_id = _session_owner_id(user)
    await check_rate_limit(request, 20, 60, subject=f"agent:{owner_id}")
    if not await agent_service.destroy(owner_id, conversation_id):
        return JSONResponse({"error": "AGENT_CONVERSATION_NOT_FOUND"}, 404)
    return {"ok": True}


@app.post("/api/rewards/redeem")
async def redeem(
    request: Request,
    data: dict,
    user: dict = Depends(require_current_user),
):
    _session_owner_id(user)
    await check_rate_limit(request, 30, 60)
    reward = next((r for r in REWARDS_CATALOG if r["id"] == data.get("reward_id")), None)
    if not reward: return JSONResponse({"error": "Not found"}, 404)
    code = "RL-" + uuid.uuid4().hex[:6].upper() + "-" + str(reward["cost"])
    return {"ok": True, "coupon": {"code": code, "title": reward["title"], "image": reward["image"], "cost": reward["cost"], "claimed_date": "Just now", "expiry": "Valid 30 days"}}

@app.get("/api/fact")
async def fact(request: Request):
    await check_rate_limit(request, 60, 60)
    return dict(random.choice(FACTS_CATALOG))

if __name__ == "__main__":
    import uvicorn; uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
