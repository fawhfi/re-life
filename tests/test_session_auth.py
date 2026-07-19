from dataclasses import fields
from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import hmac
from http.cookies import SimpleCookie
import importlib
import inspect
import ipaddress
import os
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import auth
import config
import main
import sessions


class SessionSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw_schema = Path("supabase_schema.sql").read_text(encoding="utf-8")
        cls.schema = re.sub(r"(?m)--.*$", "", raw_schema)

        table_matches = re.findall(
            r"create\s+table\s+if\s+not\s+exists\s+public\.app_sessions"
            r"\s*\((.*?)\)\s*;",
            cls.schema,
            re.IGNORECASE | re.DOTALL,
        )
        if len(table_matches) != 1:
            raise AssertionError("expected exactly one active app_sessions table")

        cls.table_block = table_matches[0]
        cls.table_sql = " ".join(cls.table_block.split())

    def test_app_sessions_table_is_between_users_and_scan_records(self):
        app_users_position = self.schema.index(
            "create table if not exists public.app_users"
        )
        app_sessions_position = self.schema.index(
            "create table if not exists public.app_sessions"
        )
        scan_records_position = self.schema.index(
            "create table if not exists public.scan_records"
        )

        self.assertLess(app_users_position, app_sessions_position)
        self.assertLess(app_sessions_position, scan_records_position)

    def test_app_sessions_table_has_secure_session_columns(self):
        self.assertIn(
            "id uuid primary key default gen_random_uuid()",
            self.table_sql,
        )
        self.assertIn(
            "user_id bigint not null references public.app_users(id) on delete cascade",
            self.table_sql,
        )
        self.assertIn("token_hash text not null unique", self.table_sql)
        self.assertIn(
            "user_agent text not null default '' check (char_length(user_agent) <= 256)",
            self.table_sql,
        )
        self.assertIn(
            "request_ip_hash text not null default '' check (char_length(request_ip_hash) <= 64)",
            self.table_sql,
        )
        self.assertIn(
            "created_at timestamptz not null default now()",
            self.table_sql,
        )
        self.assertIn(
            "last_seen_at timestamptz not null default now()",
            self.table_sql,
        )
        self.assertIn("revoked_at timestamptz", self.table_sql)

    def test_app_sessions_hashes_are_lowercase_sha256_or_empty_ip_hash(self):
        self.assertIn(
            "token_hash text not null unique "
            "check (token_hash ~ '^[0-9a-f]{64}$')",
            self.table_sql,
        )
        self.assertIn(
            "check (request_ip_hash = '' or "
            "request_ip_hash ~ '^[0-9a-f]{64}$')",
            self.table_sql,
        )

    def test_app_sessions_table_has_only_non_redundant_lookup_indexes(self):
        self.assertRegex(
            self.schema,
            r"(?im)^\s*create\s+index\s+if\s+not\s+exists\s+"
            r"app_sessions_user_id_idx\s+on\s+public\.app_sessions\s*"
            r"\(\s*user_id\s*\)\s*;",
        )
        self.assertRegex(
            self.schema,
            r"(?im)^\s*create\s+index\s+if\s+not\s+exists\s+"
            r"app_sessions_last_seen_idx\s+on\s+public\.app_sessions\s*"
            r"\(\s*last_seen_at\s*\)\s*;",
        )
        self.assertNotRegex(
            self.schema,
            r"(?im)^\s*create\s+(?:unique\s+)?index\s+"
            r"(?:if\s+not\s+exists\s+)?app_sessions_token_hash_idx\b",
        )

    def test_app_sessions_table_does_not_store_raw_tokens(self):
        column_names = re.findall(
            r"(?m)^\s*([a-z_][a-z0-9_]*)\s+",
            self.table_block,
        )
        token_columns = [name for name in column_names if "token" in name]

        self.assertEqual(["token_hash"], token_columns)


class SessionServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        sessions._memory_sessions_by_hash.clear()
        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()
        self.now = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)
        self.token = "opaque-session-token"
        self.token_hash = hashlib.sha256(self.token.encode("utf-8")).hexdigest()
        self.user_row = {
            "id": 42,
            "public_id": "usr_alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password_hash": "must-not-leak",
            "photo_url": None,
            "spent_points": 3,
            "earned_points": 8,
            "claimed_coupons": [],
            "email_verified": True,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }

    def _session_row(self, **overrides):
        row = {
            "id": "session-1",
            "user_id": 42,
            "token_hash": self.token_hash,
            "user_agent": "browser",
            "request_ip_hash": "",
            "created_at": (self.now - timedelta(days=1)).isoformat(),
            "last_seen_at": (self.now - timedelta(seconds=30)).isoformat(),
            "revoked_at": None,
        }
        row.update(overrides)
        return row

    async def test_create_session_persists_only_hashed_bounded_metadata(self):
        captured = {}

        async def fake_insert(table, values, *, returning=True):
            captured.update(table=table, values=values, returning=returning)

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions.secrets, "token_urlsafe", return_value=self.token) as token_urlsafe, \
             patch.object(sessions, "SESSION_METADATA_HASH_KEY", "metadata-key", create=True), \
             patch.object(sessions, "supabase_insert", new=fake_insert), \
             patch.object(sessions, "_now", return_value=self.now):
            token = await sessions.create_session(
                self.user_row,
                user_agent="x" * 300,
                request_ip="203.0.113.4",
            )

        self.assertEqual(token, self.token)
        token_urlsafe.assert_called_once_with(32)
        self.assertEqual(captured["table"], "app_sessions")
        self.assertFalse(captured["returning"])
        row = captured["values"]
        self.assertEqual(row["user_id"], 42)
        self.assertEqual(row["token_hash"], self.token_hash)
        self.assertNotIn(self.token, row.values())
        self.assertEqual(len(row["user_agent"]), 256)
        expected_ip_hash = hmac.new(
            b"metadata-key",
            ipaddress.ip_address("203.0.113.4").compressed.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(row["request_ip_hash"], expected_ip_hash)
        self.assertEqual(row["last_seen_at"], self.now.isoformat())
        self.assertIsNone(row["revoked_at"])

    async def test_active_session_resolves_with_safe_user_columns(self):
        calls = []

        async def fake_select_one(table, *, columns="*", filters=None, order=None):
            calls.append((table, columns, filters))
            if table == "app_sessions":
                return self._session_row()
            if table == "app_users":
                return dict(self.user_row)
            raise AssertionError(f"unexpected table: {table}")

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=fake_select_one), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertIsInstance(context, sessions.SessionContext)
        self.assertEqual(context.session_id, "session-1")
        self.assertEqual(context.user["displayName"], "Alice")
        self.assertNotIn("password_hash", context.user)
        self.assertFalse(context.refresh_cookie)
        self.assertEqual(
            [field.name for field in fields(context)],
            ["session_id", "user", "refresh_cookie"],
        )
        self.assertFalse(hasattr(context, "token"))
        self.assertNotIn(self.token, repr(context))
        user_call = next(call for call in calls if call[0] == "app_users")
        self.assertEqual(user_call[2], {"id": 42})
        self.assertEqual(user_call[1], sessions.SAFE_USER_COLUMNS)
        self.assertNotIn("password_hash", user_call[1])

    async def test_idle_session_at_limit_is_revoked(self):
        update = AsyncMock()
        row = self._session_row(
            last_seen_at=(
                self.now - timedelta(seconds=sessions.SESSION_IDLE_SECONDS)
            ).isoformat()
        )

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=AsyncMock(return_value=row)), \
             patch.object(sessions, "supabase_update", new=update), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertIsNone(context)
        update.assert_awaited_once_with(
            "app_sessions",
            {"revoked_at": self.now.isoformat()},
            filters={"token_hash": self.token_hash},
            returning=False,
        )

    async def test_revoked_session_fails_closed_without_loading_user(self):
        select_one = AsyncMock(
            return_value=self._session_row(revoked_at=self.now.isoformat())
        )

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=select_one), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertIsNone(context)
        self.assertEqual(select_one.await_count, 1)

    async def test_missing_user_fails_closed_and_revokes_session(self):
        async def fake_select_one(table, *, columns="*", filters=None, order=None):
            return self._session_row() if table == "app_sessions" else None

        update = AsyncMock()
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=fake_select_one), \
             patch.object(sessions, "supabase_update", new=update), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertIsNone(context)
        update.assert_awaited_once()

    async def test_invalid_last_seen_fails_closed_and_attempts_revoke(self):
        update = AsyncMock()
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(
                 sessions,
                 "supabase_select_one",
                 new=AsyncMock(return_value=self._session_row(last_seen_at="not-a-time")),
             ), \
             patch.object(sessions, "supabase_update", new=update), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertIsNone(context)
        update.assert_awaited_once()

    async def test_far_future_last_seen_fails_closed_and_attempts_revoke(self):
        update = AsyncMock()
        row = self._session_row(
            last_seen_at=(
                self.now
                + timedelta(seconds=getattr(sessions, "SESSION_CLOCK_SKEW_SECONDS", 0) + 1)
            ).isoformat()
        )

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=AsyncMock(return_value=row)), \
             patch.object(sessions, "supabase_update", new=update), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertIsNone(context)
        update.assert_awaited_once()

    async def test_last_seen_within_clock_skew_is_accepted(self):
        skew_seconds = getattr(sessions, "SESSION_CLOCK_SKEW_SECONDS", 300)
        row = self._session_row(
            last_seen_at=(self.now + timedelta(seconds=skew_seconds)).isoformat()
        )

        async def fake_select_one(table, *, columns="*", filters=None, order=None):
            return row if table == "app_sessions" else dict(self.user_row)

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=fake_select_one), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertIsNotNone(context)
        self.assertFalse(context.refresh_cookie)

    async def test_touch_interval_updates_last_seen_and_refreshes_cookie(self):
        row = self._session_row(
            last_seen_at=(
                self.now - timedelta(seconds=sessions.SESSION_TOUCH_INTERVAL_SECONDS)
            ).isoformat()
        )
        update = AsyncMock()

        async def fake_select_one(table, *, columns="*", filters=None, order=None):
            return row if table == "app_sessions" else dict(self.user_row)

        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=fake_select_one), \
             patch.object(sessions, "supabase_update", new=update), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertTrue(context.refresh_cookie)
        update.assert_awaited_once_with(
            "app_sessions",
            {"last_seen_at": self.now.isoformat()},
            filters={"token_hash": self.token_hash},
            returning=False,
        )

    async def test_session_before_touch_interval_does_not_refresh_cookie(self):
        async def fake_select_one(table, *, columns="*", filters=None, order=None):
            return self._session_row() if table == "app_sessions" else dict(self.user_row)

        update = AsyncMock()
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=fake_select_one), \
             patch.object(sessions, "supabase_update", new=update), \
             patch.object(sessions, "_now", return_value=self.now):
            context = await sessions.resolve_session(self.token)

        self.assertFalse(context.refresh_cookie)
        update.assert_not_awaited()

    async def test_production_without_supabase_raises_store_unavailable(self):
        with patch.object(sessions, "IS_DEVELOPMENT", False), \
             patch.object(sessions, "supabase_enabled", return_value=False):
            with self.assertRaises(sessions.SecurityStoreUnavailable):
                await sessions.create_session(self.user_row)
            with self.assertRaises(sessions.SecurityStoreUnavailable):
                await sessions.resolve_session(self.token)
            with self.assertRaises(sessions.SecurityStoreUnavailable):
                await sessions.revoke_session(self.token)
            with self.assertRaises(sessions.SecurityStoreUnavailable):
                await sessions.revoke_all_user_sessions(42)

    async def test_production_with_ip_requires_metadata_hash_key(self):
        insert = AsyncMock()
        with patch.object(sessions, "IS_DEVELOPMENT", False), \
             patch.object(sessions, "SESSION_METADATA_HASH_KEY", "", create=True), \
             patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_insert", new=insert):
            with self.assertRaises(sessions.SecurityStoreUnavailable):
                await sessions.create_session(self.user_row, request_ip="203.0.113.4")

        insert.assert_not_awaited()
        self.assertEqual(sessions._memory_sessions_by_hash, {})

    async def test_development_memory_store_supports_create_resolve_and_revoke(self):
        auth._memory_users_by_id[42] = dict(self.user_row)

        with patch.object(sessions, "IS_DEVELOPMENT", True), \
             patch.object(sessions, "supabase_enabled", return_value=False), \
             patch.object(sessions.secrets, "token_urlsafe", return_value=self.token), \
             patch.object(sessions, "_now", return_value=self.now):
            token = await sessions.create_session(self.user_row)
            context = await sessions.resolve_session(token)
            await sessions.revoke_session(token)
            revoked_context = await sessions.resolve_session(token)

        self.assertEqual(list(sessions._memory_sessions_by_hash), [self.token_hash])
        self.assertEqual(context.user["id"], 42)
        self.assertIsNone(revoked_context)

    async def test_development_memory_user_is_returned_as_an_independent_copy(self):
        memory_user = dict(self.user_row)
        memory_user["claimed_coupons"] = ["coupon-1"]
        auth._memory_users_by_id[42] = memory_user

        with patch.object(sessions, "IS_DEVELOPMENT", True), \
             patch.object(sessions, "supabase_enabled", return_value=False), \
             patch.object(sessions.secrets, "token_urlsafe", return_value=self.token), \
             patch.object(sessions, "_now", return_value=self.now):
            token = await sessions.create_session(self.user_row)
            context = await sessions.resolve_session(token)

        context.user["claimedCoupons"].append("coupon-2")
        self.assertEqual(memory_user["claimed_coupons"], ["coupon-1"])

    async def test_revoke_all_user_sessions_filters_only_by_user_id(self):
        update = AsyncMock()
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_update", new=update), \
             patch.object(sessions, "_now", return_value=self.now):
            await sessions.revoke_all_user_sessions("42")

        update.assert_awaited_once_with(
            "app_sessions",
            {"revoked_at": self.now.isoformat()},
            filters={"user_id": 42},
            returning=True,
        )

    async def test_hmac_ip_hash_canonicalizes_addresses_and_separates_keys(self):
        expanded = "2001:0db8:0000:0000:0000:0000:0000:0001"
        compressed = "2001:db8::1"

        with patch.object(sessions, "SESSION_METADATA_HASH_KEY", "key-a", create=True):
            expanded_hash = sessions._ip_hash(expanded)
            compressed_hash = sessions._ip_hash(compressed)
        with patch.object(sessions, "SESSION_METADATA_HASH_KEY", "key-b", create=True):
            other_key_hash = sessions._ip_hash(compressed)

        self.assertEqual(expanded_hash, compressed_hash)
        self.assertNotEqual(compressed_hash, other_key_hash)
        self.assertRegex(compressed_hash, r"^[0-9a-f]{64}$")

    async def test_supabase_insert_failure_preserves_cause_and_never_writes_memory(self):
        backend_error = RuntimeError("insert unavailable")
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_insert", new=AsyncMock(side_effect=backend_error)):
            with self.assertRaises(sessions.SecurityStoreUnavailable) as raised:
                await sessions.create_session(self.user_row)

        self.assertIs(raised.exception.__cause__, backend_error)
        self.assertEqual(sessions._memory_sessions_by_hash, {})

    async def test_supabase_select_failure_preserves_cause_and_never_reads_memory(self):
        sessions._memory_sessions_by_hash[self.token_hash] = self._session_row()
        backend_error = RuntimeError("select unavailable")
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_select_one", new=AsyncMock(side_effect=backend_error)):
            with self.assertRaises(sessions.SecurityStoreUnavailable) as raised:
                await sessions.resolve_session(self.token)

        self.assertIs(raised.exception.__cause__, backend_error)
        self.assertIsNone(sessions._memory_sessions_by_hash[self.token_hash].get("revoked_at"))

    async def test_supabase_update_failure_preserves_cause_and_never_writes_memory(self):
        sessions._memory_sessions_by_hash[self.token_hash] = self._session_row()
        backend_error = RuntimeError("update unavailable")
        with patch.object(sessions, "supabase_enabled", return_value=True), \
             patch.object(sessions, "supabase_update", new=AsyncMock(side_effect=backend_error)):
            with self.assertRaises(sessions.SecurityStoreUnavailable) as raised:
                await sessions.revoke_session(self.token)

        self.assertIs(raised.exception.__cause__, backend_error)
        self.assertIsNone(sessions._memory_sessions_by_hash[self.token_hash].get("revoked_at"))

    async def test_invalidation_cleanup_store_failures_still_reject_sessions(self):
        cases = {
            "malformed": (self._session_row(last_seen_at="bad-time"), self.user_row),
            "future": (
                self._session_row(
                    last_seen_at=(self.now + timedelta(days=1)).isoformat()
                ),
                self.user_row,
            ),
            "idle": (
                self._session_row(
                    last_seen_at=(
                        self.now - timedelta(seconds=sessions.SESSION_IDLE_SECONDS)
                    ).isoformat()
                ),
                self.user_row,
            ),
            "missing-user": (self._session_row(), None),
        }

        for name, (row, user) in cases.items():
            with self.subTest(name=name), \
                 patch.object(sessions, "_load_session_row", new=AsyncMock(return_value=row)), \
                 patch.object(sessions, "_load_user", new=AsyncMock(return_value=user)), \
                 patch.object(
                     sessions,
                     "revoke_session",
                     new=AsyncMock(side_effect=sessions.SecurityStoreUnavailable("down")),
                 ) as revoke, \
                 patch.object(sessions, "_now", return_value=self.now):
                context = await sessions.resolve_session(self.token)

            self.assertIsNone(context)
            revoke.assert_awaited_once_with(self.token)

    async def test_best_effort_revoke_only_swallows_store_unavailable(self):
        with patch.object(
            sessions,
            "revoke_session",
            new=AsyncMock(side_effect=RuntimeError("programming error")),
        ):
            with self.assertRaisesRegex(RuntimeError, "programming error"):
                await sessions._best_effort_revoke(self.token)

    def test_auth_exposes_public_user_normalizer(self):
        claimed = ["coupon-1"]
        row = {**self.user_row, "claimed_coupons": claimed}
        normalized = auth.normalize_user_row(row)

        self.assertEqual(normalized["displayName"], "Alice")
        self.assertNotIn("password_hash", normalized)
        self.assertIn("password_hash", inspect.getdoc(auth.normalize_user_row))
        normalized["claimedCoupons"].append("coupon-2")
        self.assertEqual(claimed, ["coupon-1"])

class SessionMetadataKeyConfigTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)

    def test_development_without_metadata_key_uses_development_only_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            development = importlib.reload(config)

        self.assertEqual(
            development.SESSION_METADATA_HASH_KEY,
            "development-only-session-metadata-key",
        )

    def test_production_rejects_missing_blank_or_short_metadata_key(self):
        invalid_values = {
            "missing": None,
            "blank": "   ",
            "short": "x" * 31,
        }

        for name, value in invalid_values.items():
            environment = {"APP_ENV": "production"}
            if value is not None:
                environment["SESSION_METADATA_HASH_KEY"] = value

            with self.subTest(name=name), patch.dict(
                os.environ, environment, clear=True
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "SESSION_METADATA_HASH_KEY"
                ) as raised:
                    importlib.reload(config)
                if value:
                    self.assertNotIn(value, str(raised.exception))

    def test_production_rejects_metadata_key_reused_from_supabase(self):
        reused_key = "shared-production-secret-key-value"
        supabase_key_names = (
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_PUBLISHABLE_KEY",
        )

        for supabase_key_name in supabase_key_names:
            with self.subTest(supabase_key_name=supabase_key_name), patch.dict(
                os.environ,
                {
                    "APP_ENV": "production",
                    "SESSION_METADATA_HASH_KEY": reused_key,
                    supabase_key_name: reused_key,
                },
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "獨立|independent"
                ) as raised:
                    importlib.reload(config)
                self.assertNotIn(reused_key, str(raised.exception))

    def test_production_accepts_strong_independent_metadata_key(self):
        metadata_hash_key = "m" * 32
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "SESSION_METADATA_HASH_KEY": metadata_hash_key,
                "SUPABASE_SECRET_KEY": "different-supabase-secret-key-value",
                "SUPABASE_SERVICE_ROLE_KEY": "different-service-role-key-value",
                "SUPABASE_ANON_KEY": "different-anon-key-value",
                "SUPABASE_PUBLISHABLE_KEY": "different-publishable-key-value",
            },
            clear=True,
        ):
            production = importlib.reload(config)

        self.assertEqual(production.SESSION_METADATA_HASH_KEY, metadata_hash_key)

    def test_production_template_has_explicit_session_security_settings(self):
        template = Path("template.env").read_text(encoding="utf-8")
        required_lines = (
            "APP_ENV=production",
            "SESSION_COOKIE_NAME=rel_session",
            "SESSION_IDLE_DAYS=30",
            "SESSION_TOUCH_INTERVAL_SECONDS=900",
            "SESSION_CLOCK_SKEW_SECONDS=300",
            "SESSION_METADATA_HASH_KEY=",
        )

        for line in required_lines:
            with self.subTest(line=line):
                self.assertRegex(template, rf"(?m)^{re.escape(line)}$")
        self.assertRegex(
            template,
            r"(?m)^# .*production.*啟動.*拒絕.*(?:空|弱|過短).*重用.*金鑰",
        )


class SessionRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.token = "opaque-route-token"
        self.raw_user = {
            "id": 42,
            "public_id": "usr_alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password_hash": "must-not-leak",
            "photo_url": None,
            "spent_points": 3,
            "earned_points": 8,
            "claimed_coupons": [],
            "email_verified": True,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }
        self.safe_user = auth.normalize_user_row(self.raw_user)

    def tearDown(self):
        self.client.close()

    def _context(self, *, refresh_cookie=False):
        return sessions.SessionContext(
            session_id="session-1",
            user=dict(self.raw_user),
            refresh_cookie=refresh_cookie,
        )

    def _cookie(self, response):
        parsed = SimpleCookie()
        parsed.load(response.headers.get("set-cookie", ""))
        return parsed[config.SESSION_COOKIE_NAME]

    def _session_cookie_values(self, response):
        values = []
        prefix = f"{config.SESSION_COOKIE_NAME}="
        for header in response.headers.get_list("set-cookie"):
            if not header.startswith(prefix):
                continue
            parsed = SimpleCookie()
            parsed.load(header)
            values.append(parsed[config.SESSION_COOKIE_NAME].value)
        return values

    def test_me_rejects_missing_session_with_authentication_required_detail(self):
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=None),
        ) as resolve:
            response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "AUTHENTICATION_REQUIRED"})
        resolve.assert_awaited_once_with(None)

    def test_me_returns_safe_normalized_user_for_valid_session(self):
        context = self._context()
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ) as resolve:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "user": self.safe_user})
        self.assertNotIn("password_hash", response.json()["user"])
        resolve.assert_awaited_once_with(self.token)

    def test_register_requires_well_formed_verification_code(self):
        payload = {
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": "correct-pass",
        }
        for verification_code in (None, "12345", "abcdef"):
            register = AsyncMock(return_value=self.safe_user)
            request_payload = dict(payload)
            if verification_code is not None:
                request_payload["verification_code"] = verification_code
            with self.subTest(verification_code=verification_code), patch.object(
                main, "check_rate_limit", new=AsyncMock()
            ), patch.object(main, "create_user", new=register):
                response = self.client.post(
                    "/api/auth/register",
                    json=request_payload,
                )

            self.assertEqual(response.status_code, 422)
            register.assert_not_awaited()

    def test_register_consumes_code_in_create_user_and_never_sets_session_cookie(self):
        context = self._context(refresh_cookie=True)
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()), patch.object(
            main, "create_user", new=AsyncMock(return_value=self.safe_user)
        ) as register, patch.object(
            main, "create_session", new=AsyncMock()
        ) as create_session:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.post(
                "/api/auth/register",
                json={
                    "displayName": " Alice ",
                    "email": " Alice@Example.COM ",
                    "password": "correct-pass",
                    "verification_code": "123456",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "user": self.safe_user})
        self.assertNotIn("set-cookie", response.headers)
        register.assert_awaited_once_with(
            "Alice",
            "correct-pass",
            "alice@example.com",
            verification_code="123456",
        )
        create_session.assert_not_awaited()

    def test_register_rejects_wrong_or_reused_code(self):
        register = AsyncMock(side_effect=ValueError("INVALID_OR_EXPIRED_CODE"))
        with patch.object(main, "check_rate_limit", new=AsyncMock()), patch.object(
            main, "create_user", new=register
        ):
            response = self.client.post(
                "/api/auth/register",
                json={
                    "display_name": "Alice",
                    "email": "alice@example.com",
                    "password": "correct-pass",
                    "verification_code": "123456",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "INVALID_OR_EXPIRED_CODE"})

    def test_independent_verify_code_route_is_removed(self):
        response = self.client.post(
            "/api/verify-code",
            json={"email": "alice@example.com", "code": "123456"},
        )

        self.assertEqual(response.status_code, 404)

    def test_login_accepts_both_display_name_fields_and_sets_secure_cookie_shape(self):
        payloads = (
            {"display_name": " Alice ", "password": "correct-pass"},
            {"displayName": " Alice ", "password": "correct-pass"},
        )
        for is_production in (False, True):
            for payload in payloads:
                self.client.cookies.clear()
                with self.subTest(is_production=is_production, payload=payload), \
                     patch.object(main, "check_rate_limit", new=AsyncMock()) as rate_limit, \
                     patch.object(main, "login_user", new=AsyncMock(return_value=self.raw_user)) as login, \
                     patch.object(
                         main,
                         "create_session",
                         new=AsyncMock(return_value=self.token),
                     ) as create, \
                     patch.object(
                         sessions,
                         "IS_PRODUCTION",
                         is_production,
                     ):
                    response = self.client.post(
                        "/api/auth/login",
                        json=payload,
                        headers={
                            "user-agent": "route-test-browser",
                            "x-forwarded-for": "203.0.113.99",
                        },
                    )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"ok": True, "user": self.safe_user})
                self.assertNotIn("password_hash", response.json()["user"])
                self.assertEqual(rate_limit.await_args.args[1:], (5, 60))
                login.assert_awaited_once_with("Alice", "correct-pass")
                create.assert_awaited_once_with(
                    self.raw_user,
                    user_agent="route-test-browser",
                    request_ip="testclient",
                )
                cookie = self._cookie(response)
                self.assertEqual(cookie.value, self.token)
                self.assertEqual(cookie["path"], "/")
                self.assertEqual(cookie["max-age"], str(config.SESSION_IDLE_SECONDS))
                self.assertEqual(cookie["samesite"].lower(), "lax")
                self.assertTrue(cookie["httponly"])
                self.assertEqual(bool(cookie["secure"]), is_production)

    def test_login_with_refreshable_session_emits_only_new_session_cookie(self):
        new_token = "new-session-token"
        context = self._context(refresh_cookie=True)
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()), \
             patch.object(
                 main,
                 "login_user",
                 new=AsyncMock(return_value=self.raw_user),
             ), patch.object(
                 main,
                 "create_session",
                 new=AsyncMock(return_value=new_token),
             ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.post(
                "/api/auth/login",
                json={"display_name": "Alice", "password": "correct-pass"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._session_cookie_values(response), [new_token])
        self.assertNotIn(self.token, response.headers.get("set-cookie", ""))

    def test_bad_credentials_do_not_create_or_set_session_cookie(self):
        context = self._context(refresh_cookie=True)
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()), \
             patch.object(
                 main,
                 "login_user",
                 new=AsyncMock(side_effect=ValueError("INVALID_CREDENTIALS")),
             ), \
             patch.object(main, "create_session", new=AsyncMock()) as create:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.post(
                "/api/auth/login",
                json={"displayName": "Alice", "password": "wrong-pass"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "INVALID_CREDENTIALS"})
        self.assertNotIn("set-cookie", response.headers)
        create.assert_not_awaited()

    def test_login_session_store_outage_returns_503_without_cookie(self):
        context = self._context(refresh_cookie=True)
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()), \
             patch.object(main, "login_user", new=AsyncMock(return_value=self.raw_user)), \
             patch.object(
                 main,
                 "create_session",
                 new=AsyncMock(
                     side_effect=sessions.SecurityStoreUnavailable("store down")
                 ),
             ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.post(
                "/api/auth/login",
                json={"display_name": "Alice", "password": "correct-pass"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "AUTH_SERVICE_UNAVAILABLE"})
        self.assertNotIn("set-cookie", response.headers)

    def test_successful_password_reset_revokes_all_sessions_and_outage_fails_closed(self):
        tokens = ("alice-old-session-a", "alice-old-session-b")
        now = datetime.now(timezone.utc).isoformat()
        auth._memory_users_by_id[42] = dict(self.raw_user)
        sessions._memory_sessions_by_hash.clear()
        for index, token in enumerate(tokens, start=1):
            sessions._memory_sessions_by_hash[sessions._token_hash(token)] = {
                "id": f"reset-session-{index}",
                "user_id": 42,
                "last_seen_at": now,
                "revoked_at": None,
            }

        try:
            with patch.object(sessions, "IS_DEVELOPMENT", True), \
                 patch.object(sessions, "supabase_enabled", return_value=False), \
                 patch.object(main, "check_rate_limit", new=AsyncMock()), \
                 patch.object(main, "verify_reset_code", new=AsyncMock(return_value=self.raw_user)), \
                 patch.object(main, "update_password", new=AsyncMock(return_value=True)):
                response = self.client.post(
                    "/api/reset-password",
                    json={
                        "email": "alice@example.com",
                        "code": "123456",
                        "password": "new-password",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["ok"])
                for token in tokens:
                    self.assertIsNone(asyncio.run(sessions.resolve_session(token)))
                    self.client.cookies.set(config.SESSION_COOKIE_NAME, token)
                    protected = self.client.get("/api/users/me")
                    self.assertEqual(protected.status_code, 401)

                with patch.object(
                    main,
                    "revoke_all_user_sessions",
                    new=AsyncMock(
                        side_effect=sessions.SecurityStoreUnavailable("store down")
                    ),
                    create=True,
                ):
                    unavailable = self.client.post(
                        "/api/reset-password",
                        json={
                            "email": "alice@example.com",
                            "code": "123456",
                            "password": "newer-password",
                        },
                    )

                self.assertEqual(unavailable.status_code, 503)
                self.assertEqual(
                    unavailable.json(),
                    {"error": "AUTH_SERVICE_UNAVAILABLE"},
                )
                self.assertNotIn("ok", unavailable.json())
        finally:
            sessions._memory_sessions_by_hash.clear()
            auth._memory_users_by_id.clear()

    def test_forgot_password_has_one_response_for_known_unknown_and_mail_outage(self):
        unavailable = getattr(auth, "EmailDeliveryUnavailable", RuntimeError)
        send_reset = AsyncMock(
            side_effect=(None, unavailable("mail unavailable"))
        )
        lookup = AsyncMock(return_value=self.raw_user)
        responses = []
        with patch.object(main, "check_rate_limit", new=AsyncMock()), \
             patch.object(main, "send_reset_code", new=send_reset), \
             patch.object(main, "get_user_by_email", new=lookup, create=True):
            for email in ("known@example.com", "unknown@example.com"):
                responses.append(
                    self.client.post("/api/forgot-password", json={"email": email})
                )

        self.assertEqual(
            [(response.status_code, response.json()) for response in responses],
            [(200, {"ok": True}), (200, {"ok": True})],
        )
        self.assertEqual(send_reset.await_count, 2)
        lookup.assert_not_awaited()

    def test_reset_clears_refreshable_cookie_on_success_and_revoke_outage(self):
        context = self._context(refresh_cookie=True)
        revoke_all = AsyncMock(
            side_effect=(None, sessions.SecurityStoreUnavailable("store down"))
        )
        with patch.object(
            sessions, "resolve_session", new=AsyncMock(return_value=context)
        ), patch.object(main, "check_rate_limit", new=AsyncMock()), \
             patch.object(
                 main, "verify_reset_code", new=AsyncMock(return_value=self.raw_user)
             ), patch.object(
                 main, "update_password", new=AsyncMock(return_value=True)
             ), patch.object(main, "revoke_all_user_sessions", new=revoke_all):
            responses = []
            for password in ("new-password", "newer-password"):
                self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
                responses.append(
                    self.client.post(
                        "/api/reset-password",
                        json={
                            "email": "alice@example.com",
                            "code": "123456",
                            "password": password,
                        },
                    )
                )

        self.assertEqual(responses[0].status_code, 200)
        self.assertEqual(responses[0].json(), {"ok": True})
        self.assertEqual(responses[1].status_code, 503)
        self.assertEqual(
            responses[1].json(), {"error": "AUTH_SERVICE_UNAVAILABLE"}
        )
        for response in responses:
            cookie = self._cookie(response)
            self.assertEqual(cookie.value, "")
            self.assertEqual(cookie["max-age"], "0")
            self.assertNotIn(
                f"{config.SESSION_COOKIE_NAME}={self.token}",
                response.headers.get("set-cookie", ""),
            )

    def test_reset_revokes_sessions_before_updating_password(self):
        scenarios = (
            ("revoke_failure", True, True, 503, ["revoke"]),
            ("update_failure", False, False, 503, ["revoke", "update"]),
            ("success", False, True, 200, ["revoke", "update"]),
        )
        context = self._context(refresh_cookie=True)

        for name, revoke_fails, update_succeeds, status, expected_order in scenarios:
            events = []

            async def revoke(_user_id):
                events.append("revoke")
                if revoke_fails:
                    raise sessions.SecurityStoreUnavailable("store down")

            async def update(_email, _password):
                events.append("update")
                return update_succeeds

            with self.subTest(name=name), patch.object(
                sessions, "resolve_session", new=AsyncMock(return_value=context)
            ), patch.object(main, "check_rate_limit", new=AsyncMock()), \
                 patch.object(
                     main,
                     "verify_reset_code",
                     new=AsyncMock(return_value=self.raw_user),
                 ), patch.object(main, "revoke_all_user_sessions", new=revoke), \
                 patch.object(main, "update_password", new=update):
                self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
                response = self.client.post(
                    "/api/reset-password",
                    json={
                        "email": "alice@example.com",
                        "code": "123456",
                        "password": "new-password",
                    },
                )

            self.assertEqual(response.status_code, status)
            self.assertEqual(events, expected_order)
            self.assertEqual(self._cookie(response).value, "")

    def test_middleware_refreshes_from_request_local_token(self):
        context = self._context(refresh_cookie=True)
        self.assertFalse(hasattr(context, "token"))
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ) as resolve:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._cookie(response).value, self.token)
        resolve.assert_awaited_once_with(self.token)

    def test_middleware_store_outage_returns_secured_503_not_401(self):
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(
                side_effect=sessions.SecurityStoreUnavailable("store down")
            ),
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "AUTH_SERVICE_UNAVAILABLE"})
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_logout_resolve_store_outage_returns_secured_503_and_clears_cookie(self):
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(
                side_effect=sessions.SecurityStoreUnavailable("store down")
            ),
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "AUTH_SERVICE_UNAVAILABLE"})
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("set-cookie", response.headers)
        cookie_header = response.headers["set-cookie"]
        cookie = self._cookie(response)
        self.assertEqual(cookie.value, "")
        self.assertEqual(cookie["max-age"], "0")
        self.assertNotIn(
            f"{config.SESSION_COOKIE_NAME}={self.token}",
            cookie_header,
        )

    def test_logout_revokes_local_cookie_token_suppresses_refresh_and_clears_cookie(self):
        context = self._context(refresh_cookie=True)
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ), patch.object(
            main,
            "revoke_session",
            new=AsyncMock(),
        ) as revoke:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        revoke.assert_awaited_once_with(self.token)
        cookie_header = response.headers.get("set-cookie", "")
        cookie = self._cookie(response)
        self.assertEqual(cookie.value, "")
        self.assertEqual(cookie["path"], "/")
        self.assertEqual(cookie["max-age"], "0")
        self.assertNotIn(f"{config.SESSION_COOKIE_NAME}={self.token}", cookie_header)

    def test_logout_store_outage_still_clears_cookie_without_refreshing_raw_token(self):
        context = self._context(refresh_cookie=True)
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ), patch.object(
            main,
            "revoke_session",
            new=AsyncMock(
                side_effect=sessions.SecurityStoreUnavailable("store down")
            ),
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "AUTH_SERVICE_UNAVAILABLE"})
        cookie_header = response.headers.get("set-cookie", "")
        self.assertEqual(self._cookie(response).value, "")
        self.assertNotIn(f"{config.SESSION_COOKIE_NAME}={self.token}", cookie_header)

    def test_home_redirects_anonymous_users_and_renders_for_valid_session(self):
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=None),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()):
            anonymous = self.client.get("/", follow_redirects=False)

        context = self._context()
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=context),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            authenticated = self.client.get("/", follow_redirects=False)

        self.assertEqual(anonymous.status_code, 303)
        self.assertEqual(anonymous.headers["location"], "/login")
        self.assertEqual(authenticated.status_code, 200)
        self.assertIn("/static/app.js", authenticated.text)


