"""Re-Life API — FastAPI entry point."""
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
from io import BytesIO
import re, uuid, os, random, traceback, time
from pathlib import Path
from datetime import datetime

from config import *
from data import *
from models import *
from storage import supabase_storage_download, verify_supabase_storage_signature
from auth import *
from weather import get_header_weather

root_dir = Path(__file__).parent
if os.path.exists(root_dir / ".env"):
    load_dotenv()

app = FastAPI(title="Re-Life API")

# ── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["*"])

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

def _infer_waste_type(payload: dict) -> str:
    haystack = " ".join(
        str(payload.get(key, ""))
        for key in ("waste_type", "material", "category", "name", "description")
    ).lower()
    if "glass" in haystack:
        return "glass"
    if any(token in haystack for token in ("metal", "aluminum", "aluminium", "steel", "tin")):
        return "metal"
    if any(token in haystack for token in ("organic", "compost", "food")):
        return "organic"
    if any(token in haystack for token in ("paper", "cardboard", "carton", "wood")):
        return "paper"
    if any(token in haystack for token in ("ewaste", "e-waste", "electronic")):
        return "ewaste"
    return "plastic"


def _as_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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

async def _normalize_scan_payload(ai: dict, contents: bytes, filename: str, mode: str, sid: str) -> dict:
    result = dict(ai or {})
    ext = Path(str(filename)).suffix or ".png"
    fn = f"{uuid.uuid4()}{ext}"
    result["image_url"] = await upload_image(contents, fn)
    result["mode"] = mode
    result["id"] = result.get("id") or str(uuid.uuid4())
    result["timestamp"] = datetime.now().isoformat()
    result["schema_id"] = sid
    if mode != "purchase":
        result["alternative"] = None

    waste_type = result.get("waste_type") or _infer_waste_type(result)
    result["waste_type"] = waste_type

    is_local = (
        result.get("runtime_source") == "onnxruntime"
        or result.get("model_source") == "transformer"
        or result.get("classifier_source") in {"nlp", "transformer"}
    )
    result.setdefault("classifier_source", "nlp" if is_local else DEFAULT_AI_MODEL)
    result.setdefault("model_source", "transformer" if is_local else DEFAULT_AI_MODEL)
    result.setdefault("runtime_source", "onnxruntime" if is_local else "remote")
    result.setdefault("artifact", "model_fp16.onnx" if is_local else result.get("model_source", DEFAULT_AI_MODEL))
    result.setdefault("waste_label", CNN_LABELS.get(waste_type, waste_type.replace("_", " ").title()))

    text = result.get("text") or result.get("description") or result.get("disposal_guide") or f"{result['waste_label']} waste."
    result["text"] = text
    if not result.get("tokens"):
        result["tokens"] = [token for token in re.findall(r"[A-Za-z0-9]+", text.lower()) if token]
    result.setdefault("confidence", 0.0)
    return result


async def _analyze_scan_image(
    contents: bytes,
    sid: str,
    mode: str,
    *,
    force_local: bool = False,
) -> dict:
    if force_local:
        print("[Classifier] Debug mode enabled; using local transformer")
        return local_scan_response(contents, mode)

    try:
        return await ai_analyze(contents, sid)
    except Exception as remote_e:
        print(f"[Classifier] Remote AI error: {str(remote_e)[:200]}")
        try:
            ai = local_scan_response(contents, mode)
            ai["ai_error"] = "AI failed to call, using fallback."
            ai["fallback_used"] = True
            return ai
        except Exception as cls_e:
            print(f"[Classifier] Local transformer error: {str(cls_e)[:200]}")
            raise

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
    await check_rate_limit(request, 5, 60)
    display_name = (data.get("display_name") or data.get("displayName") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    try:
        user = await create_user(display_name, password, email or None)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 400)
    return {"ok": True, "user": user}


@app.post("/api/auth/login")
async def auth_login(request: Request, data: dict):
    await check_rate_limit(request, 5, 60)
    display_name = (data.get("display_name") or data.get("displayName") or "").strip()
    password = data.get("password") or ""
    try:
        user = await login_user(display_name, password)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 400)
    return {"ok": True, "user": user}


@app.get("/api/users")
async def list_users(request: Request):
    await check_rate_limit(request, 60, 60)
    return await get_all_users()


@app.get("/api/users/by-name/{display_name}")
async def user_by_name(request: Request, display_name: str):
    await check_rate_limit(request, 60, 60)
    user = await get_user_by_name(display_name)
    if not user:
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    return user


@app.get("/api/users/by-email/{email}")
async def user_by_email(request: Request, email: str):
    await check_rate_limit(request, 60, 60)
    user = await get_user_by_email(email)
    if not user:
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    return user


@app.get("/api/users/by-id/{identifier}")
async def user_by_id(request: Request, identifier: str):
    await check_rate_limit(request, 60, 60)
    user = await get_user_by_id(identifier)
    if not user:
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    return user


@app.patch("/api/users/{identifier}")
async def update_user(request: Request, identifier: str, data: dict):
    await check_rate_limit(request, 30, 60)
    if not await save_user_data(identifier, data):
        return JSONResponse({"error": "USER_NOT_FOUND"}, 404)
    user = await get_user_by_id(identifier)
    return {"ok": True, "user": user}


@app.get("/api/records")
async def list_records(request: Request, user_id: str | None = None, display_name: str | None = None, user_key: str | None = None):
    await check_rate_limit(request, 60, 60)
    return await get_items(user_id, display_name, user_key)


