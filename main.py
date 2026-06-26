"""Re-Life API — FastAPI entry point."""
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
import uuid, os, random, traceback, time
from pathlib import Path
from datetime import datetime

from config import *
from data import *
from models import *
from auth import *

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
    allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])

# ── Security Headers ────────────────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=self, microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── Static files ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=root_dir / "static"), name="static")

def _page(path: str) -> str:
    return (root_dir / "templates" / path).read_text(encoding="utf-8")

# ── Pages ───────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def firebase_config():
    return JSONResponse(get_firebase_config())

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
    ai = None; ai_error = None
    if debug.lower() == "true":
        ai_error = "Debug mode — skipping AI"
    elif DEFAULT_AI_MODEL not in AVAILABLE_MODELS:
        ai_error = f"Model '{DEFAULT_AI_MODEL}' not available"
    else:
        for attempt in range(3):
            try:
                ai = await ai_analyze(contents, sid)
                break
            except Exception as e:
                ai_error = str(e)
                print(f"[AI] Error attempt {attempt+1}: {ai_error[:200]}")
                if attempt < 2:
                    import asyncio; await asyncio.sleep(1)
    if ai is None:
        print(f"[Classifier] AI failed, using CNN…")
        try:
            cat, conf = classify_image(contents)
            ai = classifier_response(cat, conf, mode)
        except Exception as cls_e:
            print(f"[Classifier] CNN fallback error: {str(cls_e)}")
            return JSONResponse({"error": "Image analysis failed", "mode": mode, "schema_id": sid}, 500)

    ext = Path(str(file.filename)).suffix or ".png"
    fn = f"{uuid.uuid4()}{ext}"
    ai["image_url"] = upload_image(contents, fn)
    ai["mode"] = mode; ai["id"] = str(uuid.uuid4()); ai["timestamp"] = datetime.now().isoformat(); ai["schema_id"] = sid
    if mode != "purchase": ai["alternative"] = None
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
    return await get_news_cached(db_get, db_put)

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
