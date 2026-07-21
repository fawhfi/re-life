"""Offline ReAgent runtime with explicit approval-aware tool workflows."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Protocol
import unicodedata

import numpy as np
import onnxruntime as ort

from backend.ai.workflow import (
    AgentRunContext,
    is_personal_replacement_decision,
    normalize_agent_language,
)


LOCAL_AGENT_STATE_VERSION = 1
LOCAL_AGENT_INTENTS = {
    "guidance",
    "nearby",
    "weather",
    "records",
    "decision",
    "general",
}
LOCAL_AGENT_MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "nlp" / "artifacts" / "reagent_intent.onnx"
)
_GENERAL_OPT_OUT_PHRASES = (
    "do not use any tool",
    "just say hello",
    "沒有要求位置或紀錄",
    "没有要求位置或记录",
    "只想說謝謝",
    "只想说谢谢",
    "純粹入嚟打個招呼",
    "纯粹进来打个招呼",
    "暫時不用執行任何",
    "暂时不用执行任何",
)


def _is_explicit_general_opt_out(message: str) -> bool:
    normalized = _normalized_text(message)
    return any(phrase in normalized for phrase in _GENERAL_OPT_OUT_PHRASES)


class LocalIntentRouter(Protocol):
    """Classify a user message into one supported offline Agent workflow."""

    def classify(self, message: str) -> str: ...


def _encode_agent_message(
    message: str,
    *,
    max_bytes: int,
    content_bytes: int,
) -> np.ndarray:
    payload = str(message or "").strip().lower().encode("utf-8")
    payload_budget = content_bytes - 1
    if len(payload) > payload_budget:
        head_bytes = (payload_budget * 2) // 3
        payload = payload[:head_bytes] + payload[-(payload_budget - head_bytes) :]
    values = [1, *(byte + 2 for byte in payload)]
    values.extend([0] * (max_bytes - len(values)))
    return np.asarray([values], dtype=np.int64)


def _load_local_agent_metadata(
    model_path: Path,
) -> tuple[tuple[str, ...], int, int]:
    metadata_path = model_path.with_suffix(".json")
    if not metadata_path.is_file():
        raise FileNotFoundError(f"Local Agent metadata not found: {metadata_path}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Invalid local Agent metadata: {metadata_path}") from exc
    if not isinstance(metadata, dict):
        raise RuntimeError("Invalid local Agent metadata object")

    raw_labels = metadata.get("labels")
    if not isinstance(raw_labels, list) or not raw_labels:
        raise RuntimeError("Local Agent metadata has no labels")
    labels = tuple(str(label) for label in raw_labels)
    if len(set(labels)) != len(labels) or set(labels) != LOCAL_AGENT_INTENTS:
        raise RuntimeError("Local Agent metadata contains unsupported labels")

    max_bytes = metadata.get("max_bytes")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise RuntimeError("Local Agent metadata has an invalid max_bytes")
    if not 8 <= max_bytes <= 2048:
        raise RuntimeError("Local Agent metadata max_bytes is out of bounds")
    config = metadata.get("config")
    if isinstance(config, dict) and config.get("max_bytes", max_bytes) != max_bytes:
        raise RuntimeError("Local Agent metadata has inconsistent max_bytes")
    content_bytes = config.get("content_bytes", max_bytes) if isinstance(config, dict) else max_bytes
    if isinstance(content_bytes, bool) or not isinstance(content_bytes, int):
        raise RuntimeError("Local Agent metadata has an invalid content_bytes")
    if not 2 <= content_bytes <= max_bytes:
        raise RuntimeError("Local Agent metadata content_bytes is out of bounds")
    if metadata.get("model", model_path.name) != model_path.name:
        raise RuntimeError("Local Agent metadata points to a different model")
    return labels, max_bytes, content_bytes


class OnnxLocalIntentRouter:
    """Run the independent byte-level ReAgent routing Transformer in ONNX Runtime."""

    def __init__(self, model_path: str | Path = LOCAL_AGENT_MODEL_PATH):
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Local Agent model not found: {path}")
        self._labels, self._max_bytes, self._content_bytes = _load_local_agent_metadata(path)
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.intra_op_num_threads = max(
            1,
            min(4, int(os.getenv("REL_LOCAL_AGENT_THREADS", "1"))),
        )
        options.inter_op_num_threads = 1
        options.enable_mem_pattern = False
        options.enable_cpu_mem_arena = False
        self._session = ort.InferenceSession(
            str(path.resolve()),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        inputs = self._session.get_inputs()
        outputs = self._session.get_outputs()
        if len(inputs) != 1 or not outputs:
            raise RuntimeError("Invalid local Agent ONNX interface")
        input_shape = inputs[0].shape
        output_shape = outputs[0].shape
        if inputs[0].type != "tensor(int64)":
            raise RuntimeError("Local Agent ONNX input must use int64 token ids")
        if len(input_shape) != 2 or input_shape[1] != self._max_bytes:
            raise RuntimeError("Local Agent ONNX input does not match metadata")
        if len(output_shape) != 2 or output_shape[1] != len(self._labels):
            raise RuntimeError("Local Agent ONNX output does not match metadata")
        self._input_name = inputs[0].name
        self._output_name = outputs[0].name

    def predict(self, message: str) -> tuple[str, float]:
        logits = np.asarray(
            self._session.run(
                [self._output_name],
                {
                    self._input_name: _encode_agent_message(
                        message,
                        max_bytes=self._max_bytes,
                        content_bytes=self._content_bytes,
                    )
                },
            )[0],
            dtype=np.float32,
        )[0]
        if logits.shape != (len(self._labels),):
            raise RuntimeError("Local Agent model returned an invalid intent shape")
        shifted = logits - logits.max()
        probabilities = np.exp(shifted)
        probabilities /= probabilities.sum()
        index = int(probabilities.argmax())
        return self._labels[index], float(probabilities[index])

    def classify(self, message: str) -> str:
        if _is_explicit_general_opt_out(message):
            return "general"
        protected_intent = HeuristicLocalIntentRouter().classify(message)
        intent, confidence = self.predict(message)
        sensitive_intents = {"decision", "records", "nearby", "weather"}
        if protected_intent in sensitive_intents:
            return protected_intent
        if intent in sensitive_intents:
            return protected_intent
        return intent if confidence >= 0.65 else protected_intent


class HeuristicLocalIntentRouter:
    """Preserve privacy-sensitive routing when the local model is uncertain."""

    def classify(self, message: str) -> str:
        normalized = _normalized_text(message)
        if _is_explicit_general_opt_out(normalized):
            return "general"

        guidance_focus = (
            "my question is how to sort",
            "correct recycling method",
            "正確回收方法",
            "正确回收方法",
            "回唔回收到",
            "回不回收到",
            "怎樣分類回收",
            "怎样分类回收",
            "應該怎樣處理",
            "应该怎样处理",
            "應該如何處理",
            "应该如何处理",
        )
        if any(phrase in normalized for phrase in guidance_focus):
            return "guidance"

        weather_terms = (
            "weather",
            "forecast",
            "rain",
            "temperature",
            "typhoon",
            "天氣",
            "天气",
            "落雨",
            "下雨",
            "大雨",
            "umbrella",
            "thunderstorm",
            "heat warning",
            "雷暴",
            "降雨",
            "颱風",
            "台风",
        )
        negated_records = (
            "not query my recycling records",
            "not my recycling records",
            "不是查询我的回收记录",
            "不是查詢我的回收紀錄",
            "唔係查我嘅回收紀錄",
        )
        if any(term in normalized for term in weather_terms) and any(
            phrase in normalized for phrase in negated_records
        ):
            return "weather"

        strong_decision_terms = (
            "repair quote",
            "repair, donation",
            "repair or replace",
            "fix or replace",
            "翻新",
            "換新",
            "换新",
            "整定換",
            "整定换",
        )
        new_item_choice = (
            any(term in normalized for term in ("新機", "新机"))
            and any(term in normalized for term in ("應該", "应该", "選", "选"))
        )
        if any(term in normalized for term in strong_decision_terms) or new_item_choice:
            return "decision"
        if is_personal_replacement_decision(normalized):
            return "decision"
        saved_history_terms = (
            "saved history",
            "previously saved",
            "last month saved",
            "上個月保存",
            "上个月保存",
            "之前儲存",
            "之前储存",
        )
        if any(term in normalized for term in saved_history_terms):
            return "records"
        if any(term in normalized for term in ("record", "history", "紀錄", "记录", "歷史", "历史")):
            return "records"
        has_scan = any(term in normalized for term in ("scan", "掃描", "扫描"))
        scan_history = has_scan and any(
            term in normalized
            for term in (
                "my recent",
                "my last",
                "what did i scan",
                "scanned before",
                "最近掃描",
                "最近扫描",
                "上次掃描",
                "上次扫描",
                "之前掃描",
                "之前扫描",
                "掃描過",
                "扫描过",
                "掃描咗",
            )
        )
        if scan_history:
            return "records"
        if any(term in normalized for term in weather_terms):
            return "weather"
        nearby = any(term in normalized for term in ("nearby", "nearest", "near me", "close", "closest", "where", "附近", "最近", "邊度", "哪里", "哪裡", "周围", "周圍"))
        recycling = any(term in normalized for term in ("recycl", "drop off", "回收", "collection point", "收集點", "收集点", "電子廢物", "电子废物"))
        facility_accepts = "facility" in normalized and any(
            term in normalized for term in ("takes", "accepts")
        )
        accepts_recyclable_item = any(
            term in normalized for term in ("takes", "accepts", "收舊", "接收")
        ) and any(
            term in normalized
            for term in (
                "metal",
                "can",
                "battery",
                "printer",
                "bicycle",
                "bike",
                "電池",
                "电池",
                "單車",
                "单车",
                "金屬",
                "金属",
                "罐",
                "雪櫃",
                "冰箱",
            )
        )
        explicit_location_search = any(
            term in normalized
            for term in ("use my current location", "使用我的位置", "使用我现在的位置", "定位")
        ) and any(term in normalized for term in ("find", "search", "找", "附近", "周围", "周圍"))
        if explicit_location_search:
            return "nearby"
        if nearby and (recycling or facility_accepts or accepts_recyclable_item):
            return "nearby"
        if recycling or any(term in normalized for term in ("dispose", "which bin", "垃圾桶", "回收箱")):
            return "guidance"
        return "general"


class HybridLocalIntentRouter:
    """Combine Transformer coverage with conservative privacy-sensitive rules."""

    _SENSITIVE_INTENTS = {"decision", "records", "nearby", "weather"}

    def __init__(
        self,
        model: OnnxLocalIntentRouter,
        *,
        fallback: LocalIntentRouter | None = None,
        confidence_threshold: float = 0.65,
    ):
        self._model = model
        self._fallback = fallback or HeuristicLocalIntentRouter()
        self._confidence_threshold = max(0.0, min(1.0, float(confidence_threshold)))

    def classify(self, message: str) -> str:
        if _is_explicit_general_opt_out(message):
            return "general"
        protected_intent = self._fallback.classify(message)
        if protected_intent in self._SENSITIVE_INTENTS:
            return protected_intent
        intent, confidence = self._model.predict(message)
        if intent in self._SENSITIVE_INTENTS:
            return protected_intent
        return intent if confidence >= self._confidence_threshold else protected_intent


def build_local_intent_router(
    model_path: str | Path = LOCAL_AGENT_MODEL_PATH,
) -> LocalIntentRouter:
    """Build the ONNX router, retaining a no-network fallback if loading fails."""
    heuristic = HeuristicLocalIntentRouter()
    try:
        return HybridLocalIntentRouter(
            OnnxLocalIntentRouter(model_path),
            fallback=heuristic,
        )
    except Exception:
        return heuristic


class LazyLocalIntentRouter:
    """Delay ONNX allocation until the remote Agent actually needs fallback."""

    def __init__(self, model_path: str | Path = LOCAL_AGENT_MODEL_PATH):
        self._model_path = Path(model_path)
        self._router: LocalIntentRouter | None = None

    def classify(self, message: str) -> str:
        if self._router is None:
            self._router = build_local_intent_router(self._model_path)
        return self._router.classify(message)


@dataclass(slots=True)
class LocalAgentOutcome:
    status: str
    message: str
    request_id: str = ""
    action_type: str = ""
    pending_state: dict[str, Any] | None = None


_MATERIAL_ALIASES = {
    "paper": ("paper", "cardboard", "carton", "紙", "纸", "紙皮"),
    "plastic": ("plastic", "plastics", "bottle", "膠", "塑料", "塑膠"),
    "glass": ("glass", "jar", "玻璃"),
    "metal": ("metal", "aluminium", "aluminum", "steel", "can", "tin", "金屬", "金属", "鋁", "铝"),
    "compostable": ("organic", "food waste", "compost", "廚餘", "厨余", "有機", "有机"),
    "ewaste": ("e-waste", "ewaste", "electronic", "battery", "電子", "电子", "電池", "电池"),
}

_ITEM_QUERY_ALIASES = {
    "washing machine": ("washing machine", "washer", "洗衣機", "洗衣机"),
    "phone": ("smartphone", "mobile phone", "iphone", "android phone", "手機", "手机", "電話", "电话"),
    "computer": ("laptop", "notebook", "macbook", "computer", "電腦", "电脑", "筆電", "笔电"),
    "tablet": ("tablet", "ipad", "平板"),
    "headphones": ("headphones", "earbuds", "airpods", "耳機", "耳机"),
    "television": ("television", "smart tv", "tv", "電視", "电视"),
    "refrigerator": ("refrigerator", "fridge", "freezer", "雪櫃", "雪柜", "冰箱"),
    "air conditioner": ("air conditioner", "air conditioning", "冷氣機", "冷气机", "冷氣", "冷气", "空調", "空调"),
    "camera": ("digital camera", "camera", "相機", "相机"),
    "watch": ("smartwatch", "smart watch", "watch", "手錶", "手表"),
    "shoes": ("sneakers", "trainers", "footwear", "shoes", "shoe", "鞋子", "鞋"),
    "furniture": ("furniture", "sofa", "couch", "chair", "table", "家具", "沙發", "沙发", "椅", "桌"),
    "bicycle": ("bicycle", "bike", "單車", "单车", "自行車", "自行车"),
    "printer": ("printer", "印表機", "打印機", "打印机"),
    "vacuum": ("vacuum cleaner", "vacuum", "hoover", "吸塵機", "吸尘器"),
}


def _normalized_text(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", str(value or "")),
    ).strip().lower()[:2000]


def _material_from_message(message: str) -> str:
    normalized = _normalized_text(message)
    for material, aliases in _MATERIAL_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return material
    return ""


def _item_query_from_message(message: str) -> str:
    normalized = _normalized_text(message)
    for query, aliases in _ITEM_QUERY_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return query
    english_match = re.search(
        r"\b(?:my|this|that|these|those)\s+"
        r"([a-z0-9][a-z0-9-]*(?:\s+[a-z0-9][a-z0-9-]*){0,2})",
        normalized,
    )
    if english_match:
        words = english_match.group(1).split()
        stopwords = {"and", "but", "has", "have", "is", "keeps", "or", "that", "which", "with"}
        return " ".join(word for word in words if word not in stopwords)[:80]
    chinese_match = re.search(
        r"(?:我的|我嘅|我部|我件|呢部|呢件|這部|这部|這件|这件)"
        r"(.{1,12}?)(?:壞|坏|故障|應該|应该|值得|值不值得|係咪|系咪|[?？])",
        normalized,
    )
    if chinese_match:
        return chinese_match.group(1).strip()[:80]
    return _material_from_message(message)


def _language_text(language: str, *, en: str, simplified: str, traditional: str) -> str:
    normalized = normalize_agent_language(language)
    if normalized == "zh_simplified":
        return simplified
    if normalized == "zh_traditional":
        return traditional
    return en


def _public_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        key: point.get(key)
        for key in (
            "name",
            "distance_m",
            "materials",
            "open_hours",
            "accessibility",
            "maps_url",
            "detail_url",
        )
        if point.get(key) is not None
    }


class LocalAgentRuntime:
    """Run bounded ReAgent workflows locally when a remote model is unavailable."""

    def __init__(self, *, router: LocalIntentRouter | None = None):
        self._router = router or LazyLocalIntentRouter()

    async def start(
        self,
        message: str,
        *,
        context: AgentRunContext,
        session: Any,
    ) -> LocalAgentOutcome:
        del session
        intent = str(self._router.classify(message) or "general").strip().lower()
        if intent not in LOCAL_AGENT_INTENTS:
            intent = "general"
        if context.personal_decision:
            intent = "decision"
        material = _material_from_message(message)
        if intent in {"nearby", "weather"}:
            return self._approval_outcome(
                context,
                message=message,
                intent=intent,
                material=material,
                action_type="get_user_location",
            )
        if intent in {"records", "decision"}:
            return self._approval_outcome(
                context,
                message=message,
                intent=intent,
                material=material,
                action_type="read_user_records",
            )
        if intent == "guidance":
            return self._guidance_outcome(context, material)
        return LocalAgentOutcome(
            status="completed",
            message=_language_text(
                context.language,
                en="The remote model is unavailable. I can still help with recycling guidance, nearby points, weather, your approved records, and item decisions.",
                simplified="远程模型暂时不可用。我仍可协助回收分类、附近回收点、天气、经你批准的记录，以及物品去留决定。",
                traditional="遠端模型暫時不可用。我仍可協助回收分類、附近回收點、天氣、經你批准的紀錄，以及物品去留決定。",
            ),
        )

    async def resume(
        self,
        state: dict[str, Any],
        *,
        context: AgentRunContext,
        session: Any,
        approved: bool,
    ) -> LocalAgentOutcome:
        del session
        if (
            not isinstance(state, dict)
            or state.get("runtime") != "local"
            or state.get("version") != LOCAL_AGENT_STATE_VERSION
        ):
            raise ValueError("Invalid local Agent state")
        intent = str(state.get("intent") or "")
        action_type = str(state.get("action_type") or "")
        material = str(state.get("material") or "")[:40]
        if action_type == "get_user_location":
            if not approved or context.location is None:
                return LocalAgentOutcome(
                    status="completed",
                    message=_language_text(
                        context.language,
                        en="Location was not shared, so I did not search nearby.",
                        simplified="你没有分享位置，因此我没有搜索附近地点。",
                        traditional="你沒有分享位置，因此我沒有搜尋附近地點。",
                    ),
                )
            if intent == "nearby":
                return await self._nearby_outcome(context, material)
            if intent == "weather":
                return await self._weather_outcome(context)
        if action_type == "read_user_records":
            return await self._records_outcome(
                context,
                message=str(state.get("message") or "")[:2000],
                intent=intent,
                approved=approved,
            )
        raise ValueError("Unsupported local Agent action")

    @staticmethod
    def pending_state_for(
        message: str,
        *,
        intent: str,
        action_type: str,
        material: str = "",
    ) -> dict[str, Any]:
        return {
            "runtime": "local",
            "version": LOCAL_AGENT_STATE_VERSION,
            "intent": intent,
            "action_type": action_type,
            "message": str(message or "")[:2000],
            "material": str(material or "")[:40],
        }

    def _approval_outcome(
        self,
        context: AgentRunContext,
        *,
        message: str,
        intent: str,
        material: str,
        action_type: str,
    ) -> LocalAgentOutcome:
        request_id = secrets.token_urlsafe(18)
        if action_type == "get_user_location":
            prompt = _language_text(
                context.language,
                en="I need your location permission to continue.",
                simplified="我需要你的位置权限才能继续。",
                traditional="我需要你的位置權限才能繼續。",
            )
        else:
            prompt = _language_text(
                context.language,
                en="Allow access to your relevant recycling records?",
                simplified="是否允许读取与你问题相关的回收记录？",
                traditional="是否允許讀取與你問題相關的回收紀錄？",
            )
        return LocalAgentOutcome(
            status="requires_action",
            message=prompt,
            request_id=request_id,
            action_type=action_type,
            pending_state=self.pending_state_for(
                message,
                intent=intent,
                action_type=action_type,
                material=material,
            ),
        )

    @staticmethod
    def _guidance_outcome(context: AgentRunContext, material: str) -> LocalAgentOutcome:
        payload = context.guide_lookup(material)
        if isinstance(payload, dict) and not payload.get("error"):
            method = str(payload.get("method") or "")[:300]
            location = str(payload.get("location") or "")[:300]
            detail = "; ".join(value for value in (method, location) if value)
        else:
            detail = ""
        if not detail:
            detail = _language_text(
                context.language,
                en="I could not identify a supported material. Try naming the material or item.",
                simplified="我无法识别受支持的材料，请说明材料或物品名称。",
                traditional="我無法識別受支援的材料，請說明材料或物品名稱。",
            )
        return LocalAgentOutcome(status="completed", message=detail)

    @staticmethod
    async def _nearby_outcome(
        context: AgentRunContext,
        material: str,
    ) -> LocalAgentOutcome:
        latitude, longitude = context.location or (0.0, 0.0)
        points = await context.recycling_lookup(
            latitude,
            longitude,
            material=material,
            limit=5,
            distance_km=3,
        )
        safe_points = [
            _public_point(point)
            for point in list(points or [])[:5]
            if isinstance(point, dict)
        ]
        context.last_points = safe_points
        if not safe_points:
            message = _language_text(
                context.language,
                en="I could not find a supported recycling point within 3 km.",
                simplified="我在三公里内找不到受支持的回收点。",
                traditional="我在三公里內找不到受支援的回收點。",
            )
            return LocalAgentOutcome(status="completed", message=message)
        point = safe_points[0]
        name = str(point.get("name") or "Recycling point")[:160]
        distance = point.get("distance_m")
        distance_text = f" ({int(distance)} m)" if isinstance(distance, (int, float)) else ""
        return LocalAgentOutcome(
            status="completed",
            message=_language_text(
                context.language,
                en=f"The nearest result is {name}{distance_text}.",
                simplified=f"最近的结果是{name}{distance_text}。",
                traditional=f"最近的結果是{name}{distance_text}。",
            ),
        )

    @staticmethod
    async def _weather_outcome(context: AgentRunContext) -> LocalAgentOutcome:
        latitude, longitude = context.location or (0.0, 0.0)
        payload = await context.weather_lookup(latitude=latitude, longitude=longitude)
        summary = ""
        if isinstance(payload, dict):
            summary = str(
                payload.get("summary")
                or payload.get("condition")
                or payload.get("description")
                or ""
            )[:500]
        if not summary:
            summary = _language_text(
                context.language,
                en="Current weather details are unavailable.",
                simplified="目前天气资料不可用。",
                traditional="目前天氣資料不可用。",
            )
        return LocalAgentOutcome(status="completed", message=summary)

    @staticmethod
    async def _records_outcome(
        context: AgentRunContext,
        *,
        message: str,
        intent: str,
        approved: bool,
    ) -> LocalAgentOutcome:
        if not approved:
            return LocalAgentOutcome(
                status="completed",
                message=_language_text(
                    context.language,
                    en="I did not read your records. I can continue with general advice instead.",
                    simplified="我没有读取你的记录，可以改用一般建议继续。",
                    traditional="我沒有讀取你的紀錄，可以改用一般建議繼續。",
                ),
            )
        query = _item_query_from_message(message)
        records = await context.records_lookup(
            user_id=context.user_id,
            limit=5,
            query=query,
        )
        safe_names = [
            str(record.get("name") or record.get("category") or "")[:120]
            for record in list(records or [])[:5]
            if isinstance(record, dict)
        ]
        safe_names = [name for name in safe_names if name]
        if intent == "decision":
            evidence = ", ".join(safe_names[:3])
            if evidence:
                return LocalAgentOutcome(
                    status="completed",
                    message=_language_text(
                        context.language,
                        en=f"I found relevant records for {evidence}. Keep using the item if it is safe and reliable; prefer repair when the fault and cost are reasonable; replace only when safety, repeated failure, compatibility, or lifecycle cost justifies it. Confirm its current condition and repair quote before deciding.",
                        simplified=f"我找到与{evidence}有关的记录。若物品安全可靠可继续使用；故障与费用合理时优先维修；只有安全、反复故障、兼容性或全周期成本足以支持时才更换。决定前请确认当前状况和维修报价。",
                        traditional=f"我找到與{evidence}有關的紀錄。若物品安全可靠可繼續使用；故障與費用合理時優先維修；只有安全、反覆故障、相容性或全週期成本足以支持時才更換。決定前請確認目前狀況和維修報價。",
                    ),
                )
            return LocalAgentOutcome(
                status="completed",
                message=_language_text(
                    context.language,
                    en="I found no matching record. What is failing, is there a safety issue, and what is the repair quote compared with replacement cost?",
                    simplified="我找不到匹配记录。请说明哪里故障、是否有安全问题，以及维修报价相对更换费用是多少。",
                    traditional="我找不到匹配紀錄。請說明哪裡故障、是否有安全問題，以及維修報價相對更換費用是多少。",
                ),
            )
        summary = ", ".join(safe_names) or _language_text(
            context.language,
            en="No matching records were found.",
            simplified="没有找到匹配记录。",
            traditional="沒有找到匹配紀錄。",
        )
        return LocalAgentOutcome(status="completed", message=summary)
