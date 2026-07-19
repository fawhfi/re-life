import asyncio
import hashlib
import hmac
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import auth
import config


class AuthCodeSecurityRedTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        auth._pending_verifications.clear()

    async def asyncTearDown(self):
        auth._pending_verifications.clear()

    async def test_code_digest_uses_dedicated_hmac_secret(self):
        payload = b"verify:user@example.com:123456"
        with patch.object(auth, "AUTH_CODE_SECRET", "dedicated-secret-a"):
            first = auth._code_digest("verify", " User@Example.COM ", "123456")
        with patch.object(auth, "AUTH_CODE_SECRET", "dedicated-secret-b"):
            second = auth._code_digest("verify", "user@example.com", "123456")

        self.assertEqual(
            first,
            hmac.new(b"dedicated-secret-a", payload, hashlib.sha256).hexdigest(),
        )
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, hashlib.sha256(payload).hexdigest())

    async def test_generate_code_uses_secrets_randbelow_boundaries(self):
        with patch.object(auth.secrets, "randbelow", side_effect=(0, 899_999)) as randbelow:
            self.assertEqual(auth._generate_code(), "100000")
            self.assertEqual(auth._generate_code(), "999999")

        self.assertEqual(randbelow.call_args_list[0].args, (900_000,))
        self.assertEqual(randbelow.call_args_list[1].args, (900_000,))

    async def test_production_rejects_short_or_reused_auth_code_secret(self):
        common = {
            "IS_PRODUCTION": True,
            "RESEND_API_KEY": "re_test_key",
            "RESEND_FROM": "Re-Life <noreply@re-life.test>",
            "SUPABASE_SECRET_KEY": "supabase-secret",
            "SUPABASE_SERVICE_ROLE_KEY": "supabase-secret",
            "SUPABASE_ANON_KEY": "supabase-anon",
            "SUPABASE_PUBLISHABLE_KEY": "supabase-publishable",
        }
        with patch.multiple(
            config,
            **common,
            AUTH_CODE_SECRET="too-short",
            SESSION_METADATA_HASH_KEY="session-secret",
        ):
            with self.assertRaisesRegex(RuntimeError, "AUTH_CODE_SECRET"):
                config.validate_auth_security_settings()

        shared = "shared-secret-" + ("x" * 32)
        for reused_setting in (
            "SESSION_METADATA_HASH_KEY",
            "SUPABASE_SECRET_KEY",
        ):
            values = {
                **common,
                "AUTH_CODE_SECRET": shared,
                "SESSION_METADATA_HASH_KEY": "session-secret",
                reused_setting: shared,
            }
            if reused_setting == "SUPABASE_SECRET_KEY":
                values["SUPABASE_SERVICE_ROLE_KEY"] = shared
            with self.subTest(reused_setting=reused_setting), patch.multiple(
                config, **values
            ):
                with self.assertRaisesRegex(RuntimeError, "independent"):
                    config.validate_auth_security_settings()

    async def test_fifth_wrong_memory_attempt_consumes_code(self):
        with patch.object(auth, "supabase_enabled", return_value=False), \
             patch.object(auth, "AUTH_CODE_SECRET", "test-secret"), \
             patch.object(auth, "AUTH_CODE_MAX_ATTEMPTS", 5):
            await auth._store_code_row("verify", "user@example.com", "123456")
            row = auth._memory_get_code("verify", "user@example.com")

            for attempt in range(1, 5):
                self.assertFalse(
                    await auth.consume_code("verify", "user@example.com", "000000")
                )
                self.assertEqual(row["attempts"], attempt)
                self.assertIsNone(row["consumed_at"])

            self.assertFalse(
                await auth.consume_code("verify", "user@example.com", "000000")
            )

        self.assertEqual(row["attempts"], 5)
        self.assertIsNotNone(row["consumed_at"])

    async def test_valid_consume_is_once_and_zero_row_cas_fails(self):
        row = {
            "id": 91,
            "purpose": "verify",
            "email": "user@example.com",
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
            "attempts": 0,
            "consumed_at": None,
        }
        with patch.object(auth, "AUTH_CODE_SECRET", "test-secret"):
            row["code_hash"] = auth._code_digest(
                "verify", "user@example.com", "123456"
            )

        updated = {**row, "attempts": 1, "consumed_at": "now"}
        with patch.object(auth, "supabase_enabled", return_value=True), \
             patch.object(auth, "AUTH_CODE_SECRET", "test-secret"), \
             patch.object(auth, "AUTH_CODE_MAX_ATTEMPTS", 5), \
             patch.object(
                 auth, "supabase_select_one", new=AsyncMock(return_value=row)
             ), patch.object(
                 auth,
                 "supabase_update",
                 new=AsyncMock(side_effect=([updated], [])),
             ) as update:
            self.assertTrue(
                await auth.consume_code("verify", "user@example.com", "123456")
            )
            self.assertFalse(
                await auth.consume_code("verify", "user@example.com", "123456")
            )

        self.assertEqual(update.await_count, 2)
        for call in update.call_args_list:
            self.assertEqual(call.kwargs["filters"], {"id": 91, "attempts": 0})
            self.assertIs(call.kwargs["returning"], True)
            self.assertEqual(call.args[1]["attempts"], 1)
            self.assertIsNotNone(call.args[1]["consumed_at"])

    async def test_memory_rows_have_unique_ids_and_resend_invalidates_old_code(self):
        with patch.object(auth, "supabase_enabled", return_value=False), \
             patch.object(auth, "AUTH_CODE_SECRET", "test-secret"):
            first = await auth._store_code_row(
                "verify", "user@example.com", "123456"
            )
            second = await auth._store_code_row(
                "verify", "user@example.com", "654321"
            )

            self.assertNotEqual(first["id"], second["id"])
            self.assertNotIn("code", second)
            self.assertFalse(
                await auth.consume_code("verify", "user@example.com", "123456")
            )
            self.assertTrue(
                await auth.consume_code("verify", "user@example.com", "654321")
            )
            self.assertFalse(
                await auth.consume_code("verify", "user@example.com", "654321")
            )

    async def test_failed_older_delivery_does_not_delete_newer_code(self):
        older_started = asyncio.Event()
        release_older = asyncio.Event()

        async def interleaved_delivery(_email, _subject, _intro, code):
            if code == "111111":
                older_started.set()
                await release_older.wait()
                raise auth.EmailDeliveryUnavailable("older delivery failed")
            return True

        with patch.object(auth, "supabase_enabled", return_value=False), \
             patch.object(auth, "IS_DEVELOPMENT", False), \
             patch.object(auth, "ALLOW_DEV_AUTH_CODES", False), \
             patch.object(
                 auth, "_generate_code", side_effect=("111111", "222222")
             ), patch.object(auth, "_send_code_email", new=interleaved_delivery):
            older = asyncio.create_task(
                auth.send_verification_code("user@example.com")
            )
            await older_started.wait()
            newer_result = await auth.send_verification_code("user@example.com")
            release_older.set()
            with self.assertRaises(auth.EmailDeliveryUnavailable):
                await older

            self.assertIsNone(newer_result)
            self.assertTrue(
                await auth.consume_code("verify", "user@example.com", "222222")
            )

    async def test_reset_delivery_is_uniform_and_unknown_code_cannot_bind_later(self):
        known_email = "known@example.com"
        unknown_email = "unknown@example.com"
        delivered = []

        async def capture_delivery(email, subject, intro, code):
            delivered.append((email, subject, intro, code))
            return True

        known_user = {
            "id": 7,
            "public_id": "usr_known",
            "display_name": "Known",
            "email": known_email,
            "password_hash": "known-hash",
            "email_verified": True,
        }
        later_user = {
            "id": 8,
            "public_id": "usr_later",
            "display_name": "Later",
            "email": unknown_email,
            "password_hash": "later-hash",
            "email_verified": True,
        }

        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()
        try:
            auth._memory_store_user(known_user)
            with patch.object(auth, "supabase_enabled", return_value=False), \
                 patch.object(
                     auth, "_generate_code", side_effect=("333333", "444444")
                 ), patch.object(auth, "_send_code_email", new=capture_delivery):
                results = (
                    await auth.send_reset_code(known_email),
                    await auth.send_reset_code(unknown_email),
                )

                known_row = auth._memory_get_code("reset", known_email)
                unknown_row = auth._memory_get_code("reset", unknown_email)
                self.assertEqual(results, (None, None))
                self.assertEqual(known_row["user_id"], 7)
                self.assertIsNone(unknown_row["user_id"])
                self.assertEqual(len(delivered), 2)
                self.assertEqual(delivered[0][1:3], delivered[1][1:3])
                self.assertIn("If this email is registered", delivered[0][2])

                auth._memory_store_user(later_user)
                self.assertIsNone(
                    await auth.verify_reset_code(unknown_email, "444444")
                )
                self.assertFalse(
                    await auth.consume_code("reset", unknown_email, "444444")
                )
        finally:
            auth._memory_users_by_id.clear()
            auth._memory_users_by_public_id.clear()

    async def test_unknown_purpose_and_malformed_rows_fail_closed(self):
        fetch = AsyncMock()
        with patch.object(auth, "_fetch_code_row", new=fetch):
            self.assertFalse(
                await auth.consume_code("login", "user@example.com", "123456")
            )
        fetch.assert_not_awaited()

        base = {
            "id": "memory-row",
            "purpose": "verify",
            "email": "user@example.com",
            "code_hash": auth._code_digest(
                "verify", "user@example.com", "123456"
            ),
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
            "attempts": 0,
            "consumed_at": None,
        }
        malformed_rows = (
            {**base, "expires_at": "not-a-date"},
            {
                **base,
                "expires_at": (
                    datetime.now(timezone.utc) - timedelta(seconds=1)
                ).isoformat(),
            },
            {**base, "consumed_at": "already-consumed"},
            {**base, "attempts": "zero"},
        )
        with patch.object(
            auth, "_fetch_code_row", new=AsyncMock(side_effect=malformed_rows)
        ), patch.object(auth, "supabase_enabled", return_value=False):
            for _row in malformed_rows:
                self.assertFalse(
                    await auth.consume_code(
                        "verify", "user@example.com", "123456"
                    )
                )

    async def test_supabase_outage_does_not_fallback_to_memory_code(self):
        with patch.object(auth, "AUTH_CODE_SECRET", "test-secret"):
            memory_row = auth._memory_store_code(
                "verify", "user@example.com", "123456"
            )

        with patch.object(auth, "supabase_enabled", return_value=True), \
             patch.object(
                 auth,
                 "supabase_select_one",
                 new=AsyncMock(side_effect=RuntimeError("database unavailable")),
             ):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                await auth.consume_code(
                    "verify", "user@example.com", "123456"
                )

        self.assertIsNone(memory_row["consumed_at"])

    async def test_verify_helpers_share_consume_and_reset_returns_safe_user(self):
        safe_user = {
            "id": 7,
            "email": "user@example.com",
            "displayName": "User",
        }
        consume = AsyncMock(side_effect=(True, True, False))
        fetch_reset = AsyncMock(
            side_effect=({"user_id": 7}, {"user_id": 7})
        )
        get_user = AsyncMock(return_value=safe_user)
        with patch.object(auth, "consume_code", new=consume), patch.object(
            auth, "_fetch_code_row", new=fetch_reset
        ), patch.object(auth, "get_user_by_internal_id", new=get_user):
            self.assertTrue(
                await auth.verify_code(" User@Example.COM ", " 123456 ")
            )
            self.assertEqual(
                await auth.verify_reset_code(
                    " User@Example.COM ", " 654321 "
                ),
                safe_user,
            )
            self.assertIsNone(
                await auth.verify_reset_code("user@example.com", "000000")
            )

        self.assertEqual(
            [call.args for call in consume.await_args_list],
            [
                ("verify", "user@example.com", "123456"),
                ("reset", "user@example.com", "654321"),
                ("reset", "user@example.com", "000000"),
            ],
        )
        get_user.assert_awaited_once_with(7)

    async def test_schema_caps_attempts_and_indexes_active_codes(self):
        schema = (
            Path(__file__).resolve().parents[1] / "supabase_schema.sql"
        ).read_text(encoding="utf-8").lower()
        compact_schema = " ".join(schema.split())
        drop_constraint = (
            "drop constraint if exists auth_codes_attempts_check;"
        )
        normalize_legacy = (
            "update public.auth_codes set attempts = 5, "
            "consumed_at = coalesce(consumed_at, now()) where attempts > 5;"
        )
        add_constraint = "add constraint auth_codes_attempts_check"

        self.assertIn("check (attempts between 0 and 5)", schema)
        self.assertIn(normalize_legacy, compact_schema)
        self.assertLess(
            compact_schema.index(drop_constraint),
            compact_schema.index(normalize_legacy),
        )
        self.assertLess(
            compact_schema.index(normalize_legacy),
            compact_schema.index(add_constraint),
        )
        self.assertIn("auth_codes_active_lookup_idx", schema)
        self.assertIn("where consumed_at is null", schema)


class VerifiedRegistrationAndLoginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        auth._pending_verifications.clear()
        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()

    async def asyncTearDown(self):
        auth._pending_verifications.clear()
        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()

    @staticmethod
    def _user_row(password_hash="stored-password-hash"):
        return {
            "id": 42,
            "public_id": "usr_alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password_hash": password_hash,
            "photo_url": None,
            "spent_points": 0,
            "earned_points": 0,
            "claimed_coupons": [],
            "email_verified": True,
        }

    async def test_create_user_cannot_be_called_without_verification_code(self):
        with self.assertRaises(TypeError):
            await auth.create_user(
                "Alice",
                "correct-horse-battery-staple",
                "alice@example.com",
            )

    async def test_create_user_checks_duplicates_before_consuming_code(self):
        consume = AsyncMock(return_value=True)
        with patch.object(
            auth,
            "get_user_by_name",
            new=AsyncMock(return_value=self._user_row()),
        ), patch.object(
            auth,
            "get_user_by_email",
            new=AsyncMock(return_value=None),
        ), patch.object(auth, "consume_code", new=consume):
            with self.assertRaisesRegex(ValueError, "USERNAME_TAKEN"):
                await auth.create_user(
                    "Alice",
                    "correct-horse-battery-staple",
                    "alice@example.com",
                    verification_code="123456",
                )

        consume.assert_not_awaited()

    async def test_create_user_consumes_code_before_memory_insert(self):
        hasher = MagicMock()
        hasher.hash.return_value = "new-password-hash"
        consume = AsyncMock(return_value=True)
        with patch.object(auth, "supabase_enabled", return_value=False), patch.object(
            auth, "get_user_by_name", new=AsyncMock(return_value=None)
        ), patch.object(
            auth, "get_user_by_email", new=AsyncMock(return_value=None)
        ), patch.object(auth, "consume_code", new=consume), patch.object(
            auth, "PASSWORD_HASHER", hasher
        ):
            user = await auth.create_user(
                "  Alice  ",
                "correct-horse-battery-staple",
                " Alice@Example.COM ",
                verification_code="123456",
            )

        consume.assert_awaited_once_with(
            "verify", "alice@example.com", "123456"
        )
        self.assertEqual(user["display_name"], "Alice")
        self.assertEqual(user["email"], "alice@example.com")
        self.assertTrue(user["emailVerified"])
        self.assertEqual(
            auth._memory_users_by_id[user["id"]]["password_hash"],
            "new-password-hash",
        )

    async def test_create_user_rejects_invalid_or_reused_code_without_insert(self):
        consume = AsyncMock(return_value=False)
        with patch.object(auth, "supabase_enabled", return_value=False), patch.object(
            auth, "get_user_by_name", new=AsyncMock(return_value=None)
        ), patch.object(
            auth, "get_user_by_email", new=AsyncMock(return_value=None)
        ), patch.object(auth, "consume_code", new=consume):
            with self.assertRaisesRegex(ValueError, "INVALID_OR_EXPIRED_CODE"):
                await auth.create_user(
                    "Alice",
                    "correct-horse-battery-staple",
                    "alice@example.com",
                    verification_code="123456",
                )

        self.assertEqual(auth._memory_users_by_id, {})

    async def test_supabase_registration_empty_insert_fails_closed(self):
        hasher = MagicMock()
        hasher.hash.return_value = "new-password-hash"
        with patch.object(auth, "supabase_enabled", return_value=True), patch.object(
            auth, "get_user_by_name", new=AsyncMock(return_value=None)
        ), patch.object(
            auth, "get_user_by_email", new=AsyncMock(return_value=None)
        ), patch.object(
            auth, "consume_code", new=AsyncMock(return_value=True)
        ), patch.object(
            auth, "supabase_insert", new=AsyncMock(return_value=[])
        ), patch.object(auth, "PASSWORD_HASHER", hasher):
            with self.assertRaisesRegex(RuntimeError, "CREATE_USER_FAILED"):
                await auth.create_user(
                    "Alice",
                    "correct-horse-battery-staple",
                    "alice@example.com",
                    verification_code="123456",
                )

    async def test_unknown_and_wrong_password_use_one_lookup_and_same_error(self):
        for row in (None, self._user_row()):
            lookup = AsyncMock(return_value=row)
            hasher = MagicMock()
            hasher.verify.side_effect = auth.VerifyMismatchError()
            with self.subTest(row_exists=row is not None), patch.object(
                auth, "supabase_enabled", return_value=True
            ), patch.object(
                auth, "supabase_select_one", new=lookup
            ), patch.object(auth, "PASSWORD_HASHER", hasher):
                with self.assertRaisesRegex(ValueError, "INVALID_CREDENTIALS"):
                    await auth.login_user(" Alice ", "wrong-password")

            lookup.assert_awaited_once_with(
                "app_users", filters={"display_name": "Alice"}
            )
            hasher.verify.assert_called_once()
            if row is None:
                self.assertEqual(
                    hasher.verify.call_args.args[0], auth.DUMMY_PASSWORD_HASH
                )

    async def test_malformed_password_hash_is_uniform_invalid_credentials(self):
        auth._memory_store_user(self._user_row(password_hash="not-an-argon-hash"))
        with patch.object(auth, "supabase_enabled", return_value=False):
            with self.assertRaisesRegex(ValueError, "INVALID_CREDENTIALS"):
                await auth.login_user("Alice", "wrong-password")

    async def test_supabase_login_rehashes_by_internal_id_and_fails_on_zero_rows(self):
        row = self._user_row()
        hasher = MagicMock()
        hasher.verify.return_value = True
        hasher.check_needs_rehash.return_value = True
        hasher.hash.return_value = "fresh-password-hash"

        for updated_rows, should_fail in (([{**row, "password_hash": "fresh-password-hash"}], False), ([], True)):
            update = AsyncMock(return_value=updated_rows)
            with self.subTest(should_fail=should_fail), patch.object(
                auth, "supabase_enabled", return_value=True
            ), patch.object(
                auth, "supabase_select_one", new=AsyncMock(return_value=row)
            ), patch.object(
                auth, "supabase_update", new=update
            ), patch.object(auth, "PASSWORD_HASHER", hasher):
                if should_fail:
                    with self.assertRaisesRegex(RuntimeError, "PASSWORD_REHASH_FAILED"):
                        await auth.login_user("Alice", "correct-password")
                else:
                    user = await auth.login_user("Alice", "correct-password")
                    self.assertEqual(user["id"], 42)

            update.assert_awaited_once_with(
                "app_users",
                {"password_hash": "fresh-password-hash"},
                filters={"id": 42},
                returning=True,
            )

    async def test_memory_login_rehashes_the_original_row(self):
        row = self._user_row()
        auth._memory_store_user(row)
        hasher = MagicMock()
        hasher.verify.return_value = True
        hasher.check_needs_rehash.return_value = True
        hasher.hash.return_value = "fresh-password-hash"

        with patch.object(auth, "supabase_enabled", return_value=False), patch.object(
            auth, "PASSWORD_HASHER", hasher
        ):
            user = await auth.login_user("Alice", "correct-password")

        self.assertEqual(user["id"], 42)
        self.assertEqual(row["password_hash"], "fresh-password-hash")
        self.assertIn("updated_at", row)


if __name__ == "__main__":
    unittest.main()
