"""Firebase 服务（占位符）"""
import httpx
from core.config import FIREBASE_DB_URL

async def get_user_by_email(email: str) -> dict | None:
    """通过邮箱获取用户"""
    if not FIREBASE_DB_URL:
        print(f"[Firebase] FIREBASE_DB_URL not configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{FIREBASE_DB_URL}/users.json")
            if res.status_code != 200:
                print(f"[Firebase] Failed to fetch users: {res.status_code}")
                return None

            users = res.json()
            if not users:
                print(f"[Firebase] No users found")
                return None

            print(f"[Firebase] Searching for email: {email}")
            for key, data in users.items():
                if isinstance(data, dict):
                    user_email = data.get("email", "").lower()
                    print(f"[Firebase] Checking user {key}: {user_email}")
                    if user_email == email.lower():
                        return {"key": key, **data}

        print(f"[Firebase] User not found for email: {email}")
        return None
    except Exception as e:
        print(f"[Firebase] get_user_by_email failed: {e}")
        return None

async def update_password(email: str, new_password: str) -> bool:
    """更新密码（需要实现密码哈希）"""
    user = await get_user_by_email(email)
    if not user or not FIREBASE_DB_URL:
        return False

    try:
        # 这里应该使用 Argon2 或 bcrypt 进行哈希
        # 简化版本，实际应该在客户端使用 Firebase Auth
        password_hash = f"hashed_{new_password}"  # 占位符

        async with httpx.AsyncClient(timeout=10) as client:
            await client.patch(
                f"{FIREBASE_DB_URL}/users/{user['key']}.json",
                json={"passwordHash": password_hash}
            )

        return True
    except Exception as e:
        print(f"[Firebase] update_password failed: {e}")
        return False