@app.post("/api/records")
async def create_record(request: Request, data: dict):
    await check_rate_limit(request, 30, 60)
    try:
        result = await add_item(data or {})
    except ValueError as e:
        return JSONResponse({"error": str(e)}, 400)
    return {"ok": True, **result}


@app.delete("/api/records")
async def clear_records(request: Request, user_id: str | None = None, display_name: str | None = None, user_key: str | None = None):
    await check_rate_limit(request, 30, 60)
    await clear_all_items(user_id, display_name, user_key)
    return {"ok": True}


@app.delete("/api/records/{item_id}")
async def delete_record(request: Request, item_id: str):
    await check_rate_limit(request, 30, 60)
    await delete_item(item_id)
    return {"ok": True}

# ── Auth endpoints ──────────────────────────────────────────────────────────

@app.post("/api/send-verification")
async def send_verification(request: Request, data: dict):
    await check_rate_limit(request, 5, 60)
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JSONResponse({"error": "Valid email required"}, 400)
    dev_code = await send_verification_code(email)
    return JSONResponse({"ok": True, **({"dev_code": dev_code} if dev_code else {})})

@app.post("/api/verify-code")
async def verify_code_endpoint(request: Request, data: dict):
    await check_rate_limit(request, 5, 60)
    email = (data.get("email") or "").strip().lower()
    code  = (data.get("code") or "").strip()
    if not email or not code:
        return JSONResponse({"error": "Email and code required"}, 400)
    ok = await verify_code(email, code)
    return JSONResponse({"ok": True, "email": email} if ok else ({"error": "Invalid or expired code"}, 400))

@app.post("/api/forgot-password")
async def forgot_password(request: Request, data: dict):
    await check_rate_limit(request, 3, 120)
    email = (data.get("email") or "").strip().lower()
    if not email: return JSONResponse({"error": "Email required"}, 400)
    user = await get_user_by_email(email)
    if not user:
        # Return success to prevent user enumeration
        return JSONResponse({"ok": True})
    dev_code = await send_reset_code(email)
    return JSONResponse({"ok": True, **({"dev_code": dev_code} if dev_code else {})})

@app.post("/api/reset-password")
async def reset_password(request: Request, data: dict):
    await check_rate_limit(request, 5, 60)
    email = (data.get("email") or "").strip().lower()
    code  = (data.get("code") or "").strip()
    password = data.get("password", "")
    if not email or not code or len(password) < 8:
        return JSONResponse({"error": "Email, code, and new password (8+ chars) required"}, 400)
    user = await verify_reset_code(email, code)
    if not user:
        return JSONResponse({"error": "Invalid or expired code"}, 400)
    if not await update_password(email, password):
        return JSONResponse({"error": "Failed to update password"}, 500)
    return JSONResponse({"ok": True, "displayName": user.get("displayName", ""), "email": email})

# ── Scan endpoints ──────────────────────────────────────────────────────────

@app.post("/api/scan/ai")
async def scan_item_ai(request: Request, file: UploadFile = File(...), mode: str = Form("dispose"),
                       item_type: str = Form("food"), item_state: str = Form("new"), debug: str = Form("false")):
    await check_rate_limit(request, 15, 60)
    if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        return JSONResponse({"error": "Only JPEG, PNG, WebP allowed"}, 400)
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)"}, 413)
    sid = f"{item_type}_{item_state}"
    try:
        ai = await _analyze_scan_image(contents, sid, mode, force_local=_as_bool(debug))
    except Exception:
        return JSONResponse({"error": "Image analysis failed", "mode": mode, "schema_id": sid}, 500)

    ai = await _normalize_scan_payload(ai, contents, file.filename, mode, sid)

    scores = ai.get("weighted_scores", {"a": 50, "b": 50, "c": 50, "d": 50, "e": 50})
    ov = calc_weighted(scores, sid); g = get_grade(ov)
    ai["overall_score"] = ov; ai["grade"] = g["grade"]; ai["grade_advice"] = g["advice"]; ai["grade_color"] = g["color"]
    m = ai.get("material", "plastic")
    if m in HK_DISPOSAL: ai["disposal_info"] = HK_DISPOSAL[m]
    if sid in CRITERIA_LABELS: ai["criteria_labels"] = CRITERIA_LABELS[sid]
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

@app.post("/api/rewards/redeem")
async def redeem(request: Request, data: dict):
    await check_rate_limit(request, 30, 60)
    reward = next((r for r in REWARDS_CATALOG if r["id"] == data.get("reward_id")), None)
    if not reward: return JSONResponse({"error": "Not found"}, 404)
    code = "RL-" + uuid.uuid4().hex[:6].upper() + "-" + str(reward["cost"])
    return {"ok": True, "coupon": {"code": code, "title": reward["title"], "image": reward["image"], "cost": reward["cost"], "claimed_date": "Just now", "expiry": "Valid 30 days"}}

@app.get("/api/fact")
async def fact(request: Request):
    await check_rate_limit(request, 60, 60)
    facts = ["Recycling a single aluminum can saves enough energy to power a TV for 3 hours.",
             "Hong Kong generates over 15,000 tonnes of municipal solid waste every day.",
             "One tree can absorb up to 22kg of CO2 per year.",
             "Plastic bottles take up to 450 years to decompose.",
             "Food waste accounts for 30% of HK municipal solid waste.",
             "Glass is 100% recyclable endlessly without quality loss."]
    return {"fact": random.choice(facts)}

if __name__ == "__main__":
    import uvicorn; uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