class FrontendSessionTests(unittest.TestCase):
    IDENTITY_KEYS = (
        "RE_LIFE_CURRENT_USER",
        "RE_LIFE_CURRENT_USER_ID",
        "RE_LIFE_CURRENT_USER_KEY",
        "RE_LIFE_USER_AVATAR",
    )

    @classmethod
    def setUpClass(cls):
        cls.supabase_js = Path("static/supabase.js").read_text(encoding="utf-8")
        cls.app_js = Path("static/app.js").read_text(encoding="utf-8")
        cls.login_html = Path("templates/login.html").read_text(encoding="utf-8")
        cls.register_html = Path("templates/register.html").read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _between(source, start, end):
        start_index = source.index(start)
        end_index = source.index(end, start_index)
        return source[start_index:end_index]

    def _run_supabase_node_scenario(self, scenario):
        harness = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("static/supabase.js", "utf8");
const aliceServerUser = {
    id: 42,
    public_id: "user-a",
    display_name: "Alice",
    email: "alice@example.com",
    photo_url: null,
    spent_points: 3,
    earned_points: 8,
    claimed_coupons: [],
    email_verified: true,
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-02T00:00:00+00:00",
};
const bobServerUser = {
    id: 84,
    public_id: "user-b",
    display_name: "Bob",
    email: "bob@example.com",
    photo_url: null,
    spent_points: 5,
    earned_points: 13,
    claimed_coupons: [],
    email_verified: true,
    created_at: "2026-02-01T00:00:00+00:00",
    updated_at: "2026-02-02T00:00:00+00:00",
};
function jsonResponse(status, payload) {
    return {
        ok: status >= 200 && status < 300,
        status,
        async text() { return JSON.stringify(payload); },
    };
}
let fetchImpl;
const window = { location: { origin: "https://app.example.test" } };
const navigator = {};
const context = vm.createContext({
    window,
    navigator,
    URL,
    URLSearchParams,
    Blob,
    FormData,
    Uint8Array,
    atob,
    console,
    fetch: (...args) => fetchImpl(...args),
});
vm.runInContext(source, context, { filename: "static/supabase.js" });
const FB = window.FB;
"""
        completed = subprocess.run(
            ["node", "-e", harness + scenario],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(
                "Node frontend scenario failed:\n"
                f"STDOUT:\n{completed.stdout}\n"
                f"STDERR:\n{completed.stderr}"
            )

    def test_json_and_form_requests_send_same_origin_credentials(self):
        request_json = self._between(
            self.supabase_js,
            "async function requestJson",
            "async function requestFormJson",
        )
        request_form = self._between(
            self.supabase_js,
            "async function requestFormJson",
            "function stringifyErrorValue",
        )

        self.assertIn('credentials: "same-origin"', request_json)
        self.assertIn('credentials: "same-origin"', request_form)

    def test_frontend_auth_api_restores_and_clears_server_session_user(self):
        self.assertIn("let currentSessionUser = null;", self.supabase_js)
        self.assertIn("let authOperationGeneration = 0;", self.supabase_js)
        self.assertIn('const AUTH_COOKIE_LOCK_NAME = "re-life-auth-cookie";', self.supabase_js)
        self.assertRegex(
            self.supabase_js,
            r"async getCurrentUser\(\)\s*\{\s*"
            r"const operationGeneration = beginAuthOperation\(\);\s*"
            r"let data;\s*try\s*\{\s*"
            r'data = await requestJson\("/api/users/me"\);\s*'
            r"\}\s*catch \(error\)\s*\{\s*"
            r"ensureCurrentAuthOperation\(operationGeneration\);\s*"
            r"throw error;\s*\}\s*"
            r"const normalizedUser = normalizeUser\(data\);\s*"
            r"ensureCurrentAuthOperation\(operationGeneration\);\s*"
            r"currentSessionUser = normalizedUser;\s*"
            r"return currentSessionUser;\s*\}",
        )
        self.assertRegex(
            self.supabase_js,
            r"async logout\(\)\s*\{\s*"
            r"return runSerializedAuthMutation\(async \(\) => \{\s*"
            r"const operationGeneration = beginAuthOperation\(\);\s*"
            r"try\s*\{\s*"
            r'await requestJson\("/api/auth/logout",\s*\{\s*'
            r'method:\s*"POST",?\s*\}\);\s*'
            r"\}\s*finally\s*\{\s*"
            r"if \(operationGeneration === authOperationGeneration\)\s*\{\s*"
            r"currentSessionUser = null;\s*\}\s*\}\s*\}\);\s*\}",
        )
        self.assertRegex(
            self.supabase_js,
            r"async loginUser\(displayName, password\)\s*\{\s*"
            r"return runSerializedAuthMutation\(async \(\) => \{\s*"
            r"const operationGeneration = beginAuthOperation\(\);\s*"
            r"let data;\s*try\s*\{\s*"
            r'data = await requestJson\("/api/auth/login",[\s\S]*?'
            r"\}\s*catch \(error\)\s*\{\s*"
            r"ensureCurrentAuthOperation\(operationGeneration\);\s*"
            r"throw error;\s*\}\s*"
            r"const normalizedUser = normalizeUser\(data\.user\);\s*"
            r"ensureCurrentAuthOperation\(operationGeneration\);\s*"
            r"currentSessionUser = normalizedUser;\s*"
            r"return currentSessionUser;",
        )

    def test_record_identity_helpers_are_removed_and_session_assignment_is_controlled(self):
        self.assertNotIn("localStorage", self.supabase_js)
        self.assertNotIn("function fallbackUserId", self.supabase_js)
        self.assertNotIn("function fallbackUserName", self.supabase_js)

        assignments = re.findall(r"currentSessionUser\s*=\s*([^;]+);", self.supabase_js)
        self.assertEqual(assignments.count("normalizedUser"), 2)
        self.assertTrue(
            all(value in {"null", "normalizedUser"} for value in assignments),
            assignments,
        )

    def test_failed_me_clears_cached_identity_before_record_fallback(self):
        self._run_supabase_node_scenario(
            r"""
