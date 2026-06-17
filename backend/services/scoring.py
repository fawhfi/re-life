"""评分计算服务"""

# 评分权重
SCHEMA_WEIGHTS = {
    "food_new": {"a": 0.30, "b": 0.25, "c": 0.20, "d": 0.15, "e": 0.10},
    "food_expire": {"a": 0.20, "b": 0.20, "c": 0.25, "d": 0.20, "e": 0.15},
    "item_new": {"a": 0.25, "b": 0.35, "c": 0.10, "d": 0.20, "e": 0.10},
    "item_expire": {"a": 0.25, "b": 0.30, "c": 0.10, "d": 0.25, "e": 0.10},
}

# 评分标准标签
CRITERIA_LABELS = {
    "food_new": {
        "a": "Environmental Impact",
        "b": "Sustainability",
        "c": "Biodegradability",
        "d": "Recyclability",
        "e": "Food Preservation"
    },
    "food_expire": {
        "a": "Environmental Impact",
        "b": "Sustainability",
        "c": "Biodegradability",
        "d": "Recycling",
        "e": "Safety & Waste Prevention"
    },
    "item_new": {
        "a": "Environmental Impact",
        "b": "Sustainability",
        "c": "Biodegradability",
        "d": "Recycling",
        "e": "Social & Innovation"
    },
    "item_expire": {
        "a": "Environmental Impact",
        "b": "Sustainability",
        "c": "Biodegradability",
        "d": "Recycling",
        "e": "Reuse Potential"
    },
}

# 香港废物处理指南
HK_DISPOSAL = {
    "plastic": {
        "type": "Plastic (PET/HDPE)",
        "method": "Rinse clean, flatten",
        "location": "Tri-colour recycling bins, GREEN@COMMUNITY"
    },
    "pp_plastic": {
        "type": "Other Plastic / PP",
        "method": "Rinse clean, disassemble parts",
        "location": "GREEN@COMMUNITY"
    },
    "paper": {
        "type": "Paper / Cardboard",
        "method": "Keep dry, no grease, flatten",
        "location": "Blue paper recycling bins"
    },
    "metal": {
        "type": "Metal Cans",
        "method": "Rinse clean, flatten",
        "location": "Metal recycling bins"
    },
    "glass": {
        "type": "Glass Bottles",
        "method": "Rinse clean, remove caps",
        "location": "Government glass recycling points"
    },
    "compostable": {
        "type": "Compostable",
        "method": "Do NOT place in regular recycling",
        "location": "Industrial/home composting programs"
    },
    "wood": {
        "type": "Wood / Bulky Waste",
        "method": "Remove metal fittings, compress",
        "location": "LCSD collection points or private recyclers"
    },
}

def calc_weighted_score(scores: dict, schema_id: str) -> int:
    """计算加权总分"""
    weights = SCHEMA_WEIGHTS.get(schema_id, SCHEMA_WEIGHTS["food_new"])
    total = sum(scores.get(k, 50) * weights[k] for k in weights)
    return round(total)

def get_grade(score: int) -> dict:
    """根据分数获取等级"""
    if score >= 85:
        return {"grade": "Excellent (A)", "advice": "Highly Recommended", "color": "#065f46"}
    if score >= 70:
        return {"grade": "Good (B)", "advice": "Acceptable", "color": "#047857"}
    if score >= 55:
        return {"grade": "Fair (C)", "advice": "Consider Alternatives", "color": "#ca8a04"}
    if score >= 40:
        return {"grade": "Poor (D)", "advice": "Avoid if Possible", "color": "#b45309"}
    return {"grade": "Very Poor (E)", "advice": "Strongly Discouraged", "color": "#dc2626"}
