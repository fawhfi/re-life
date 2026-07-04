"""Scan orchestration for remote AI and local fallback analysis."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import uuid
from collections.abc import Awaitable, Callable

from config import DEFAULT_AI_MODEL
from models import CNN_LABELS, ai_analyze, local_scan_response, upload_image
from scoring import CRITERIA_LABELS, HK_DISPOSAL, calc_weighted, get_grade


RemoteAnalyzer = Callable[[bytes, str], Awaitable[dict]]
LocalAnalyzer = Callable[[bytes, str], dict]


def parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def infer_waste_type(payload: dict) -> str:
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


async def analyze_scan_image(
    contents: bytes,
    schema_id: str,
    mode: str,
    *,
    force_local: bool = False,
    remote_analyzer: RemoteAnalyzer = ai_analyze,
    local_analyzer: LocalAnalyzer = local_scan_response,
) -> dict:
    if force_local:
        print("[Classifier] Debug mode enabled; using local transformer")
        return local_analyzer(contents, mode)

    try:
        return await remote_analyzer(contents, schema_id)
    except Exception as remote_error:
        print(f"[Classifier] Remote AI error: {str(remote_error)[:200]}")
        try:
            result = local_analyzer(contents, mode)
            result["ai_error"] = "AI failed to call, using fallback."
            result["fallback_used"] = True
            return result
        except Exception as local_error:
            print(f"[Classifier] Local transformer error: {str(local_error)[:200]}")
            raise


async def normalize_scan_payload(ai: dict, contents: bytes, filename: str, mode: str, schema_id: str) -> dict:
    result = dict(ai or {})
    ext = Path(str(filename)).suffix or ".png"
    image_name = f"{uuid.uuid4()}{ext}"
    result["image_url"] = await upload_image(contents, image_name)
    result["mode"] = mode
    result["id"] = result.get("id") or str(uuid.uuid4())
    result["timestamp"] = datetime.now().isoformat()
    result["schema_id"] = schema_id
    if mode != "purchase":
        result["alternative"] = None

    waste_type = result.get("waste_type") or infer_waste_type(result)
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


def enrich_scan_result(result: dict, schema_id: str) -> dict:
    scores = result.get("weighted_scores", {"a": 50, "b": 50, "c": 50, "d": 50, "e": 50})
    overall_score = calc_weighted(scores, schema_id)
    grade = get_grade(overall_score)
    result["overall_score"] = overall_score
    result["grade"] = grade["grade"]
    result["grade_advice"] = grade["advice"]
    result["grade_color"] = grade["color"]

    material = result.get("material", "plastic")
    if material in HK_DISPOSAL:
        result["disposal_info"] = HK_DISPOSAL[material]
    if schema_id in CRITERIA_LABELS:
        result["criteria_labels"] = CRITERIA_LABELS[schema_id]
    return result
