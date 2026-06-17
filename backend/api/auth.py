"""认证 API 路由"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from core.security import check_rate_limit
from services.email import send_verification_code, verify_code
from services.firebase import get_user_by_email, update_password

ph = PasswordHasher()

router = APIRouter()

@router.post("/send-verification")
async def send_verification(request: Request, data: dict):
    """发送验证码"""
    await check_rate_limit(request, 5, 60)

    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Valid email required")

    dev_code = await send_verification_code(email)
    return JSONResponse({
        "ok": True,
        **({"dev_code": dev_code} if dev_code else {})
    })

@router.post("/verify-code")
async def verify_code_endpoint(request: Request, data: dict):
    """验证验证码"""
    await check_rate_limit(request, 5, 60)

    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()

    if not email or not code:
        raise HTTPException(400, "Email and code required")

    ok = await verify_code(email, code)
    if not ok:
        raise HTTPException(400, "Invalid or expired code")

    return JSONResponse({"ok": True, "email": email})

@router.post("/login")
async def login_with_password(request: Request, data: dict):
    """使用邮箱和密码登录"""
    await check_rate_limit(request, 5, 60)

    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        raise HTTPException(400, "Email and password required")

    # 验证用户
    user = await get_user_by_email(email)
    if not user:
        raise HTTPException(401, "Invalid email or password")

    # 验证 Argon2 密码哈希
    password_hash = user.get("passwordHash", "")
    if not password_hash:
        raise HTTPException(401, "Invalid email or password")

    try:
        ph.verify(password_hash, password)
    except VerifyMismatchError:
        raise HTTPException(401, "Invalid email or password")

    return JSONResponse({
        "ok": True,
        "email": email,
        "displayName": user.get("displayName", ""),
        "uid": user.get("userId", user.get("uid", email))
    })

@router.post("/forgot-password")
async def forgot_password(request: Request, data: dict):
    """忘记密码"""
    await check_rate_limit(request, 3, 120)

    email = (data.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Email required")

    user = await get_user_by_email(email)
    if not user:
        # 防止用户枚举，返回成功
        return JSONResponse({"ok": True})

    dev_code = await send_verification_code(email, reset=True)
    return JSONResponse({
        "ok": True,
        **({"dev_code": dev_code} if dev_code else {})
    })

@router.post("/reset-password")
async def reset_password_endpoint(request: Request, data: dict):
    """重置密码"""
    await check_rate_limit(request, 5, 60)

    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()
    password = data.get("password", "")

    if not email or not code or len(password) < 8:
        raise HTTPException(400, "Email, code, and new password (8+ chars) required")

    # 验证重置码
    ok = await verify_code(email, code, reset=True)
    if not ok:
        raise HTTPException(400, "Invalid or expired code")

    # 更新密码
    user = await get_user_by_email(email)
    if not user:
        raise HTTPException(404, "User not found")

    success = await update_password(email, password)
    if not success:
        raise HTTPException(500, "Failed to update password")

    return JSONResponse({
        "ok": True,
        "displayName": user.get("displayName", ""),
        "email": email
    })
