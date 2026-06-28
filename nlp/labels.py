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
        "It looks like a glass bottle or jar, so rinse it and sort it with glass.",
        "Glass packaging detected. Remove the lid if needed and recycle the container.",
        "This is likely glass waste, such as a bottle, jar, or clear container.",
        "Glass waste detected. Keep it dry, clean, and away from mixed recycling.",
    ],
    "metal": [
        "This looks like metal waste. Empty it and recycle it with metals.",
        "It may be a can, tin, or foil item. Flatten it if possible and sort it with metal.",
        "Metal packaging detected. Keep it separate from regular trash.",
        "This is likely aluminum or steel packaging. Rinse it and recycle it.",
        "Metal waste detected. Do not mix it with food residue if you can avoid it.",
    ],
    "organic": [
        "This looks like organic waste. Treat it as food waste or compost.",
        "It looks like food scraps, peels, or leftovers. Put it with organic waste.",
        "Organic waste detected. Keep it out of regular recycling.",
        "This is likely compostable kitchen waste. Remove packaging before sorting.",
        "Organic waste detected. Keep it in the food waste stream.",
    ],
    "paper": [
        "This looks like paper waste. Keep it dry and recycle it with paper.",
        "It looks like cardboard, carton, or paperboard. Flatten it and sort it with paper.",
        "Paper waste detected. Keep it clean and away from liquids.",
        "This is likely paper packaging. Remove tape if possible and recycle it.",
        "Paper waste detected. Flatten boxes and place them with paper items.",
    ],
    "plastic": [
        "This looks like plastic waste. Rinse it if possible and sort it separately.",
        "It may be a bottle, lid, tray, or wrapper. Sort it with plastic items.",
        "Plastic waste detected. Keep it away from paper recycling.",
        "This is likely a plastic container or film package. Rinse and dry it.",
        "Plastic waste detected. Separate mixed-material packaging when you can.",
    ],
    "ewaste": [
        "This looks like e-waste. Keep it away from regular recycling.",
        "It may be a battery, cable, charger, or device. Handle it as electronic waste.",
        "Electronic waste detected. Do not mix it with normal trash.",
        "This is likely a broken device or accessory. Drop it at an e-waste point.",
        "E-waste detected. Remove batteries if the device allows safe separation.",
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
