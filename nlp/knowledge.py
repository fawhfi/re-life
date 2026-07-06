from __future__ import annotations

from dataclasses import dataclass
import json
import re

from .labels import CAPTION_TEMPLATES, TOKEN_ALIASES, WASTE_TOKENS

DEFAULT_PROMPT = "Give a practical waste scan summary."


@dataclass(frozen=True, slots=True)
class WasteKnowledge:
    waste_type: str
    aliases: tuple[str, ...]
    material: str
    disposal: str
    recycle: str
    reuse: str
    warning: str
    zh: str


@dataclass(frozen=True, slots=True)
class InstructionExample:
    waste_type: str
    task: str
    prompt: str
    response: str


WASTE_KNOWLEDGE = {
    "glass": WasteKnowledge(
        waste_type="glass",
        aliases=("glass", "bottle", "jar", "cup", "broken glass"),
        material="glass container",
        disposal="Keep it clean, remove the lid if practical, and recycle it with glass.",
        recycle="Recycle clean bottles or jars with glass, separate from mixed trash.",
        reuse="Reuse clean jars as spice storage, cutting-root vases, or desk coin catchers.",
        warning="Wrap broken glass before handling and keep it away from food waste.",
        zh="這看起來是玻璃廢物。先沖洗，能分開瓶蓋就分開，再投入玻璃回收。",
    ),
    "metal": WasteKnowledge(
        waste_type="metal",
        aliases=("metal", "can", "tin", "aluminum", "foil", "aerosol"),
        material="metal packaging",
        disposal="Empty it, rinse sticky residue, and recycle it with metal cans or tins.",
        recycle="Recycle empty cans or tins with metal; flatten them when safe.",
        reuse="Use clean tins as pen cups, seed planters, or small parts holders.",
        warning="Do not recycle pressurized aerosol cans unless local guidance says they are accepted.",
        zh="這看起來是金屬廢物。先清空和簡單沖洗，再按金屬罐或鋁罐回收。",
    ),
    "organic": WasteKnowledge(
        waste_type="organic",
        aliases=("organic", "food waste", "compost", "scraps", "coffee grounds", "bones", "peels", "leftovers"),
        material="food or compostable waste",
        disposal="Put it in food waste or compost where available, and remove any packaging first.",
        recycle="Do not recycle organic waste with dry materials; use food waste or compost channels.",
        reuse="Use suitable scraps for stock, peels for citrus cleaner, or coffee grounds for deodorizing.",
        warning="Do not mix food residue into dry recycling because it can contaminate the whole batch.",
        zh="這看起來是廚餘或有機廢物。先移除包裝，再放入廚餘或堆肥渠道。",
    ),
    "paper": WasteKnowledge(
        waste_type="paper",
        aliases=("paper", "cardboard", "carton", "paperboard", "receipt", "greasy box"),
        material="paper or cardboard",
        disposal="Keep it dry, flatten boxes, and recycle it with paper.",
        recycle="Recycle clean dry paper; remove food residue, plastic windows, and excess tape.",
        reuse="Turn clean cardboard into drawer dividers, gift tags, seed-starting trays, or packing pads.",
        warning="Wet or greasy paper should not go into clean paper recycling.",
        zh="這看起來是紙類廢物。保持乾爽，紙盒先壓平，再放入紙類回收。",
    ),
    "plastic": WasteKnowledge(
        waste_type="plastic",
        aliases=("plastic", "bottle", "container", "packaging", "film", "foam", "bag"),
        material="plastic packaging",
        disposal="Rinse and dry the item if practical, then sort it with accepted plastic recycling.",
        recycle="Recycle accepted plastic only; remove caps, film, or mixed parts when easy.",
        reuse="Reuse bottles as refill containers, cable sorters, mini planters, or a 24-hour second-life challenge.",
        warning="Do not put dirty plastic into paper recycling, and avoid guessing for mixed-material packaging.",
        zh="這看起來是塑膠廢物。可行的話先沖洗和晾乾，再按可接受塑膠類別回收。",
    ),
    "ewaste": WasteKnowledge(
        waste_type="ewaste",
        aliases=("ewaste", "e-waste", "battery", "device", "cable", "bulb", "power bank", "charger"),
        material="electronic waste",
        disposal="Take it to an e-waste collection point instead of normal recycling or general trash.",
        recycle="Recycle electronics through e-waste channels; remove batteries only when safe.",
        reuse="Try repair, a school maker box, a repair cafe, or parts donation before disposal.",
        warning="Do not crush batteries or damaged electronics; they can leak, spark, or overheat.",
        zh="這看起來是電子廢物。不要放入普通回收或垃圾桶，應交到電子廢物回收點。",
    ),
}

JSON_HINTS = {
    "glass": ("rinse recycle glass", "jar storage"),
    "metal": ("empty recycle metal", "pen cup"),
    "organic": ("food waste compost", "stock or cleaner"),
    "paper": ("keep dry recycle", "drawer divider"),
    "plastic": ("rinse recycle plastic", "refill or planter"),
    "ewaste": ("e-waste point", "repair or donate"),
}

