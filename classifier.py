"""
classifier.py
=============
ONNX CNN classifier fallback — runs when the NVIDIA AI API fails.

Loads the trained EfficientNet-B2 ONNX model that classifies waste into
6 categories: glass, metal, organic, paper, plastic, ewaste.

Preprocessing matches training:
  - Resize to 260×260
  - Normalize with ImageNet mean/std
  - Run inference, softmax → class probabilities
  - Map predicted material to the response format expected by main.py
"""

from __future__ import annotations

import io
import json
import random
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


# ─── Constants (mirrors cnn_classifier/dataset.py) ──────────────────────────
CATEGORIES   = ["glass", "metal", "organic", "paper", "plastic"]
IMG_SIZE     = 260
MEAN         = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD          = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# ─── Material → response mapping ──────────────────────────────────────────
_MATERIAL_MAP: dict[str, dict] = {
    "glass": {
        "material": "glass",
        "standard_type": "general",
        "eco_rate": 4,
        "recycle_rate": 5,
        "description": "Glass container — infinitely recyclable without quality loss.",
        "disposal_guide": "Rinse clean, remove caps. Place in glass recycling bins.",
        "precaution": "Do not mix with broken window glass or mirrors.",
    },
    "metal": {
        "material": "metal",
        "standard_type": "general",
        "eco_rate": 4,
        "recycle_rate": 5,
        "description": "Metal can or container — highly recyclable and retains value.",
        "disposal_guide": "Rinse clean, flatten if possible. Place in metal recycling bins.",
        "precaution": "Remove any plastic lids or labels before recycling.",
    },
    "organic": {
        "material": "compostable",
        "standard_type": "food",
        "eco_rate": 5,
        "recycle_rate": 4,
        "description": "Organic / food waste — can be composted or used for biogas.",
        "disposal_guide": "Separate from general waste. Use food waste recycling bins where available.",
        "precaution": "Remove any non-compostable packaging before disposal.",
    },
    "paper": {
        "material": "paper",
        "standard_type": "general",
        "eco_rate": 5,
        "recycle_rate": 5,
        "description": "Paper or cardboard packaging — biodegradable and widely recycled.",
        "disposal_guide": "Keep dry, flatten cardboard. Place in blue paper recycling bins.",
        "precaution": "Do not recycle greasy or food-soiled paper.",
    },
    "plastic": {
        "material": "plastic",
        "standard_type": "general",
        "eco_rate": 2,
        "recycle_rate": 3,
        "description": "Plastic container or packaging — check resin code for recyclability.",
        "disposal_guide": "Rinse clean, flatten. Use tri-colour recycling bins or GREEN@COMMUNITY.",
        "precaution": "Remove pumps, spray tops, and mixed-material parts.",
    },
}

# ─── Product name templates per category ───────────────────────────────────
_NAME_POOL: dict[str, list[str]] = {
    "glass":    ["Glass Bottle", "Glass Jar", "Glass Container"],
    "metal":    ["Aluminum Can", "Metal Tin", "Steel Container"],
    "organic":  ["Food Waste", "Organic Scrap", "Compostable Item"],
    "paper":    ["Cardboard Box", "Paper Package", "Paper Carton"],
    "plastic":  ["Plastic Bottle", "Plastic Container", "Plastic Packaging"],
}


class JunkClassifier:
    """Loads ONNX model once at startup and provides predict() for inference."""

    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        self._session = None

    @property
    def session(self):
        if self._session is None:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            # Prefer CPU on Windows for stability; CUDA if available on Linux
            if "CUDAExecutionProvider" in providers:
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            else:
                providers = ["CPUExecutionProvider"]
            self._session = ort.InferenceSession(
                str(self.model_path), providers=providers,
            )
            print(f"[Classifier] Loaded ONNX model: {self.model_path}")
            print(f"[Classifier] Providers: {providers}")
            print(f"[Classifier] Categories: {CATEGORIES}")
        return self._session

    def _preprocess(self, image_bytes: bytes) -> np.ndarray:
        """Resize, normalize, convert to NCHW float32 tensor matching training."""
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        arr = np.array(img, dtype=np.float32) / 255.0          # [0, 1]
        arr = (arr - MEAN) / STD                                # normalize
        arr = np.transpose(arr, (2, 0, 1))                      # HWC → CHW
        return np.expand_dims(arr, axis=0).astype(np.float32)   # add batch dim

    def predict(self, image_bytes: bytes) -> tuple[str, float]:
        """Run inference and return (category_name, confidence)."""
        inp = self._preprocess(image_bytes)
        logits = self.session.run(["logits"], {"image": inp})[0][0]  # shape (6,)
        # Softmax
        ex = np.exp(logits - np.max(logits))
        probs = ex / ex.sum()
        idx = int(np.argmax(probs))
        return CATEGORIES[idx], float(probs[idx])

    def analyze(self, image_bytes: bytes, mode: str) -> dict:
        """
        Full analysis pipeline:
          1. Run classifier → predicted material
          2. Map to eco scores, disposal info, description
          3. Return the dict format expected by main.py's scan_item_ai handler.

        The 'mode' parameter ("dispose" or "purchase") controls whether an
        alternative product suggestion is included (purchase only).
        """
        category, confidence = self.predict(image_bytes)
        info = _MATERIAL_MAP.get(category, _MATERIAL_MAP["plastic"])
        name = random.choice(_NAME_POOL.get(category, _NAME_POOL["plastic"]))

        # Derive weighted scores from eco_rate (1-5 → 0-100 scale with noise)
        eco = info["eco_rate"]
        rec = info["recycle_rate"]
        base = int((eco + rec) / 2 * 20)  # 1-5 → 20-100
        jitter = lambda: max(0, min(100, base + random.randint(-12, 12)))

        result = {
            "name":          name,
            "brand":         "",
            "category":      category,
            "standard_type": info["standard_type"],
            "description":   f"{info['description']} (CNN classifier, {confidence:.0%} confidence)",
            "material":      info["material"],
            "disposal_guide": info["disposal_guide"],
            "precaution":     info["precaution"],
            "eco_rate":       eco,
            "recycle_rate":   rec,
            "weighted_scores": {
                "a": jitter(), "b": jitter(), "c": jitter(), "d": jitter(), "e": jitter(),
            },
            "alternative": (
                {
                    "name":         "Eco-Friendly Alternative (AI fallback)",
                    "eco_rate":     5,
                    "recycle_rate": 5,
                }
                if mode == "purchase"
                else None
            ),
        }
        return result


# ─── Singleton ──────────────────────────────────────────────────────────────
_classifier: Optional[JunkClassifier] = None


def get_classifier(model_path: str | Path | None = None) -> JunkClassifier:
    """Lazy-load the classifier singleton."""
    global _classifier
    if _classifier is None:
        if model_path is None:
            model_path = Path(__file__).parent / "models" / "model.onnx"
        _classifier = JunkClassifier(model_path)
    return _classifier


def classifier_analyze(image_bytes: bytes, mode: str) -> dict:
    """Convenience: one-call classifier analysis."""
    return get_classifier().analyze(image_bytes, mode)
