"""邮件验证服务"""
import random
import time
from collections import defaultdict

from core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, VERIFICATION_CODE_EXPIRY

# 内存存储（生产环境应使用 Redis 或 Firebase）
_pending_verifications: dict[str, dict] = {}
_pending_resets: dict[str, dict] = {}

async def send_verification_code(email: str, reset: bool = False) -> str | None:
    """发送验证码

    返回:
        如果 SMTP 未配置，返回开发模式验证码；否则返回 None
    """
    code = str(random.randint(100000, 999999))

    # 保存到内存
    store = _pending_resets if reset else _pending_verifications
    store[email] = {
        "code": code,
        "expires_at": time.time() + VERIFICATION_CODE_EXPIRY
    }

    # 清理过期验证码
    now = time.time()
    for key in list(store.keys()):
        if store[key].get("expires_at", 0) < now:
            del store[key]

    # 尝试发送邮件
    if SMTP_USER and SMTP_PASS:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg["From"] = SMTP_FROM
            msg["To"] = email

            if reset:
                msg["Subject"] = "Re-Life — Password Reset Code"
                body = f"Your password reset code: {code}\n\nExpires in 5 minutes."
            else:
                msg["Subject"] = "Re-Life — Email Verification Code"
                body = f"Your verification code: {code}\n\nExpires in 5 minutes."

            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)

            print(f"[Email] Sent to {email}")
            return None
        except Exception as e:
            print(f"[Email] SMTP failed: {e}")

    # 开发模式：返回验证码
    print(f"[Email] Dev code for {email}: {code}")
    return code

async def verify_code(email: str, code: str, reset: bool = False) -> bool:
    """验证验证码"""
    store = _pending_resets if reset else _pending_verifications
    pending = store.get(email)

    if not pending:
        return False

    # 检查是否过期
    if time.time() > pending["expires_at"]:
        del store[email]
        return False

    # 验证码匹配
    if pending["code"] == code:
        del store[email]
        return True

    return False