PROMPT_VARIANTS = {
    "scan_summary": (DEFAULT_PROMPT, "What is this waste?", "Give a scan summary."),
    "disposal_guidance": ("How should I dispose of this?", "What bin should this go in?", "Give disposal guidance."),
    "recycle_advice": ("Give recycling advice.", "Can this be recycled?", "How do I recycle this?"),
    "reuse_tip": ("Give a short reuse tip.", "Give me a reuse idea.", "Any second life idea?"),
    "safety_warning": ("Give a safety warning.", "Any safety warning?", "What should I avoid?"),
    "json_summary": ("Return JSON with disposal and reuse_tip.", "JSON only.", "Return compact JSON."),
    "zh_summary": ("Use Traditional Chinese.", "用中文回答。", "請用繁體中文回答。"),
}


def knowledge_for(waste_type: str) -> WasteKnowledge:
    return WASTE_KNOWLEDGE.get(waste_type, WASTE_KNOWLEDGE["plastic"])


def _json_response(waste_type: str, knowledge: WasteKnowledge) -> str:
    disposal, reuse = JSON_HINTS[waste_type]
    return json.dumps(
        {"waste_type": waste_type, "disposal": disposal, "reuse_tip": reuse},
        separators=(",", ":"),
    )


def _add_prompt_examples(examples: list[InstructionExample], waste_type: str, task: str, response: str) -> None:
    for prompt in PROMPT_VARIANTS[task]:
        examples.append(InstructionExample(waste_type, task, prompt, response))


def build_instruction_catalog() -> list[InstructionExample]:
    examples: list[InstructionExample] = []
    for waste_type in WASTE_TOKENS:
        knowledge = knowledge_for(waste_type)
        label = TOKEN_ALIASES[waste_type]
        _add_prompt_examples(
            examples,
            waste_type,
            "scan_summary",
            f"This looks like {label.lower()} waste. {knowledge.disposal}",
        )
        for index, caption in enumerate(CAPTION_TEMPLATES[waste_type]):
            prompt = PROMPT_VARIANTS["scan_summary"][index % len(PROMPT_VARIANTS["scan_summary"])]
            examples.append(InstructionExample(waste_type, "scan_summary", prompt, caption))
        _add_prompt_examples(examples, waste_type, "disposal_guidance", knowledge.disposal)
        _add_prompt_examples(examples, waste_type, "recycle_advice", knowledge.recycle)
        _add_prompt_examples(examples, waste_type, "reuse_tip", f"Reuse tip: {knowledge.reuse}")
        _add_prompt_examples(examples, waste_type, "safety_warning", knowledge.warning)
        _add_prompt_examples(examples, waste_type, "json_summary", _json_response(waste_type, knowledge))
        _add_prompt_examples(examples, waste_type, "zh_summary", knowledge.zh)
    return examples


def grounded_response_for(waste_type: str, prompt: str | None = None) -> str:
    knowledge = knowledge_for(waste_type)
    prompt_text = (prompt or DEFAULT_PROMPT).lower()
    label = TOKEN_ALIASES.get(waste_type, waste_type.title())
    if "json" in prompt_text:
        return _json_response(waste_type, knowledge)
    if "chinese" in prompt_text or "zh" in prompt_text or "繁" in prompt_text or "中文" in prompt_text:
        return knowledge.zh
    if "reuse" in prompt_text or "second" in prompt_text:
        return f"Reuse tip: {knowledge.reuse}"
    if "warning" in prompt_text or "safe" in prompt_text or "avoid" in prompt_text:
        return knowledge.warning
    if "recycl" in prompt_text:
        return knowledge.recycle
    if "dispose" in prompt_text or "disposal" in prompt_text or "bin" in prompt_text or "trash" in prompt_text:
        return knowledge.disposal
    return f"This looks like {label.lower()} waste. {knowledge.disposal}"


def response_satisfies_prompt(text: str, prompt: str | None = None) -> bool:
    body = (text or "").strip()
    if not body:
        return False
    prompt_text = (prompt or DEFAULT_PROMPT).lower()
    body_lower = body.lower()
    if "json" in prompt_text:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return False
        return {"waste_type", "disposal", "reuse_tip"}.issubset(payload)
    if "chinese" in prompt_text or "zh" in prompt_text or "繁" in prompt_text or "中文" in prompt_text:
        return bool(re.search(r"[\u4e00-\u9fff]", body))
    if len(body_lower.split()) <= 3:
        return False
    if "reuse" in prompt_text or "second" in prompt_text:
        return "reuse" in body_lower or "second-life" in body_lower or "second life" in body_lower
    if "warning" in prompt_text or "safe" in prompt_text:
        return any(term in body_lower for term in ("warning", "do not", "avoid", "safe", "keep away"))
    return "waste" in body_lower or "recycl" in body_lower
