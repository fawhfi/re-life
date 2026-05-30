from fastapi import FastAPI, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uuid, shutil, os, json, base64, random, httpx, re, traceback, io
from pathlib import Path
from datetime import datetime

import numpy as np
import onnxruntime as ort
from PIL import Image

root_dir = Path(__file__).parent

if os.path.exists(root_dir / ".env"):
    load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

app = FastAPI(title="Re-Life API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = root_dir / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=root_dir / "static"), name="static")

# ── Server-side CNN Classifier ───────────────────────────────────────────────
CNN_CATEGORIES = ["glass", "metal", "organic", "paper", "plastic", "ewaste"]
CNN_IMG_SIZE   = 224
CNN_MEAN        = [0.485, 0.456, 0.406]
CNN_STD         = [0.229, 0.224, 0.225]

CLASSIFIER_MATERIAL_MAP = {
    "glass":   {"material": "glass",       "standard_type": "general", "eco_rate": 4, "recycle_rate": 5, "description": "Glass container — infinitely recyclable."},
    "metal":   {"material": "metal",       "standard_type": "general", "eco_rate": 4, "recycle_rate": 5, "description": "Metal can — highly recyclable."},
    "organic": {"material": "compostable", "standard_type": "food",    "eco_rate": 5, "recycle_rate": 4, "description": "Organic / food waste — compostable."},
    "paper":   {"material": "paper",       "standard_type": "general", "eco_rate": 5, "recycle_rate": 5, "description": "Paper / cardboard — biodegradable."},
    "plastic": {"material": "plastic",     "standard_type": "general", "eco_rate": 2, "recycle_rate": 3, "description": "Plastic container — limited recyclability."},
    "ewaste":  {"material": "plastic",     "standard_type": "general", "eco_rate": 2, "recycle_rate": 3, "description": "Electronic waste — contains hazardous materials."},
}

CLASSIFIER_NAME_POOL = {
    "glass":   ["Glass Bottle", "Glass Jar", "Glass Container"],
    "metal":   ["Aluminum Can", "Metal Tin", "Steel Container"],
    "organic": ["Food Waste", "Organic Scrap", "Compostable Item"],
    "paper":   ["Cardboard Box", "Paper Package", "Paper Carton"],
    "plastic": ["Plastic Bottle", "Plastic Container", "Plastic Packaging"],
    "ewaste":  ["Electronic Device", "E-Waste Item", "Electronic Component"],
}

_model_path = root_dir / "models" / "model_INT8.onnx"
_cnn_session: ort.InferenceSession | None = None
if _model_path.exists():
    _cnn_session = ort.InferenceSession(str(_model_path), providers=["CPUExecutionProvider"])
    print(f"[Classifier] Loaded INT8 model from {_model_path}")
else:
    print(f"[Classifier] ⚠ Model not found at {_model_path} — classifier disabled")

def _classify_image(image_bytes: bytes) -> tuple[str, float]:
    """Run CNN inference. Returns (category, confidence)."""
    if _cnn_session is None:
        raise RuntimeError("Classifier model not loaded")
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((CNN_IMG_SIZE, CNN_IMG_SIZE), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0
    # Normalize: (pixel - mean) / std, then NCHW
    arr = (arr - np.array(CNN_MEAN, dtype=np.float32)) / np.array(CNN_STD, dtype=np.float32)
    arr = np.transpose(arr, (2, 0, 1))[np.newaxis, ...].astype(np.float32)  # [1, 3, 224, 224]
    outputs = _cnn_session.run(["logits"], {"image": arr})
    logits = outputs[0][0]
    # Softmax
    ex = np.exp(logits - np.max(logits))
    probs = ex / ex.sum()
    idx = int(np.argmax(probs))
    return CNN_CATEGORIES[idx], float(probs[idx])

def _classifier_response(category: str, confidence: float, mode: str) -> dict:
    """Build the response dict the frontend expects from a CNN prediction."""
    info  = CLASSIFIER_MATERIAL_MAP.get(category, CLASSIFIER_MATERIAL_MAP["plastic"])
    names = CLASSIFIER_NAME_POOL.get(category, CLASSIFIER_NAME_POOL["plastic"])
    name  = random.choice(names)
    eco   = info["eco_rate"]
    rec   = info["recycle_rate"]
    base  = round(((eco + rec) / 2) * 20)
    jitter = lambda: max(0, min(100, base + random.randint(-12, 12)))
    m = info["material"]
    disp = HK_DISPOSAL.get(m, HK_DISPOSAL["plastic"])
    return {
        "name": name, "brand": "", "category": category,
        "standard_type": info["standard_type"],
        "description": f"{info['description']} (Server CNN, {confidence:.0%} confidence)",
        "material": m, "eco_rate": eco, "recycle_rate": rec,
        "weighted_scores": {"a": jitter(), "b": jitter(), "c": jitter(), "d": jitter(), "e": jitter()},
        "disposal_guide": disp.get("method", ""),
        "precaution": "Server-side classification — verify manually for hazardous items.",
        "disposal_info": disp,
        "alternative": {"name": "Eco-Friendly Alternative (CNN)", "eco_rate": 5, "recycle_rate": 5} if mode == "purchase" else None,
    }

# Scoring Engine
SCHEMA_WEIGHTS = {
    "food_new": {"a": 0.30, "b": 0.25, "c": 0.20, "d": 0.15, "e": 0.10},
    "food_expire": {"a": 0.20, "b": 0.20, "c": 0.25, "d": 0.20, "e": 0.15},
    "item_new": {"a": 0.25, "b": 0.35, "c": 0.10, "d": 0.20, "e": 0.10},
    "item_expire": {"a": 0.25, "b": 0.30, "c": 0.10, "d": 0.25, "e": 0.10},
}
CRITERIA_LABELS = {
    "food_new":    {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recyclability", "e": "Food Preservation"},
    "food_expire": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Safety & Waste Prevention"},
    "item_new":    {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Social & Innovation"},
    "item_expire": {"a": "Environmental Impact", "b": "Sustainability", "c": "Biodegradability", "d": "Recycling", "e": "Reuse Potential"},
}
HK_DISPOSAL = {
    "plastic": {"type": "Plastic (PET/HDPE)", "method": "Rinse clean, flatten", "location": "Tri-colour recycling bins, GREEN@COMMUNITY"},
    "pp_plastic": {"type": "Other Plastic / PP", "method": "Rinse clean, disassemble parts", "location": "GREEN@COMMUNITY"},
    "paper": {"type": "Paper / Cardboard", "method": "Keep dry, no grease, flatten", "location": "Blue paper recycling bins"},
    "metal": {"type": "Metal Cans", "method": "Rinse clean, flatten", "location": "Metal recycling bins"},
    "glass": {"type": "Glass Bottles", "method": "Rinse clean, remove caps", "location": "Government glass recycling points"},
    "compostable": {"type": "Compostable", "method": "Do NOT place in regular recycling", "location": "Industrial/home composting programs"},
    "wood": {"type": "Wood / Bulky Waste", "method": "Remove metal fittings, compress", "location": "LCSD collection points or private recyclers"},
}

# Rewards Catalog
REWARDS_CATALOG = [
    {"id": "tree-plant", "title": "Plant a Native Tree in HK Country Park", "provider": "Tree Planting HK", "cost": 500, "image": "🌳", "category": "Environment", "description": "Sponsor planting a native sapling in Tai Lam or Sai Kung country park."},
    {"id": "fairprice-voucher", "title": "PARKnSHOP HK$30 Cash Voucher", "provider": "PARKnSHOP", "cost": 350, "image": "🎟️", "category": "Voucher", "description": "Valid at all PARKnSHOP, TASTE, and Fusion stores across Hong Kong."},
    {"id": "mtr-ride", "title": "MTR Single Journey Ticket", "provider": "MTR Corporation", "cost": 200, "image": "🚇", "category": "Transport", "description": "One free adult single journey on any MTR urban line."},
    {"id": "starbucks-treat", "title": "Starbucks HK$25 eGift", "provider": "Starbucks HK", "cost": 280, "image": "☕", "category": "Voucher", "description": "Redeemable for any handcrafted beverage at Starbucks Hong Kong."},
    {"id": "ocean-cleanup", "title": "Sponsor Ocean Cleanup (1kg)", "provider": "Ocean Recovery Alliance", "cost": 150, "image": "🌊", "category": "Environment", "description": "Fund the removal of 1kg of marine plastic from HK coastal waters."},
    {"id": "reusable-kit", "title": "Reusable Eco Starter Kit", "provider": "Green Store HK", "cost": 400, "image": "🎒", "category": "Product", "description": "Bamboo cutlery set, beeswax wrap, and organic cotton tote bag."},
]

def calc_weighted(scores, sid):
    w = SCHEMA_WEIGHTS.get(sid, SCHEMA_WEIGHTS["food_new"])
    return round(sum(scores.get(k, 50) * w[k] for k in w))

def get_grade(score):
    if score >= 85: return {"grade": "Excellent (A)", "advice": "Highly Recommended", "color": "#065f46"}
    if score >= 70: return {"grade": "Good (B)", "advice": "Acceptable", "color": "#047857"}
    if score >= 55: return {"grade": "Fair (C)", "advice": "Consider Alternatives", "color": "#ca8a04"}
    if score >= 40: return {"grade": "Poor (D)", "advice": "Avoid if Possible", "color": "#b45309"}
    return {"grade": "Very Poor (E)", "advice": "Strongly Discouraged", "color": "#dc2626"}

# Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    return (root_dir / "templates/index.html").read_text(encoding="utf-8")

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return (root_dir / "templates/login.html").read_text(encoding="utf-8")

@app.post("/api/scan")
async def scan_item(file: UploadFile = File(...), mode: str = Form("dispose")):
    ext = Path(str(file.filename)).suffix or ".png"
    filename = f"{uuid.uuid4()}{ext}"
    with open(UPLOAD_DIR / filename, "wb") as f: shutil.copyfileobj(file.file, f)
    result = _mock(mode)
    result["mode"] = mode
    result["image_url"] = f"/uploads/{filename}"
    result["id"] = str(uuid.uuid4())
    result["timestamp"] = datetime.now().isoformat()
    return JSONResponse(result)

@app.post("/api/scan/ai")
async def scan_item_ai(file: UploadFile = File(...), mode: str = Form("dispose"), item_type: str = Form("food"), item_state: str = Form("new"), debug: str = Form("false")):
    contents = await file.read()
    sid = f"{item_type}_{item_state}"
    ai = None
    ai_error = None
    if debug.lower() == "true":
        # Debug mode: skip AI, go straight to CNN classifier
        ai_error = "Debug mode — skipping NVIDIA API"
        print("[Debug] Skipping AI, using classifier directly")
    elif not NVIDIA_API_KEY:
        ai_error = "No API key configured. Set NVIDIA_API in .env or enter it in Settings."
    else:
        for attempt in range(3):
            try:
                ai = await _ai_analyze(contents, sid)
                break
            except Exception as e:
                ai_error = traceback.format_exc()
                print(f"AI ERROR (attempt {attempt + 1}/3):\n{ai_error}")
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(1)
    if ai is None:
        # Fall back to server-side CNN classifier
        print(f"[Classifier] AI failed ({ai_error}), running server-side CNN…")
        try:
            cat, conf = _classify_image(contents)
            print(f"[Classifier] Predicted: {cat} ({conf:.2%})")
            ai = _classifier_response(cat, conf, mode)
        except Exception as cls_e:
            print(f"[Classifier] CNN failed too: {cls_e}")
            return JSONResponse({"classifier_fallback": True, "ai_error": str(cls_e), "mode": mode, "schema_id": sid})
    ext = Path(str(file.filename)).suffix or ".png"
    fn = f"{uuid.uuid4()}{ext}"
    with open(UPLOAD_DIR / fn, "wb") as f: f.write(contents)
    ai["image_url"] = f"/uploads/{fn}"
    ai["mode"] = mode; ai["id"] = str(uuid.uuid4()); ai["timestamp"] = datetime.now().isoformat(); ai["schema_id"] = sid
    # Alternative only relevant in purchase mode
    if mode != "purchase":
        ai["alternative"] = None
    scores = ai.get("weighted_scores", {"a": 50, "b": 50, "c": 50, "d": 50, "e": 50})
    ov = calc_weighted(scores, sid); g = get_grade(ov)
    ai["overall_score"] = ov; ai["grade"] = g["grade"]; ai["grade_advice"] = g["advice"]; ai["grade_color"] = g["color"]
    m = ai.get("material", "plastic")
    if m in HK_DISPOSAL: ai["disposal_info"] = HK_DISPOSAL[m]
    if sid in CRITERIA_LABELS: ai["criteria_labels"] = CRITERIA_LABELS[sid]
    return JSONResponse(ai)

def _extract_json(text):
    """Try to extract a JSON object from text that may contain markdown fences or surrounding prose."""
    if not text or not text.strip():
        return None
    text = text.strip()
    # 1. Strip markdown code fences
    if text.startswith("```"):
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.lower().startswith("json"):
                p = p[4:].strip()
            try:
                return json.loads(p)
            except json.JSONDecodeError:
                continue
        return None
    # 2. Direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 3. Find first JSON object by tracking brace depth
    start = text.find("{")
    if start != -1:
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None

async def _ai_analyze(image_bytes, sid):
    prompt = f"""Look at this image carefully. Identify the product shown, its packaging material, and rate its environmental impact for Hong Kong.

Respond with ONLY a JSON object (no markdown, no explanation, no text outside):

{{
  "name": "Product name you see",
  "brand": "Brand name or empty",
  "category": "Category like beverage/snack/dairy/electronics/household",
  "standardType": "food" or "general",
  "description": "One sentence about product and packaging",
  "material": "plastic" or "pp_plastic" or "paper" or "metal" or "glass" or "compostable" or "wood",
  "disposalGuide": "HK disposal instruction",
  "precaution": "Safety note",
  "ecoRate": 1-5,
  "recycleRate": 1-5,
  "weightedScores": {{"a":0-100,"b":0-100,"c":0-100,"d":0-100,"e":0-100}},
  "alternative": {{
    "name": "A more eco-friendly alternative product name",
    "ecoRate": 5,
    "recycleRate": 5
  }}
}}

Rate honestly based on what you see. Give varied, realistic scores — not all zeros or middle values.
For "alternative", suggest a more sustainable replacement product that achieves the same purpose."""
    # Compress image to keep base64 under ~500KB (NVIDIA has request size limits)
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        compressed = buf.getvalue()
        print(f"[AI] Image: {len(image_bytes)} -> {len(compressed)} bytes (compressed)")
    except Exception:
        compressed = image_bytes
        print(f"[AI] Image: {len(image_bytes)} bytes (no PIL, sent raw)")

    b64 = base64.b64encode(compressed).decode()
    mime = "image/jpeg" if compressed != image_bytes else "image/png"
    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": "You are an environmental packaging evaluator. You MUST respond with ONLY a single JSON object. No markdown, no explanation, no reasoning in the output — just the JSON object."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]},
        ],
        "max_tokens": 65536,
        "temperature": 0.6,
        "top_p": 0.95,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(NVIDIA_BASE_URL, json=payload, headers=headers)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500] if e.response else ""
            raise Exception(f"API error {e.response.status_code}: {body}") from e
        d = r.json()

    print(f"[AI] Raw response keys: {list(d.keys())}")
    choice = (d.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content", "")
    reasoning = msg.get("reasoning_content", "")
    finish = choice.get("finish_reason", "")

    if finish and finish != "stop":
        raise Exception(f"AI call stopped early (finish_reason={finish})")

    print(f"[AI] content[:200]: {(content or '')[:200]}")
    print(f"[AI] reasoning_content[:200]: {(reasoning or '')[:200]}")

    j = _extract_json(content) or _extract_json(reasoning)
    if not j:
        preview = (content or reasoning or "")[:300]
        raise Exception(f"AI returned non-JSON response: {preview}")

    print(f"[AI] Extracted JSON: {json.dumps(j, ensure_ascii=False)}")

    alt = j.get("alternative")
    alternative = None
    if alt and isinstance(alt, dict) and alt.get("name"):
        alternative = {
            "name": alt.get("name", "Eco-Friendly Alternative"),
            "eco_rate": alt.get("ecoRate", 5),
            "recycle_rate": alt.get("recycleRate", 5),
        }

    return {"name": j.get("name", "Scanned"), "brand": j.get("brand", ""), "category": j.get("category", ""), "description": j.get("description", ""), "eco_rate": j.get("ecoRate", 3), "recycle_rate": j.get("recycleRate", 4), "standard_type": j.get("standardType", "food"), "material": j.get("material", "plastic"), "disposal_guide": j.get("disposalGuide", ""), "precaution": j.get("precaution", ""), "weighted_scores": j.get("weightedScores", {"a": 50, "b": 50, "c": 50, "d": 50, "e": 50}), "alternative": alternative}

def _mock(mode):
    r = lambda: random.randint(1, 5)
    s = lambda: {"a": random.randint(30, 100), "b": random.randint(30, 100), "c": random.randint(30, 100), "d": random.randint(30, 100), "e": random.randint(30, 100)}
    if mode == "purchase":
        return {"name": "Scanned Product", "eco_rate": r(), "recycle_rate": r(), "alternative": {"name": "Eco-Friendly Alternative", "eco_rate": 5, "recycle_rate": 4}, "description": "Mock analysis.", "weighted_scores": s(), "material": random.choice(["plastic", "paper", "glass"]), "disposal_guide": "Rinse and recycle.", "precaution": "Remove caps and labels."}
    return {"name": "Scanned Item", "eco_rate": r(), "recycle_rate": r(), "alternative": None, "description": "Mock analysis.", "weighted_scores": s(), "material": random.choice(["plastic", "pp_plastic", "metal", "wood"]), "disposal_guide": "Drop at GREEN@COMMUNITY.", "precaution": "Separate materials."}

@app.get("/api/tips")
async def get_tips():
    return [{"title": "Energy saving tips to save money", "source": "From HSBC SG", "snippet": "More and more people are making a conscious effort to use less energy."}, {"title": "How to recycle electronics properly", "source": "From NEA", "snippet": "E-waste contains valuable materials but also hazardous substances."}, {"title": "Zero waste grocery shopping", "source": "From WWF", "snippet": "Simple swaps can dramatically cut your household plastic waste."}]

@app.get("/api/schemas")
async def get_schemas():
    return {"item_types": [{"value": "food", "label": "Food Items"}, {"value": "general", "label": "General Items"}], "item_states": [{"value": "new", "label": "New Purchase"}, {"value": "expire", "label": "About to Expire"}], "weights": SCHEMA_WEIGHTS, "criteria_labels": CRITERIA_LABELS}

@app.get("/api/rewards")
async def get_rewards(): return REWARDS_CATALOG

@app.post("/api/rewards/redeem")
async def redeem_reward(data: dict):
    reward = next((r for r in REWARDS_CATALOG if r["id"] == data.get("reward_id")), None)
    if not reward: return JSONResponse({"error": "Not found"}, 404)
    code = "RL-" + uuid.uuid4().hex[:6].upper() + "-" + str(reward["cost"])
    return {"ok": True, "coupon": {"code": code, "title": reward["title"], "image": reward["image"], "cost": reward["cost"], "claimed_date": "Just now", "expiry": "Valid 30 days"}}

@app.get("/api/fact")
async def get_fact():
    facts = ["Recycling a single aluminum can saves enough energy to power a TV for 3 hours.", "Hong Kong generates over 15,000 tonnes of municipal solid waste every day.", "One tree can absorb up to 22kg of CO2 per year.", "Plastic bottles take up to 450 years to decompose.", "Food waste accounts for 30% of HK municipal solid waste.", "Glass is 100% recyclable endlessly without quality loss."]
    return {"fact": random.choice(facts)}

if __name__ == "__main__":
    import uvicorn; uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
