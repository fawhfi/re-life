"""CNN 图像分类模型"""
import io
import random
import numpy as np
from PIL import Image
import onnxruntime as ort
from pathlib import Path

from core.config import MODEL_PATH
from services.scoring import HK_DISPOSAL

# CNN 配置
CNN_CATEGORIES = ["glass", "metal", "organic", "paper", "plastic", "ewaste"]
CNN_IMG_SIZE = 224
CNN_MEAN = [0.485, 0.456, 0.406]
CNN_STD = [0.229, 0.224, 0.225]

# 分类器映射
CLASSIFIER_MATERIAL_MAP = {
    "glass": {"material": "glass", "standard_type": "general", "eco_rate": 4, "recycle_rate": 5, "description": "Glass container — infinitely recyclable."},
    "metal": {"material": "metal", "standard_type": "general", "eco_rate": 4, "recycle_rate": 5, "description": "Metal can — highly recyclable."},
    "organic": {"material": "compostable", "standard_type": "food", "eco_rate": 5, "recycle_rate": 4, "description": "Organic / food waste — compostable."},
    "paper": {"material": "paper", "standard_type": "general", "eco_rate": 5, "recycle_rate": 5, "description": "Paper / cardboard — biodegradable."},
    "plastic": {"material": "plastic", "standard_type": "general", "eco_rate": 2, "recycle_rate": 3, "description": "Plastic container — limited recyclability."},
    "ewaste": {"material": "plastic", "standard_type": "general", "eco_rate": 2, "recycle_rate": 3, "description": "Electronic waste — contains hazardous materials."},
}

CLASSIFIER_NAME_POOL = {
    "glass": ["Glass Bottle", "Glass Jar", "Glass Container"],
    "metal": ["Aluminum Can", "Metal Tin", "Steel Container"],
    "organic": ["Food Waste", "Organic Scrap", "Compostable Item"],
    "paper": ["Cardboard Box", "Paper Package", "Paper Carton"],
    "plastic": ["Plastic Bottle", "Plastic Container", "Plastic Packaging"],
    "ewaste": ["Electronic Device", "E-Waste Item", "Electronic Component"],
}

# 全局模型实例
_cnn_session: ort.InferenceSession | None = None
_cnn_loaded = False

def _ensure_cnn():
    """确保 CNN 模型已加载"""
    global _cnn_session, _cnn_loaded

    if not _cnn_loaded:
        if MODEL_PATH.exists():
            _cnn_session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
            print(f"[CNN] Model loaded from {MODEL_PATH}")
        else:
            print(f"[CNN] Model not found at {MODEL_PATH}")
        _cnn_loaded = True

def classify_image(image_bytes: bytes) -> tuple[str, float]:
    """使用 CNN 分类图像"""
    _ensure_cnn()

    if _cnn_session is None:
        raise RuntimeError("CNN model not loaded")

    # 预处理图像
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((CNN_IMG_SIZE, CNN_IMG_SIZE), Image.BILINEAR)

    arr = np.array(img, dtype=np.float32) / 255.0
    arr = (arr - np.array(CNN_MEAN, dtype=np.float32)) / np.array(CNN_STD, dtype=np.float32)
    arr = np.transpose(arr, (2, 0, 1))[np.newaxis, ...].astype(np.float32)

    # 推理
    outputs = _cnn_session.run(["logits"], {"image": arr})
    logits = outputs[0][0]

    # Softmax
    exp_logits = np.exp(logits - np.max(logits))
    probs = exp_logits / exp_logits.sum()

    idx = int(np.argmax(probs))
    return CNN_CATEGORIES[idx], float(probs[idx])

def classifier_response(category: str, confidence: float, mode: str) -> dict:
    """生成分类器响应"""
    info = CLASSIFIER_MATERIAL_MAP.get(category, CLASSIFIER_MATERIAL_MAP["plastic"])
    names = CLASSIFIER_NAME_POOL.get(category, CLASSIFIER_NAME_POOL["plastic"])
    name = random.choice(names)

    eco = info["eco_rate"]
    rec = info["recycle_rate"]
    base = round(((eco + rec) / 2) * 20)

    jitter = lambda: max(0, min(100, base + random.randint(-12, 12)))

    material = info["material"]
    disposal_info = HK_DISPOSAL.get(material, HK_DISPOSAL["plastic"])

    return {
        "name": name,
        "brand": "",
        "category": category,
        "standard_type": info["standard_type"],
        "description": f"{info['description']} (Server CNN, {confidence:.0%} confidence)",
        "material": material,
        "eco_rate": eco,
        "recycle_rate": rec,
        "weighted_scores": {
            "a": jitter(),
            "b": jitter(),
            "c": jitter(),
            "d": jitter(),
            "e": jitter()
        },
        "disposal_guide": disposal_info.get("method", ""),
        "precaution": "Server-side classification — verify manually for hazardous items.",
        "disposal_info": disposal_info,
        "alternative": {
            "name": "Eco-Friendly Alternative (CNN)",
            "eco_rate": 5,
            "recycle_rate": 5
        } if mode == "purchase" else None,
        "criteria_labels": {}  # 将在主路由中添加
    }
