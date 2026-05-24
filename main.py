from fastapi import FastAPI, File, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uuid, shutil, os, json, base64, random, httpx, re
from pathlib import Path
from datetime import datetime

root_dir = Path(__file__).parent

if os.path.exists(root_dir / ".env"):
    load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API")
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "moonshotai/kimi-k2.6"

app = FastAPI(title="Re-Life API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_DIR = root_dir / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=root_dir / "static"), name="static")

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

# Seed Records
records: list[dict] = [
    {"id": "1", "name": "Fresh Milk", "mode": "purchase", "eco_rate": 3, "recycle_rate": 4, "image": "🥛", "alternative": {"name": "Almond Milk", "eco_rate": 5, "recycle_rate": 4}, "weighted_scores": {"a": 65, "b": 60, "c": 40, "d": 70, "e": 75}, "schema_id": "food_new", "material": "plastic", "disposal_guide": "Rinse and flatten before recycling.", "precaution": "Ensure carton is empty and rinsed.", "timestamp": "2025-05-16T09:00:00"},
    {"id": "2", "name": "Old Furnitures", "mode": "dispose", "eco_rate": 2, "recycle_rate": 3, "image": "🪑", "alternative": None, "weighted_scores": {"a": 50, "b": 65, "c": 40, "d": 70, "e": 50}, "schema_id": "item_expire", "material": "wood", "disposal_guide": "Contact private wood recyclers or LCSD.", "precaution": "Do not dispose in standard refuse chutes.", "timestamp": "2025-05-15T14:00:00"},
    {"id": "3", "name": "Rotten Banana", "mode": "dispose", "eco_rate": 5, "recycle_rate": 5, "image": "🍌", "alternative": None, "weighted_scores": {"a": 95, "b": 95, "c": 100, "d": 100, "e": 90}, "schema_id": "food_expire", "material": "compostable", "disposal_guide": "Place in organic food waste bin.", "precaution": "Do not wrap in airtight plastic.", "timestamp": "2025-05-15T10:00:00"},
    {"id": "4", "name": "Kitchen Waste", "mode": "dispose", "eco_rate": 4, "recycle_rate": 5, "image": "🗑️", "alternative": None, "weighted_scores": {"a": 85, "b": 80, "c": 95, "d": 85, "e": 80}, "schema_id": "food_expire", "material": "compostable", "disposal_guide": "Use GREEN@COMMUNITY food waste smart bins.", "precaution": "Drain excess liquid before depositing.", "timestamp": "2025-05-14T18:00:00"},
    {"id": "5", "name": "Abandoned TV", "mode": "dispose", "eco_rate": 1, "recycle_rate": 5, "image": "📺", "alternative": None, "weighted_scores": {"a": 30, "b": 40, "c": 5, "d": 85, "e": 50}, "schema_id": "item_expire", "material": "metal", "disposal_guide": "Call WEEE·PARK hotline for free pickup.", "precaution": "Contains lead and mercury. Do NOT dismantle.", "timestamp": "2025-05-14T12:00:00"},
    {"id": "6", "name": "Old Charger", "mode": "dispose", "eco_rate": 2, "recycle_rate": 5, "image": "🔌", "alternative": None, "weighted_scores": {"a": 40, "b": 45, "c": 5, "d": 90, "e": 60}, "schema_id": "item_expire", "material": "pp_plastic", "disposal_guide": "Drop at GREEN@COMMUNITY points.", "precaution": "Remove detachable battery first.", "timestamp": "2025-05-13T09:00:00"},
]

users: dict[str, dict] = {
    "EcoWarrior": {"avatar": "🌿", "records": [], "spent_points": 0, "claimed_coupons": []},
    "ZeroWasteHK": {"avatar": "♻️", "records": [], "spent_points": 100, "claimed_coupons": []},
}

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
async def scan_item_ai(file: UploadFile = File(...), mode: str = Form("dispose"), item_type: str = Form("food"), item_state: str = Form("new")):
    contents = await file.read()
    sid = f"{item_type}_{item_state}"
    ai = None
    ai_error = None
    if not NVIDIA_API_KEY:
        ai_error = "No API key configured. Set NVIDIA_API in .env or enter it in Settings."
    else:
        try: ai = await _ai_analyze(contents, sid)
        except Exception as e:
            ai_error = str(e)
            print(f"AI err: {e}")
    if ai is None:
        ai = _mock(mode)
        ai["description"] = f"⚠️ {ai_error or 'AI returned no result.'}"
        if ai_error:
            ai["ai_error"] = ai_error
    ext = Path(str(file.filename)).suffix or ".png"
    fn = f"{uuid.uuid4()}{ext}"
    with open(UPLOAD_DIR / fn, "wb") as f: f.write(contents)
    ai["image_url"] = f"/uploads/{fn}"
    ai["mode"] = mode; ai["id"] = str(uuid.uuid4()); ai["timestamp"] = datetime.now().isoformat(); ai["schema_id"] = sid
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
    prompt = f"""Evaluate packaging per 2026 HK Environmental Standard. Schema: "{sid}". If irrelevant image flag shouldRate=false. Return ONLY JSON: {{"shouldRate":true,"name":"...","brand":"...","category":"...","standardType":"food|general","description":"...","material":"plastic|pp_plastic|paper|metal|glass|compostable|wood","disposalGuide":"...","precaution":"...","ecoRate":1-5,"recycleRate":1-5,"weightedScores":{{"a":0-100,"b":0-100,"c":0-100,"d":0-100,"e":0-100}}}}"""
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "model": NVIDIA_MODEL,
        "messages": [
            {"role": "system", "content": "You are an environmental packaging evaluator. You MUST respond with ONLY a single JSON object. No markdown, no explanation, no reasoning in the output — just the JSON object."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]},
        ],
        "max_tokens": 4096,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(NVIDIA_URL, json=payload, headers=headers)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500] if e.response else ""
            raise Exception(f"API error {e.response.status_code}: {body}") from e
        d = r.json()

    choice = (d.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content", "")
    reasoning = msg.get("reasoning_content", "")
    finish = choice.get("finish_reason", "")

    if finish and finish != "stop":
        raise Exception(f"AI call stopped early (finish_reason={finish})")

    j = _extract_json(content) or _extract_json(reasoning)
    if not j:
        preview = (content or reasoning or "")[:300]
        raise Exception(f"AI returned non-JSON response: {preview}")

    if not j.get("shouldRate", True):
        raise Exception("AI determined image is not a recognizable product/package — try a clearer photo")

    return {"name": j.get("name", "Scanned"), "brand": j.get("brand", ""), "category": j.get("category", ""), "description": j.get("description", ""), "eco_rate": j.get("ecoRate", 3), "recycle_rate": j.get("recycleRate", 4), "standard_type": j.get("standardType", "food"), "material": j.get("material", "plastic"), "disposal_guide": j.get("disposalGuide", ""), "precaution": j.get("precaution", ""), "weighted_scores": j.get("weightedScores", {"a": 50, "b": 50, "c": 50, "d": 50, "e": 50})}

def _mock(mode):
    r = lambda: random.randint(1, 5)
    s = lambda: {"a": random.randint(30, 100), "b": random.randint(30, 100), "c": random.randint(30, 100), "d": random.randint(30, 100), "e": random.randint(30, 100)}
    if mode == "purchase":
        return {"name": "Scanned Product", "eco_rate": r(), "recycle_rate": r(), "alternative": {"name": "Eco-Friendly Alternative", "eco_rate": 5, "recycle_rate": 4}, "description": "Mock analysis.", "weighted_scores": s(), "material": random.choice(["plastic", "paper", "glass"]), "disposal_guide": "Rinse and recycle.", "precaution": "Remove caps and labels."}
    return {"name": "Scanned Item", "eco_rate": r(), "recycle_rate": r(), "alternative": None, "description": "Mock analysis.", "weighted_scores": s(), "material": random.choice(["plastic", "pp_plastic", "metal", "wood"]), "disposal_guide": "Drop at GREEN@COMMUNITY.", "precaution": "Separate materials."}

@app.get("/api/records")
async def get_records(): return records

@app.post("/api/records")
async def add_record(record: dict):
    record["id"] = str(uuid.uuid4()); record["timestamp"] = datetime.now().isoformat(); records.insert(0, record); return record

@app.delete("/api/records/{record_id}")
async def delete_record(record_id: str):
    global records; records = [r for r in records if r["id"] != record_id]; return {"ok": True}

@app.delete("/api/records")
async def clear_records():
    global records; records = []; return {"ok": True}

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

@app.get("/api/users")
async def get_users():
    return [{"name": k, "avatar": v["avatar"], "records_count": len(v["records"]), "spent_points": v["spent_points"]} for k, v in users.items()]

@app.post("/api/users/{username}/data")
async def save_user_data(username: str, data: dict):
    if username not in users: users[username] = {"avatar": "👤", "records": [], "spent_points": 0, "claimed_coupons": []}
    for k in ["records", "spent_points", "claimed_coupons"]:
        if k in data: users[username][k] = data[k]
    return {"ok": True}

@app.get("/api/users/{username}/data")
async def load_user_data(username: str):
    if username not in users: return {"records": [], "spent_points": 0, "claimed_coupons": []}
    return users[username]

@app.get("/api/stats")
async def get_stats():
    n = len(records) or 1
    return {"total_items": len(records), "total_points": sum(r.get("overall_score", 50) for r in records), "eco_avg": round(sum(r.get("eco_rate", 3) for r in records) / n, 1), "recycle_avg": round(sum(r.get("recycle_rate", 3) for r in records) / n, 1)}

@app.get("/api/fact")
async def get_fact():
    facts = ["Recycling a single aluminum can saves enough energy to power a TV for 3 hours.", "Hong Kong generates over 15,000 tonnes of municipal solid waste every day.", "One tree can absorb up to 22kg of CO2 per year.", "Plastic bottles take up to 450 years to decompose.", "Food waste accounts for 30% of HK municipal solid waste.", "Glass is 100% recyclable endlessly without quality loss."]
    return {"fact": random.choice(facts)}

if __name__ == "__main__":
    import uvicorn; uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
