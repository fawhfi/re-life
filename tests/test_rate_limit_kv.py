import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import auth
import config


class RateLimitKvTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        auth._rate_limit_store.clear()

    async def asyncTearDown(self):
        auth._rate_limit_store.clear()

    def _request(self, path="/api/scan/ai", ip="203.0.113.7", ua="TestAgent/1.0"):
        return SimpleNamespace(
            headers={
                "x-forwarded-for": ip,
                "user-agent": ua,
            },
            client=SimpleNamespace(host=ip),
            url=SimpleNamespace(path=path),
        )

    async def test_check_rate_limit_uses_kv_when_configured(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"result": "OK"}

        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        with patch.object(auth, "UPSTASH_REDIS_REST_URL", "https://example.upstash.io"), \
             patch.object(auth, "UPSTASH_REDIS_REST_TOKEN", "token"), \
             patch.object(auth.httpx, "AsyncClient", return_value=client_cm):
            await auth.check_rate_limit(self._request(), max_requests=5, window_sec=60)

        client.post.assert_awaited_once()
        _, kwargs = client.post.call_args
        self.assertEqual(
            kwargs["json"],
            ["SET", "rl_203_0_113_7_TestAgent_1_0__api_scan_ai", "1", "EX", "60", "NX"],
        )

    async def test_check_rate_limit_blocks_after_limit(self):
        first = MagicMock(status_code=200)
        first.json.return_value = {"result": "OK"}
        second = MagicMock(status_code=200)
        second.json.return_value = {"result": None}
        third = MagicMock(status_code=200)
        third.json.return_value = {"result": 2}

        client = AsyncMock()
        client.post = AsyncMock(side_effect=[first, second, third])
        client_cm = AsyncMock()
        client_cm.__aenter__.return_value = client
        client_cm.__aexit__.return_value = False

        with patch.object(auth, "UPSTASH_REDIS_REST_URL", "https://example.upstash.io"), \
             patch.object(auth, "UPSTASH_REDIS_REST_TOKEN", "token"), \
             patch.object(auth.httpx, "AsyncClient", return_value=client_cm):
            await auth.check_rate_limit(self._request(), max_requests=1, window_sec=60)
            with self.assertRaises(Exception) as ctx:
                await auth.check_rate_limit(self._request(), max_requests=1, window_sec=60)

        self.assertEqual(getattr(ctx.exception, "status_code", None), 429)

    async def test_check_rate_limit_uses_standard_redis_url_when_configured(self):
        with patch.object(auth, "UPSTASH_REDIS_REST_URL", ""), \
             patch.object(auth, "UPSTASH_REDIS_REST_TOKEN", ""), \
             patch.object(auth, "REDIS_URL", "rediss://default:secret@example.redis-cloud.com:6379", create=True), \
             patch.object(auth, "_redis_rate_count", new=AsyncMock(return_value=1), create=True) as redis_count:
            await auth.check_rate_limit(self._request(), max_requests=5, window_sec=60)

        redis_count.assert_awaited_once_with("rl_203_0_113_7_TestAgent_1_0__api_scan_ai", 60)

    async def test_check_rate_limit_blocks_with_standard_redis_url(self):
        with patch.object(auth, "UPSTASH_REDIS_REST_URL", ""), \
             patch.object(auth, "UPSTASH_REDIS_REST_TOKEN", ""), \
             patch.object(auth, "REDIS_URL", "rediss://default:secret@example.redis-cloud.com:6379", create=True), \
             patch.object(auth, "_redis_rate_count", new=AsyncMock(return_value=6), create=True):
            with self.assertRaises(Exception) as ctx:
                await auth.check_rate_limit(self._request(), max_requests=5, window_sec=60)

        self.assertEqual(getattr(ctx.exception, "status_code", None), 429)

    async def test_subject_limit_is_shared_across_ip_and_user_agent(self):
        with patch.object(auth, "UPSTASH_REDIS_REST_URL", ""), \
             patch.object(auth, "UPSTASH_REDIS_REST_TOKEN", ""), \
             patch.object(auth, "REDIS_URL", ""), \
             patch.object(auth, "IS_DEVELOPMENT", True, create=True), \
             patch.object(auth, "IS_PRODUCTION", False, create=True):
            await auth.check_rate_limit(
                self._request(ip="203.0.113.7", ua="Agent A"),
                max_requests=1,
                window_sec=60,
                subject=" User@Example.COM ",
            )
            with self.assertRaises(Exception) as ctx:
                await auth.check_rate_limit(
                    self._request(ip="198.51.100.9", ua="Agent B"),
                    max_requests=1,
                    window_sec=60,
                    subject="user@example.com",
                )

        self.assertEqual(getattr(ctx.exception, "status_code", None), 429)
        self.assertNotIn("user@example.com", " ".join(auth._rate_limit_store))

    async def test_production_without_durable_backend_fails_closed(self):
        unavailable = getattr(auth, "RateLimitStoreUnavailable", RuntimeError)
        with patch.object(auth, "UPSTASH_REDIS_REST_URL", ""), \
             patch.object(auth, "UPSTASH_REDIS_REST_TOKEN", ""), \
             patch.object(auth, "REDIS_URL", ""), \
             patch.object(auth, "IS_DEVELOPMENT", False, create=True), \
             patch.object(auth, "IS_PRODUCTION", True, create=True):
            with self.assertRaises(unavailable):
                await auth.check_rate_limit(self._request())


class RateLimitConfigTests(unittest.TestCase):
    def test_vercel_kv_rest_env_names_are_supported(self):
        old_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ.update({
                "KV_REST_API_URL": "https://example.upstash.io",
                "KV_REST_API_TOKEN": "token",
            })
            reloaded = importlib.reload(config)
            self.assertEqual(reloaded.UPSTASH_REDIS_REST_URL, "https://example.upstash.io")
            self.assertEqual(reloaded.UPSTASH_REDIS_REST_TOKEN, "token")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            importlib.reload(config)