(async () => {
    let meCalls = 0;
    const requestUrls = [];
    fetchImpl = async (url) => {
        const parsed = new URL(String(url));
        requestUrls.push(parsed);
        if (parsed.pathname === "/api/users/me") {
            meCalls += 1;
            if (meCalls === 1) {
                return jsonResponse(200, aliceServerUser);
            }
            return jsonResponse(401, { detail: "AUTHENTICATION_REQUIRED" });
        }
        if (parsed.pathname === "/api/records") {
            return jsonResponse(200, { ok: true });
        }
        throw new Error(`Unexpected request: ${parsed}`);
    };

    const alice = await FB.getCurrentUser();
    assert.equal(alice.displayName, "Alice");
    await assert.rejects(FB.getCurrentUser(), error => error.status === 401);
    await FB.getItems("999", "Bob", "usr_bob");
    await FB.clearAllItems("999", "Bob", "usr_bob");

    const recordsUrls = requestUrls.filter(url => url.pathname === "/api/records");
    assert.equal(recordsUrls.length, 2);
    assert.ok(
        recordsUrls.every(url => url.search === ""),
        `client identity reached records query: ${recordsUrls}`,
    );
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
"""
        )

    def test_logout_invalidates_deferred_me_response_and_record_fallback(self):
        self._run_supabase_node_scenario(
            r"""
(async () => {
    let resolveMe;
    const requestUrls = [];
    fetchImpl = async (url) => {
        const parsed = new URL(String(url));
        requestUrls.push(parsed);
        if (parsed.pathname === "/api/users/me") {
            return new Promise(resolve => { resolveMe = resolve; });
        }
        if (parsed.pathname === "/api/auth/logout") {
            return jsonResponse(200, { ok: true });
        }
        if (parsed.pathname === "/api/records") {
            return jsonResponse(200, { ok: true });
        }
        throw new Error(`Unexpected request: ${parsed}`);
    };

    const pendingMe = FB.getCurrentUser();
    await FB.logout();
    resolveMe(jsonResponse(200, aliceServerUser));

    let staleOutcome;
    try {
        staleOutcome = await pendingMe;
    } catch (error) {
        staleOutcome = error;
    }
    await FB.clearAllItems();
    const recordsUrl = requestUrls.find(url => url.pathname === "/api/records");

    assert.equal(
        staleOutcome?.message,
        "AUTH_STATE_CHANGED",
        `stale /me returned ${JSON.stringify(staleOutcome)}; records query: ${recordsUrl}`,
    );
    assert.equal(
        recordsUrl.search,
        "",
        `stale records query after logout: ${recordsUrl}`,
    );
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
"""
        )

    def test_stale_me_failure_becomes_auth_state_changed_and_keeps_newer_login(self):
        self._run_supabase_node_scenario(
            r"""
(async () => {
    let resolveMe;
    const requestUrls = [];
    fetchImpl = async (url) => {
        const parsed = new URL(String(url));
        requestUrls.push(parsed);
        if (parsed.pathname === "/api/users/me") {
            return new Promise(resolve => { resolveMe = resolve; });
        }
        if (parsed.pathname === "/api/auth/login") {
            return jsonResponse(200, { ok: true, user: bobServerUser });
        }
        if (parsed.pathname === "/api/records") {
            return jsonResponse(200, { ok: true });
        }
        throw new Error(`Unexpected request: ${parsed}`);
    };

    const pendingMe = FB.getCurrentUser();
    const bob = await FB.loginUser("Bob", "correct-pass");
    assert.equal(bob.displayName, "Bob");
    resolveMe(jsonResponse(401, { detail: "AUTHENTICATION_REQUIRED" }));

    let staleError;
    try {
        await pendingMe;
    } catch (error) {
        staleError = error;
    }
    await FB.clearAllItems();
    const recordsUrl = requestUrls.find(url => url.pathname === "/api/records");

    assert.equal(staleError?.code, "AUTH_STATE_CHANGED");
    assert.notEqual(staleError?.status, 401, "stale 401 must not redirect the caller");
    assert.equal(recordsUrl.search, "");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
"""
        )

    def test_logout_request_finishes_before_newer_login_starts(self):
        self._run_supabase_node_scenario(
            r"""
(async () => {
    let resolveLogout;
    let loginStarted = false;
    const requestUrls = [];
    fetchImpl = async (url) => {
        const parsed = new URL(String(url));
        requestUrls.push(parsed);
        if (parsed.pathname === "/api/auth/logout") {
            return new Promise(resolve => { resolveLogout = resolve; });
        }
        if (parsed.pathname === "/api/auth/login") {
            loginStarted = true;
            return jsonResponse(200, { ok: true, user: bobServerUser });
        }
        if (parsed.pathname === "/api/records") {
            return jsonResponse(200, { ok: true });
        }
        throw new Error(`Unexpected request: ${parsed}`);
    };

    const pendingLogout = FB.logout();
    const pendingLogin = FB.loginUser("Bob", "correct-pass");
    await Promise.resolve();
    await Promise.resolve();
    assert.equal(loginStarted, false, "login request started before logout completed");

    resolveLogout(jsonResponse(200, { ok: true }));
    await pendingLogout;
    const bob = await pendingLogin;
    assert.equal(bob.displayName, "Bob");
    await FB.clearAllItems();

    const recordsUrl = requestUrls.find(url => url.pathname === "/api/records");
    assert.equal(recordsUrl.search, "");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
"""
        )

    def test_cookie_mutations_prefer_fixed_same_origin_web_lock(self):
        self._run_supabase_node_scenario(
            r"""
(async () => {
    const lockNames = [];
    navigator.locks = {
        async request(name, callback) {
            lockNames.push(name);
            return callback();
        },
    };
    fetchImpl = async (url) => {
        const parsed = new URL(String(url));
        if (parsed.pathname === "/api/auth/login") {
            return jsonResponse(200, { ok: true, user: bobServerUser });
        }
        if (parsed.pathname === "/api/auth/logout") {
            return jsonResponse(200, { ok: true });
        }
        throw new Error(`Unexpected request: ${parsed}`);
    };

    await FB.loginUser("Bob", "correct-pass");
    await FB.logout();
    assert.deepEqual(
        lockNames,
        ["re-life-auth-cookie", "re-life-auth-cookie"],
    );
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
"""
        )

    def test_app_initializes_identity_only_from_auth_me(self):
        for helper in (
            "function readSessionState",
            "function persistSessionState",
            "function clearSessionState",
        ):
            self.assertNotIn(helper, self.app_js)

        dom_ready = self._between(
            self.app_js,
            "document.addEventListener('DOMContentLoaded'",
            "let cameraAvailable",
        )
        self.assertNotIn("RE_LIFE_CURRENT_USER", dom_ready)
        self.assertIn("const accountReady = await initAccounts();", dom_ready)
        self.assertIn("if (!accountReady) return;", dom_ready)

        init_accounts = self._between(
            self.app_js,
            "async function initAccounts",
            "function updateHeaderUI",
        )
        self.assertIn("await waitForFB();", init_accounts)
        self.assertIn("const user = await FB.getCurrentUser();", init_accounts)
        self.assertNotIn("getUserById", init_accounts)
        self.assertNotIn("getUserByName", init_accounts)

    def test_auth_failures_stop_records_and_fail_closed(self):
        dom_ready = self._between(
            self.app_js,
            "document.addEventListener('DOMContentLoaded'",
            "let cameraAvailable",
        )
        self.assertLess(
            dom_ready.index("if (!accountReady) return;"),
            dom_ready.index("await loadRecords();"),
        )

        init_accounts = self._between(
            self.app_js,
            "async function initAccounts",
            "function updateHeaderUI",
        )
        self.assertRegex(
            init_accounts,
            r"catch \(error\)\s*\{\s*"
            r"if \(error\.status === 401\)\s*\{\s*"
            r"window\.location\.replace\('/login'\);\s*"
            r"return false;\s*\}\s*throw error;\s*\}",
        )

    def test_all_in_memory_identity_state_comes_from_server_user(self):
        init_accounts = self._between(
            self.app_js,
            "async function initAccounts",
            "function updateHeaderUI",
        )
        expected_assignments = (
            "state.currentUser = user.displayName || null;",
            "state.userId = user.id ?? null;",
            "state.userKey = user._key || user.public_id || user.userId || null;",
            "state.spentPoints = user.spent_points ?? user.spentPoints ?? 0;",
            "state.earnedPoints = user.earned_points ?? user.earnedPoints ?? 0;",
            "state.claimedCoupons = user.claimed_coupons || user.claimedCoupons || [];",
            "state.userAvatar = user.photoUrl || user.photo_url || '👤';",
        )
        for assignment in expected_assignments:
            self.assertIn(assignment, init_accounts)
        self.assertIn("updateHeaderUI();", init_accounts)
        self.assertIn("return true;", init_accounts)

    def test_logout_always_resets_memory_and_redirects(self):
        logout_flow = self._between(
            self.app_js,
            "async function logoutToLogin",
            "function handleLogout",
        )
        self.assertIn("await FB.logout();", logout_flow)
        self.assertIn("catch (error)", logout_flow)
        self.assertIn("console.warn", logout_flow)
        self.assertRegex(
            logout_flow,
            r"finally\s*\{\s*resetSessionState\(\);\s*"
            r"window\.location\.replace\('/login'\);\s*\}",
        )

        logout_handlers = self._between(
            self.app_js,
            "function handleLogout",
            "async function saveUserData",
        )
        self.assertGreaterEqual(logout_handlers.count("logoutToLogin();"), 2)
        reset_session = self._between(
            self.app_js,
            "function resetSessionState",
            "async function logoutToLogin",
        )
        self.assertNotIn("localStorage", reset_session)
        self.assertNotIn("clearSessionState", reset_session)

    def test_auth_templates_do_not_persist_identity_and_redirect_correctly(self):
        for key in self.IDENTITY_KEYS:
            self.assertNotIn(key, self.login_html)
            self.assertNotIn(key, self.register_html)

        self.assertIn("await window.FB.loginUser(username, password);", self.login_html)
        self.assertIn("window.location.replace('/');", self.login_html)
        self.assertIn(
            "await window.FB.createUser(pendingUsername, pendingPassword, pendingEmail, code);",
            self.register_html,
        )
        self.assertIn("window.location.replace('/login');", self.register_html)

    def test_registration_submits_verification_code_in_one_request(self):
        create_user = self._between(
            self.supabase_js,
            "async createUser",
            "async loginUser",
        )
        self.assertIn(
            "async createUser(displayName, password, email = null, code)",
            create_user,
        )
        self.assertIn("code,", create_user)
        self.assertNotIn("runSerializedAuthMutation", create_user)
        self.assertNotIn("currentSessionUser", create_user)
        self.assertNotIn("/api/verify-code", self.register_html)
        self.assertIn("const errorCode = err.payload?.error;", self.register_html)

    def test_login_template_uses_one_generic_credential_error(self):
        login_flow = self._between(
            self.login_html,
            "async function handleLogin",
            "// ── Forgot Password Flow",
        )
        self.assertIn("const errorCode = err.payload?.error;", login_flow)
        self.assertIn("INVALID_CREDENTIALS", login_flow)
        self.assertNotIn("USER_NOT_FOUND", login_flow)
        self.assertNotIn("WRONG_PASSWORD", login_flow)

    def test_identity_storage_keys_are_removed_without_removing_preferences(self):
        for source in (self.app_js, self.supabase_js):
            for key in self.IDENTITY_KEYS:
                self.assertNotIn(key, source)

        self.assertIn("RE_LIFE_LANG", self.app_js)
        self.assertIn("RE_LIFE_THEME", self.app_js)
        self.assertIn("RE_LIFE_LANG", self.login_html)
        self.assertIn("RE_LIFE_LANG", self.register_html)


if __name__ == "__main__":
    unittest.main()
