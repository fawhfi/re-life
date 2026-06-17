"""数据 API 路由"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import random
import uuid

from core.security import check_rate_limit
from services.news import get_news_cached
from services.scoring import SCHEMA_WEIGHTS, CRITERIA_LABELS

router = APIRouter()

# 奖励目录
REWARDS_CATALOG = [
    {"id": "tree-plant", "title": "Plant a Native Tree in HK Country Park", "provider": "Tree Planting HK", "cost": 500, "image": "🌳", "category": "Environment", "description": "Sponsor planting a native sapling in Tai Lam or Sai Kung country park."},
    {"id": "fairprice-voucher", "title": "PARKnSHOP HK$30 Cash Voucher", "provider": "PARKnSHOP", "cost": 350, "image": "🎟️", "category": "Voucher", "description": "Valid at all PARKnSHOP, TASTE, and Fusion stores across Hong Kong."},
    {"id": "mtr-ride", "title": "MTR Single Journey Ticket", "provider": "MTR Corporation", "cost": 200, "image": "🚇", "category": "Transport", "description": "One free adult single journey on any MTR urban line."},
    {"id": "starbucks-treat", "title": "Starbucks HK$25 eGift", "provider": "Starbucks HK", "cost": 280, "image": "☕", "category": "Voucher", "description": "Redeemable for any handcrafted beverage at Starbucks Hong Kong."},
    {"id": "ocean-cleanup", "title": "Sponsor Ocean Cleanup (1kg)", "provider": "Ocean Recovery Alliance", "cost": 150, "image": "🌊", "category": "Environment", "description": "Fund the removal of 1kg of marine plastic from HK coastal waters."},
    {"id": "reusable-kit", "title": "Reusable Eco Starter Kit", "provider": "Green Store HK", "cost": 400, "image": "🎒", "category": "Product", "description": "Bamboo cutlery set, beeswax wrap, and organic cotton tote bag."},
]

# 环保知识
FACTS = [
    "Recycling a single aluminum can saves enough energy to power a TV for 3 hours.",
    "Hong Kong generates over 15,000 tonnes of municipal solid waste every day.",
    "One tree can absorb up to 22kg of CO2 per year.",
    "Plastic bottles take up to 450 years to decompose.",
    "Food waste accounts for 30% of HK municipal solid waste.",
    "Glass is 100% recyclable endlessly without quality loss.",
]

@router.get("/news")
async def news(request: Request):
    """获取环保新闻"""
    await check_rate_limit(request, 30, 120)
    return await get_news_cached()

@router.get("/schemas")
async def schemas(request: Request):
    """获取评分模式配置"""
    await check_rate_limit(request, 60, 60)
    return {
        "item_types": [
            {"value": "food", "label": "Food Items"},
            {"value": "general", "label": "General Items"}
        ],
        "item_states": [
            {"value": "new", "label": "New Purchase"},
            {"value": "expire", "label": "About to Expire"}
        ],
        "weights": SCHEMA_WEIGHTS,
        "criteria_labels": CRITERIA_LABELS
    }

@router.get("/rewards")
async def rewards(request: Request):
    """获取奖励目录"""
    await check_rate_limit(request, 60, 60)
    return REWARDS_CATALOG

@router.post("/rewards/redeem")
async def redeem(request: Request, data: dict):
    """兑换奖励"""
    await check_rate_limit(request, 30, 60)

    reward_id = data.get("reward_id")
    reward = next((r for r in REWARDS_CATALOG if r["id"] == reward_id), None)

    if not reward:
        return JSONResponse({"error": "Reward not found"}, 404)

    # 生成优惠券代码
    code = f"RL-{uuid.uuid4().hex[:6].upper()}-{reward['cost']}"

    return {
        "ok": True,
        "coupon": {
            "code": code,
            "title": reward["title"],
            "image": reward["image"],
            "cost": reward["cost"],
            "claimed_date": "Just now",
            "expiry": "Valid 30 days"
        }
    }

@router.get("/fact")
async def fact(request: Request):
    """获取随机环保知识"""
    await check_rate_limit(request, 60, 60)
    return {"fact": random.choice(FACTS)}
