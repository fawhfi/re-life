from __future__ import annotations

WASTE_TOKENS = ["glass", "metal", "organic", "paper", "plastic", "ewaste"]

CLASS_TO_IDX = {name: idx for idx, name in enumerate(WASTE_TOKENS)}

TOKEN_ALIASES = {
    "glass": "Glass",
    "metal": "Metal",
    "organic": "Organic",
    "paper": "Paper",
    "plastic": "Plastic",
    "ewaste": "E-waste",
}

NUM_CLASSES = len(WASTE_TOKENS)

CAPTION_TEMPLATES = {
    "glass": [
        "This looks like glass waste. Keep it clean and recycle it separately.",
        "It looks like glass waste, so sort it with glass items.",
        "Glass waste detected. Rinse it and recycle it with glass.",
    ],
    "metal": [
        "This looks like metal waste. Empty it and recycle it with metals.",
        "It looks like metal waste, so sort it with metal items.",
        "Metal waste detected. Keep it separate from regular trash.",
    ],
    "organic": [
        "This looks like organic waste. Treat it as food waste or compost.",
        "It looks like organic waste, so place it with compostable items.",
        "Organic waste detected. Keep it out of regular recycling.",
    ],
    "paper": [
        "This looks like paper waste. Keep it dry and recycle it with paper.",
        "It looks like paper waste, so sort it with paper items.",
        "Paper waste detected. Flatten it and recycle it separately.",
    ],
    "plastic": [
        "This looks like plastic waste. Rinse it if possible and sort it separately.",
        "It looks like plastic waste, so keep it with plastic items.",
        "Plastic waste detected. Keep it away from paper recycling.",
    ],
    "ewaste": [
        "This looks like e-waste. Keep it away from regular recycling.",
        "It looks like e-waste, so handle it as electronic waste.",
        "Electronic waste detected. Do not mix it with normal trash.",
    ],
}


def build_caption_catalog() -> list[str]:
    catalog: list[str] = []
    for waste_type in WASTE_TOKENS:
        catalog.extend(CAPTION_TEMPLATES[waste_type])
    return catalog


def default_caption_for(waste_type: str) -> str:
    templates = CAPTION_TEMPLATES.get(waste_type)
    if templates:
        return templates[0]
    label = TOKEN_ALIASES.get(waste_type, waste_type)
    return f"This looks like {label.lower()} waste."

