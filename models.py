"""Re-Life AI models — local transformer classifier + multi-model AI providers."""
import io, base64, random, httpx, json
from PIL import Image
from pathlib import Path
from config import (
    NVIDIA_API_KEY, NVIDIA_MODEL, OPENAI_API_KEY, OPENAI_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL, DEEPSEEK_API_KEY, CLAUDE_API_KEY, CLAUDE_MODEL,
    DEFAULT_AI_MODEL, AVAILABLE_MODELS, SUPABASE_STORAGE_BUCKET, SUPABASE_URL,
)
from data import HK_DISPOSAL
from nlp.infer import predict_image
from storage import supabase_enabled, supabase_storage_signed_url, supabase_storage_upload

# ── Legacy classifier metadata ──────────────────────────────────────────────

CNN_CATEGORIES = ["glass", "metal", "organic", "paper", "plastic", "ewaste"]
CNN_LABELS = {
    "glass": "Glass",
    "metal": "Metal",
    "organic": "Organic",
    "paper": "Paper",
    "plastic": "Plastic",
    "ewaste": "E-waste",
}

CNN_TEXT_TEMPLATES = {
    "glass": "This looks like glass waste. Keep it clean and sort it with glass items.",
    "metal": "This looks like metal waste. Empty it and sort it with metal items.",
    "organic": "This looks like organic waste. Treat it as food waste or compostable waste.",
    "paper": "This looks like paper waste. Keep it dry and sort it with paper recycling.",
    "plastic": "This looks like plastic waste. Rinse it if possible and sort it with plastic items.",
    "ewaste": "This looks like e-waste. Do not mix it with regular recyclables.",
}

CLASSIFIER_MATERIAL_MAP = {
    "glass":   {"material": "glass",       "standard_type": "general", "eco_rate": 4, "recycle_rate": 5, "description": "Glass container — infinitely recyclable."},
    "metal":   {"material": "metal",       "standard_type": "general", "eco_rate": 4, "recycle_rate": 5, "description": "Metal can — highly recyclable."},
    "organic": {"material": "compostable", "standard_type": "food",    "eco_rate": 5, "recycle_rate": 4, "description": "Organic / food waste — compostable."},
    "paper":   {"material": "paper",       "standard_type": "general", "eco_rate": 5, "recycle_rate": 5, "description": "Paper / cardboard — biodegradable."},
    "plastic": {"material": "plastic",     "standard_type": "general", "eco_rate": 2, "recycle_rate": 3, "description": "Plastic container — limited recyclability."},
    "ewaste":  {"material": "plastic",     "standard_type": "general", "eco_rate": 2, "recycle_rate": 3, "description": "Electronic waste — contains hazardous materials."},
}


def _build_waste_response(
    category: str,
    *,
    label: str,
    text: str,
    classifier_source: str,
    model_source: str,
    runtime_source: str,
    artifact: str,
    confidence: float,
    tokens: list[str] | None = None,
) -> dict:
    info = CLASSIFIER_MATERIAL_MAP.get(category, CLASSIFIER_MATERIAL_MAP["plastic"])
    eco = info["eco_rate"]
    rec = info["recycle_rate"]
    base = round(((eco + rec) / 2) * 20)
    jitter = lambda: max(0, min(100, base + random.randint(-12, 12)))
    material = info["material"]
    disp = HK_DISPOSAL.get(material, HK_DISPOSAL["plastic"])
    return {
        "name": label,
        "brand": "",
        "category": category,
        "waste_type": category,
        "waste_label": label,
        "classifier_source": classifier_source,
        "model_source": model_source,
        "runtime_source": runtime_source,
        "artifact": artifact,
        "text": text,
        "tokens": tokens or [],
        "confidence": confidence,
        "standard_type": info["standard_type"],
        "description": "",
        "material": material,
        "eco_rate": eco,
        "recycle_rate": rec,
        "weighted_scores": {"a": jitter(), "b": jitter(), "c": jitter(), "d": jitter(), "e": jitter()},
        "disposal_guide": disp.get("method", ""),
        "precaution": "Server-side classification — verify manually for hazardous items.",
        "disposal_info": disp,
        "alternative": None,
    }

def classifier_response(category: str, confidence: float, mode: str) -> dict:
    label = CNN_LABELS.get(category, category.replace("_", " ").title())
    return _build_waste_response(
        category,
        label=label,
        text=f"{label} waste.",
        classifier_source="cnn",
        model_source="transformer",
        runtime_source="onnxruntime",
        artifact="model_fp16.onnx",
        confidence=confidence,
    )

def local_scan_response(image_bytes: bytes, mode: str) -> dict:
    prediction = predict_image(image_bytes)
    category = prediction["waste_type"]
    label = prediction.get("waste_label") or CNN_LABELS.get(category, category.replace("_", " ").title())
    return _build_waste_response(
        category,
        label=label,
        text=prediction.get("text", ""),
        classifier_source=prediction.get("classifier_source", "nlp"),
        model_source=prediction.get("model_source", "transformer"),
        runtime_source=prediction.get("runtime_source", "onnxruntime"),
        artifact=prediction.get("artifact", "model_fp16.onnx"),
        confidence=prediction.get("confidence", 0.0),
        tokens=prediction.get("tokens", []),
    )

def _image_mime_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    return mime_map.get(ext, "image/jpeg")


def _data_url(contents: bytes, filename: str) -> str:
    mime = _image_mime_type(filename)
    b64 = base64.b64encode(contents).decode()
    return f"data:{mime};base64,{b64}"


