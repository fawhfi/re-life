"""扫描 API 路由"""
from fastapi import APIRouter, File, UploadFile, Form, Request, HTTPException
from fastapi.responses import JSONResponse
from pathlib import Path
import uuid
from datetime import datetime

from core.security import check_rate_limit
from core.config import ALLOWED_IMAGE_TYPES, MAX_UPLOAD_BYTES
from models.cnn import classify_image, classifier_response
from models.ai_providers import ai_analyze
from services.scoring import calc_weighted_score, get_grade

router = APIRouter()

@router.post("/scan/ai")
async def scan_item_ai(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("dispose"),
    item_type: str = Form("food"),
    item_state: str = Form("new"),
    debug: str = Form("false")
):
    """AI 图像分析端点"""
    await check_rate_limit(request, 15, 60)

    # 验证文件类型
    if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, "Only JPEG, PNG, WebP allowed")

    # 读取文件内容
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)} MB)")

    # 构建 schema ID
    schema_id = f"{item_type}_{item_state}"

    # 尝试 AI 分析
    result = None
    ai_error = None

    if debug.lower() != "true":
        try:
            result = await ai_analyze(contents, schema_id)
        except Exception as e:
            ai_error = str(e)
            print(f"[AI] Error: {ai_error[:200]}")

    # AI 失败则使用 CNN
    if result is None:
        print(f"[Classifier] AI failed, using CNN...")
        try:
            category, confidence = classify_image(contents)
            result = classifier_response(category, confidence, mode)
        except Exception as e:
            print(f"[Classifier] CNN error: {str(e)}")
            raise HTTPException(500, "Image analysis failed")

    # 生成图像 URL (Base64)
    import base64
    ext = Path(str(file.filename)).suffix or ".png"
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    mime = mime_map.get(ext.lstrip("."), "image/jpeg")
    b64 = base64.b64encode(contents).decode()
    result["image_url"] = f"data:{mime};base64,{b64}"

    # 添加元数据
    result["mode"] = mode
    result["id"] = str(uuid.uuid4())
    result["timestamp"] = datetime.now().isoformat()
    result["schema_id"] = schema_id

    # 计算总分和等级
    scores = result.get("weighted_scores", {"a": 50, "b": 50, "c": 50, "d": 50, "e": 50})
    overall = calc_weighted_score(scores, schema_id)
    grade = get_grade(overall)

    result["overall_score"] = overall
    result["grade"] = grade["grade"]
    result["grade_advice"] = grade["advice"]
    result["grade_color"] = grade["color"]

    return JSONResponse(result)
