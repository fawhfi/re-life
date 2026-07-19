import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import auth


class ResendEmailTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        auth._pending_verifications.clear()

    async def asyncTearDown(self):
        auth._pending_verifications.clear()

    async def test_send_verification_code_uses_resend_api(self):
        response = MagicMock(status_code=200, text='{"id":"email_1"}')
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        with patch.object(auth, "RESEND_API_KEY", "re_test_123"), \
             patch.object(auth, "RESEND_FROM", "Re-Life <noreply@example.com>"), \
             patch.object(auth, "_generate_code", return_value="123456"), \
             patch.object(auth.httpx, "AsyncClient", return_value=client_cm):
            dev_code = await auth.send_verification_code("user@example.com")

        self.assertIsNone(dev_code)
        client.post.assert_awaited_once()
        _, kwargs = client.post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_test_123")
        self.assertEqual(kwargs["headers"]["User-Agent"], "Re-Life/1.0")
        self.assertEqual(kwargs["json"]["from"], "Re-Life <noreply@example.com>")
        self.assertEqual(kwargs["json"]["to"], ["user@example.com"])
        self.assertEqual(kwargs["json"]["subject"], "Re-Life — Email Verification Code")
        self.assertIn("123456", kwargs["json"]["text"])
        self.assertIn("123456", kwargs["json"]["html"])

    async def test_send_reset_code_uses_resend_api(self):
        response = MagicMock(status_code=200, text='{"id":"email_2"}')
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        with patch.object(auth, "RESEND_API_KEY", "re_test_123"), \
             patch.object(auth, "RESEND_FROM", "Re-Life <noreply@example.com>"), \
             patch.object(auth, "get_user_by_email", new=AsyncMock(return_value={"id": 7, "email": "user@example.com"})), \
             patch.object(auth, "_generate_code", return_value="654321"), \
             patch.object(auth.httpx, "AsyncClient", return_value=client_cm):
            dev_code = await auth.send_reset_code("user@example.com")

        self.assertIsNone(dev_code)
        client.post.assert_awaited_once()
        _, kwargs = client.post.call_args
        self.assertEqual(kwargs["json"]["subject"], "Re-Life — Password Reset Request")
        self.assertEqual(kwargs["json"]["to"], ["user@example.com"])
        self.assertIn("654321", kwargs["json"]["text"])

    async def test_dev_code_requires_explicit_development_opt_in(self):
        unavailable = getattr(auth, "EmailDeliveryUnavailable", RuntimeError)
        with patch.object(auth, "RESEND_API_KEY", ""), \
             patch.object(auth, "IS_DEVELOPMENT", True, create=True), \
             patch.object(auth, "ALLOW_DEV_AUTH_CODES", False), \
             patch.object(auth, "supabase_enabled", return_value=False), \
             patch.object(auth, "_generate_code", return_value="111222"), \
             patch.object(auth.httpx, "AsyncClient") as client_ctor:
            with self.assertRaises(unavailable):
                await auth.send_verification_code("user@example.com")

        self.assertNotIn("verify:user@example.com", auth._pending_verifications)
        client_ctor.assert_not_called()

        with patch.object(auth, "RESEND_API_KEY", ""), \
             patch.object(auth, "IS_DEVELOPMENT", True, create=True), \
             patch.object(auth, "ALLOW_DEV_AUTH_CODES", True), \
             patch.object(auth, "supabase_enabled", return_value=False), \
             patch.object(auth, "_generate_code", return_value="333444"):
            dev_code = await auth.send_verification_code("user@example.com")

        self.assertEqual(dev_code, "333444")