async def upload_image(contents: bytes, filename: str) -> str:
    if supabase_enabled() and SUPABASE_STORAGE_BUCKET and SUPABASE_URL:
        try:
            await supabase_storage_upload(
                SUPABASE_STORAGE_BUCKET,
                filename,
                contents,
                _image_mime_type(filename),
            )
            bucket = SUPABASE_STORAGE_BUCKET.strip("/")
            return supabase_storage_signed_url(bucket, filename)
        except Exception:
            pass
    return _data_url(contents, filename)

# ── AI Providers ────────────────────────────────────────────────────────────
_AI_PROMPT = """Look at this image carefully. Identify the product shown, its packaging material, and rate its environmental impact for Hong Kong.

Respond with ONLY a JSON object (no markdown, no explanation):

{
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
  "weightedScores": {"a":0-100,"b":0-100,"c":0-100,"d":0-100,"e":0-100},
  "alternative": {"name": "A more eco-friendly alternative", "ecoRate": 5, "recycleRate": 5}
}"""

def _compress_image(image_bytes: bytes) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, "image/png"

def _extract_json(text):
    if not text or not text.strip():
        return None
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.lower().startswith("json"):
                p = p[4:].strip()
            try: return json.loads(p)
            except: continue
        return None
    try: return json.loads(text)
    except: pass
    start = text.find("{")
    if start != -1:
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{": depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0: end = i + 1; break
        if end > start:
            try: return json.loads(text[start:end])
            except: pass
    return None

async def _call_openai_compat(api_key: str, base_url: str, model_id: str, prompt: str, b64: str, mime: str) -> str:
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "You are an environmental packaging evaluator. Respond with ONLY a single JSON object."},
                    {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]},
                ],
                "max_tokens": 8192, "temperature": 0.6, "stream": False,
            },
        )
        r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

async def _call_gemini(prompt: str, b64: str, mime: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": "You are an environmental packaging evaluator. Respond with ONLY a single JSON object.\n\n" + prompt}, {"inline_data": {"mime_type": mime, "data": b64}}]}]},
        )
        r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

async def _call_claude(prompt: str, b64: str, mime: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={
                "model": CLAUDE_MODEL, "max_tokens": 4096,
                "system": "You are an environmental packaging evaluator. Respond with ONLY a single JSON object.",
                "messages": [{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}, {"type": "text", "text": prompt}]}],
            },
        )
        r.raise_for_status()
    return r.json()["content"][0]["text"]

async def _call_nvidia_stream(api_key: str, model_id: str, prompt: str, b64: str, mime: str) -> str:
    """Call NVIDIA API with streaming to avoid truncated responses."""
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are an environmental packaging evaluator. Respond with ONLY a single JSON object."},
            {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]},
        ],
        "max_tokens": 8192, "temperature": 0.6, "top_p": 0.95,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": True},
    }
    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream(
            "POST", "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as response:
            response.raise_for_status()
            full_text = ""
            async for line in response.aiter_lines():
                if line and line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                    except json.JSONDecodeError:
                        continue
            return full_text

async def ai_analyze(image_bytes: bytes, sid: str) -> dict:
    """Route to the correct AI provider based on DEFAULT_AI_MODEL."""
    compressed, mime = _compress_image(image_bytes)
    b64 = base64.b64encode(compressed).decode()
    model = DEFAULT_AI_MODEL

    if model == "nvidia" and NVIDIA_API_KEY:
        content = await _call_nvidia_stream(NVIDIA_API_KEY, NVIDIA_MODEL, _AI_PROMPT, b64, mime)
    elif model == "openai" and OPENAI_API_KEY:
        content = await _call_openai_compat(OPENAI_API_KEY, "https://api.openai.com/v1", OPENAI_MODEL, _AI_PROMPT, b64, mime)
    elif model == "deepseek" and DEEPSEEK_API_KEY:
        content = await _call_openai_compat(DEEPSEEK_API_KEY, "https://api.deepseek.com/v1", "deepseek-chat", _AI_PROMPT, b64, mime)
    elif model == "gemini" and GEMINI_API_KEY:
        content = await _call_gemini(_AI_PROMPT, b64, mime)
    elif model == "claude" and CLAUDE_API_KEY:
        content = await _call_claude(_AI_PROMPT, b64, mime)
    else:
        raise Exception(f"Model '{model}' not available")

    j = _extract_json(content)
    if not j:
        # Try to fix truncated JSON by appending closing braces
        if content and content.strip().startswith('{'):
            fixed = content.strip()
            open_b = fixed.count('{') - fixed.count('}')
            fixed += '}' * open_b
            j = _extract_json(fixed)
    if not j:
        raise Exception(f"AI returned non-JSON: {(content or '')[:200]}")

    alt = j.get("alternative")
    alternative = None
    if alt and isinstance(alt, dict) and alt.get("name"):
        alternative = {"name": alt.get("name", "Eco-Friendly Alternative"), "eco_rate": alt.get("ecoRate", 5), "recycle_rate": alt.get("recycleRate", 5)}

    return {
        "name": j.get("name", "Scanned"), "brand": j.get("brand", ""), "category": j.get("category", ""),
        "description": j.get("description", ""), "eco_rate": j.get("ecoRate", 3), "recycle_rate": j.get("recycleRate", 4),
        "standard_type": j.get("standardType", "food"), "material": j.get("material", "plastic"),
        "disposal_guide": j.get("disposalGuide", ""), "precaution": j.get("precaution", ""),
        "weighted_scores": j.get("weightedScores", {"a": 50, "b": 50, "c": 50, "d": 50, "e": 50}),
        "alternative": alternative,
    }
