from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

import auth
import config
import main
import sessions


INT_MAX = 2_147_483_647
PHOTO_URL_MAX_LENGTH = 1_000_000
SAFE_USER_COLUMNS = (
    "id,public_id,display_name,email,photo_url,spent_points,earned_points,"
    "claimed_coupons,email_verified,created_at,updated_at"
)
MALFORMED_HTTPS_AVATARS = (
    "https://[",
    "https://[::::]",
    "https://example.com：80/avatar.png",
    "https://example.com:bad/avatar.png",
)


def _valid_coupon(index: int = 0) -> dict:
    return {
        "id": f"reward-{index}",
        "title": f"Reward {index}",
        "provider": "Green Provider",
        "cost": 100 + index,
        "image": "🎫",
        "category": "Voucher",
        "description": "A valid existing reward coupon.",
        "code": f"WELCOME-{index}",
        "claimedDate": "Just now",
        "expiry": "Valid 30 days",
    }


def _invalid_account_updates() -> tuple[tuple[str, dict], ...]:
    return (
        ("points-string", {"spentPoints": "1"}),
        ("points-bool", {"spent_points": True}),
        ("points-float", {"earnedPoints": 1.5}),
        ("points-negative", {"spent_points": -1}),
        ("points-overflow", {"earned_points": INT_MAX + 1}),
        ("photo-object", {"photoUrl": {"url": "forged"}}),
        ("photo-too-long", {"photo_url": "x" * (PHOTO_URL_MAX_LENGTH + 1)}),
        (
            "too-many-coupons",
            {"claimedCoupons": [{"code": f"CODE-{i}"} for i in range(101)]},
        ),
        (
            "coupon-string-too-long",
            {"claimed_coupons": [{"code": "x" * 1_001}]},
        ),
        (
            "coupon-json-too-large",
            {
                "claimedCoupons": [
                    {"code": f"CODE-{i}", "description": "x" * 4_000}
                    for i in range(20)
                ]
            },
        ),
        (
            "coupon-extra-field",
            {"claimed_coupons": [{"code": "WELCOME", "admin": True}]},
        ),
    )


class AccountRouteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.token = "account-route-token"
        self.raw_user = {
            "id": 42,
            "public_id": "usr_alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password_hash": "must-not-leak",
            "photo_url": "https://example.test/alice.png",
            "spent_points": 3,
            "earned_points": 8,
            "claimed_coupons": [{"code": "WELCOME"}],
            "email_verified": True,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }
        self.safe_user = auth.normalize_user_row(self.raw_user)
        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()

    def tearDown(self):
        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()
        self.client.close()

    def _context(self):
        return sessions.SessionContext(
            session_id="account-session",
            user=dict(self.raw_user),
            refresh_cookie=False,
        )

    def _store_route_user(self):
        row = deepcopy(self.raw_user)
        auth._memory_users_by_id[42] = row
        auth._memory_users_by_public_id[row["public_id"]] = row

    def test_legacy_public_and_identifier_account_routes_are_not_registered(self):
        self._store_route_user()
        requests = (
            ("get", "/api/users", None),
            ("get", "/api/users/by-name/Alice", None),
            ("get", "/api/users/by-email/alice@example.com", None),
            ("get", "/api/users/by-id/42", None),
            ("patch", "/api/users/42", {"photoUrl": "forged"}),
        )

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=None),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()):
            for method, path, payload in requests:
                with self.subTest(method=method, path=path):
                    request_kwargs = {"json": payload} if payload is not None else {}
                    response = self.client.request(
                        method.upper(),
                        path,
                        **request_kwargs,
                    )
                    self.assertEqual(response.status_code, 404)

    def test_current_account_routes_require_a_session(self):
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=None),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()):
            get_response = self.client.get("/api/users/me")
            patch_response = self.client.patch(
                "/api/users/me",
                json={"photoUrl": "https://example.test/new.png"},
            )

        for response in (get_response, patch_response):
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"detail": "AUTHENTICATION_REQUIRED"})

    def test_get_current_account_returns_only_the_normalized_session_user(self):
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.get("/api/users/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.safe_user)
        self.assertNotIn("password_hash", response.json())

    def test_patch_current_account_uses_session_internal_id_and_keeps_rate_limit(self):
        coupons = [_valid_coupon(), {"code": "WELCOME"}]
        payload = {
            "user_id": 999,
            "id": 999,
            "public_id": "usr_victim",
            "display_name": "Victim",
            "email": "victim@example.com",
            "password_hash": "forged-hash",
            "_fallbackName": "Victim",
            "photoUrl": "data:image/png;base64,AAAA",
            "spentPoints": 5,
            "earned_points": 8,
            "claimedCoupons": coupons,
        }
        expected_update = {
            "photo_url": "data:image/png;base64,AAAA",
            "spent_points": 5,
            "earned_points": 8,
            "claimed_coupons": coupons,
        }

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save, patch.object(
            main,
            "get_user_by_internal_id",
            new=AsyncMock(return_value=self.safe_user),
            create=True,
        ) as refresh:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch("/api/users/me", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "user": self.safe_user})
        save.assert_awaited_once_with(42, expected_update)
        refresh.assert_awaited_once_with(42)
        self.assertEqual(rate_limit.await_args.args[1:], (30, 60))
        self.assertEqual(rate_limit.await_args.args[0].url.path, "/api/users/me")

    def test_patch_current_account_rejects_malformed_updates_before_storage(self):
        for label, payload in _invalid_account_updates():
            with self.subTest(label=label), patch.object(
                sessions,
                "resolve_session",
                new=AsyncMock(return_value=self._context()),
            ), patch.object(
                main,
                "check_rate_limit",
                new=AsyncMock(),
            ) as rate_limit, patch.object(
                main,
                "save_user_data",
                new=AsyncMock(return_value=True),
            ) as save, patch.object(
                main,
                "get_user_by_internal_id",
                new=AsyncMock(return_value=self.safe_user),
                create=True,
            ):
                self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
                response = self.client.patch("/api/users/me", json=payload)

                self.assertEqual(response.status_code, 422)
                rate_limit.assert_awaited_once()
                self.assertEqual(rate_limit.await_args.args[1:], (30, 60))
                save.assert_not_awaited()

    def test_patch_current_account_caps_streamed_body_after_rate_limit(self):
        oversized_body = json.dumps({"padding": "x" * 1_300_000})

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save, patch.object(
            main,
            "get_user_by_internal_id",
            new=AsyncMock(return_value=self.safe_user),
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch(
                "/api/users/me",
                content=oversized_body,
                headers={"content-type": "application/json", "content-length": "0"},
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(rate_limit.await_args.args[1:], (30, 60))
        save.assert_not_awaited()

    def test_patch_current_account_accepts_near_limit_valid_data_avatar(self):
        prefix = "data:image/png;base64,"
        photo = prefix + ("A" * 999_976)

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save, patch.object(
            main,
            "get_user_by_internal_id",
            new=AsyncMock(return_value=self.safe_user),
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch("/api/users/me", json={"photoUrl": photo})

        self.assertEqual(response.status_code, 200)
        rate_limit.assert_awaited_once()
        save.assert_awaited_once_with(42, {"photo_url": photo})

    def test_patch_shape_guard_allows_100_complete_coupons(self):
        coupons = [_valid_coupon(index) for index in range(100)]

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save, patch.object(
            main,
            "get_user_by_internal_id",
            new=AsyncMock(return_value=self.safe_user),
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch(
                "/api/users/me",
                json={"claimedCoupons": coupons},
            )

        self.assertEqual(response.status_code, 200)
        rate_limit.assert_awaited_once()
        save.assert_awaited_once_with(42, {"claimed_coupons": coupons})

    def test_patch_current_account_rejects_malformed_https_avatars(self):
        client = TestClient(main.app, raise_server_exceptions=False)
        try:
            for photo in MALFORMED_HTTPS_AVATARS:
                with self.subTest(photo=photo), patch.object(
                    sessions,
                    "resolve_session",
                    new=AsyncMock(return_value=self._context()),
                ), patch.object(
                    main,
                    "check_rate_limit",
                    new=AsyncMock(),
                ) as rate_limit, patch.object(
                    main,
                    "save_user_data",
                    new=AsyncMock(return_value=True),
                ) as save:
                    client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
                    response = client.patch(
                        "/api/users/me",
                        json={"photoUrl": photo},
                    )

                    self.assertEqual(response.status_code, 422)
                    rate_limit.assert_awaited_once()
                    self.assertEqual(rate_limit.await_args.args[1:], (30, 60))
                    save.assert_not_awaited()
        finally:
            client.close()

    def test_patch_current_account_redacts_large_validation_input(self):
        marker = "MALICIOUS-PHOTO-MARKER"
        payload = {"photoUrl": marker + ("x" * 1_000_000)}

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch("/api/users/me", json=payload)

        self.assertEqual(response.status_code, 422)
        rate_limit.assert_awaited_once()
        self.assertEqual(rate_limit.await_args.args[1:], (30, 60))
        self.assertLess(len(response.content), 4_096)
        self.assertNotIn(marker, response.text)
        for error in response.json()["detail"]:
            self.assertEqual(set(error), {"type", "loc", "msg"})
        save.assert_not_awaited()

    def test_patch_current_account_rejects_invalid_json_after_rate_limit(self):
        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch(
                "/api/users/me",
                content=b'{"photoUrl":',
                headers={"content-type": "application/json"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "INVALID_JSON"})
        self.assertEqual(rate_limit.await_args.args[1:], (30, 60))
        save.assert_not_awaited()

    def test_patch_validation_redacts_large_nested_field_names(self):
        marker = "MALICIOUS-FIELD-MARKER"
        malicious_field = marker + ("x" * 100_000)
        payload = {
            "claimedCoupons": [
                {"code": "WELCOME", malicious_field: True},
            ]
        }

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch("/api/users/me", json=payload)

        self.assertEqual(response.status_code, 422)
        rate_limit.assert_awaited_once()
        self.assertLess(len(response.content), 4_096)
        self.assertNotIn(marker, response.text)

    def test_patch_rejects_coupon_key_amplification_with_fixed_detail(self):
        coupon = {
            "code": "WELCOME",
            **{f"x{index}": True for index in range(5_000)},
        }

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch(
                "/api/users/me",
                json={"claimedCoupons": [coupon]},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            [{
                "type": "invalid_account_update_shape",
                "loc": ["body"],
                "msg": "INVALID_ACCOUNT_UPDATE_SHAPE",
            }],
        )
        self.assertLess(len(response.content), 4_096)
        rate_limit.assert_awaited_once()
        self.assertEqual(rate_limit.await_args.args[1:], (30, 60))
        save.assert_not_awaited()

    def test_patch_caps_pydantic_validation_detail_with_sentinel(self):
        invalid_coupon = {
            "code": [],
            "id": [],
            "title": [],
            "provider": [],
            "cost": "invalid",
            "image": [],
            "category": [],
            "description": [],
            "claimedDate": [],
            "expiry": [],
        }

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(),
        ) as rate_limit, patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ) as save:
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch(
                "/api/users/me",
                json={"claimedCoupons": [invalid_coupon] * 10},
            )

        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(len(detail), 21)
        self.assertEqual(
            detail[-1],
            {
                "type": "too_many_validation_errors",
                "loc": ["body"],
                "msg": "TOO_MANY_VALIDATION_ERRORS",
            },
        )
        self.assertLess(len(response.content), 4_096)
        rate_limit.assert_awaited_once()
        save.assert_not_awaited()

    def test_patch_current_account_returns_404_when_supabase_update_matches_no_rows(self):
        update = AsyncMock(return_value=[])
        select = AsyncMock(return_value=deepcopy(self.raw_user))

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()), patch.object(
            auth,
            "supabase_enabled",
            return_value=True,
        ), patch.object(auth, "supabase_update", new=update), patch.object(
            auth,
            "supabase_select_one",
            new=select,
        ):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch(
                "/api/users/me",
                json={"photoUrl": "https://example.test/new.png"},
            )

        self.assertEqual(response.status_code, 404)
        update.assert_awaited_once_with(
            "app_users",
            {"photo_url": "https://example.test/new.png"},
            filters={"id": 42},
            returning=True,
        )

    def test_patch_current_account_does_not_refresh_by_numeric_display_name(self):
        victim = deepcopy(self.raw_user)
        victim.update({"id": 999, "public_id": "usr_victim", "display_name": "42"})
        auth._memory_users_by_id[999] = victim
        auth._memory_users_by_public_id["usr_victim"] = victim

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(return_value=self._context()),
        ), patch.object(main, "check_rate_limit", new=AsyncMock()), patch.object(
            main,
            "save_user_data",
            new=AsyncMock(return_value=True),
        ), patch.object(auth, "supabase_enabled", return_value=False):
            self.client.cookies.set(config.SESSION_COOKIE_NAME, self.token)
            response = self.client.patch(
                "/api/users/me",
                json={"photoUrl": "https://example.test/new.png"},
            )

        self.assertEqual(response.status_code, 404)


class AccountPersistenceAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()
        self.user_42 = {
            "id": 42,
            "public_id": "usr_alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password_hash": "alice-hash",
            "photo_url": None,
            "spent_points": 3,
            "earned_points": 8,
            "claimed_coupons": [],
            "updated_at": "old-alice-time",
        }
        self.user_999 = {
            "id": 999,
            "public_id": "usr_victim",
            "display_name": "Victim",
            "email": "victim@example.com",
            "password_hash": "victim-hash",
            "photo_url": "victim-photo",
            "spent_points": 70,
            "earned_points": 90,
            "claimed_coupons": [{"code": "VICTIM"}],
            "updated_at": "old-victim-time",
        }

    def tearDown(self):
        auth._memory_users_by_id.clear()
        auth._memory_users_by_public_id.clear()

    def _store_memory_users(self):
        for source in (self.user_42, self.user_999):
            row = deepcopy(source)
            auth._memory_users_by_id[row["id"]] = row
            auth._memory_users_by_public_id[row["public_id"]] = row

    async def test_direct_helper_rejects_malformed_updates_before_storage(self):
        for label, payload in _invalid_account_updates():
            select = AsyncMock(return_value=deepcopy(self.user_42))
            update = AsyncMock(return_value=[deepcopy(self.user_42)])

            with self.subTest(label=label), patch.object(
                auth,
                "supabase_enabled",
                return_value=True,
            ), patch.object(
                auth,
                "supabase_select_one",
                new=select,
            ), patch.object(auth, "supabase_update", new=update):
                with self.assertRaises(ValidationError):
                    await auth.save_user_data(42, payload)

                select.assert_not_awaited()
                update.assert_not_awaited()

    async def test_supabase_update_is_filtered_by_internal_id_and_allowlists_payload(self):
        coupons = [_valid_coupon(), {"code": "WELCOME"}]
        data = {
            "user_id": 999,
            "id": 999,
            "public_id": "usr_victim",
            "display_name": "Victim",
            "email": "victim@example.com",
            "password_hash": "forged-hash",
            "_fallbackName": "Victim",
            "photoUrl": "https://example.test/new.png",
            "spentPoints": 15,
            "earned_points": 9,
            "claimedCoupons": coupons,
        }
        select = AsyncMock()
        update = AsyncMock(return_value=[deepcopy(self.user_42)])

        with patch.object(auth, "supabase_enabled", return_value=True), patch.object(
            auth,
            "supabase_select_one",
            new=select,
        ), patch.object(auth, "supabase_update", new=update):
            result = await auth.save_user_data(42, data)

        self.assertTrue(result)
        select.assert_not_awaited()
        update.assert_awaited_once_with(
            "app_users",
            {
                "photo_url": "https://example.test/new.png",
                "spent_points": 15,
                "earned_points": 9,
                "claimed_coupons": coupons,
            },
            filters={"id": 42},
            returning=True,
        )
        storage_payload = update.await_args.args[1]
        for forbidden in (
            "user_id",
            "id",
            "public_id",
            "display_name",
            "email",
            "password_hash",
            "_fallbackName",
        ):
            self.assertNotIn(forbidden, storage_payload)

    async def test_supabase_update_returns_false_when_internal_id_matches_no_rows(self):
        select = AsyncMock()
        update = AsyncMock(return_value=[])

        with patch.object(auth, "supabase_enabled", return_value=True), patch.object(
            auth,
            "supabase_select_one",
            new=select,
        ), patch.object(auth, "supabase_update", new=update):
            result = await auth.save_user_data(
                42,
                {
                    "_fallbackName": "Victim",
                    "photoUrl": "https://example.test/valid-photo.png",
                },
            )

        self.assertFalse(result)
        select.assert_not_awaited()
        update.assert_awaited_once_with(
            "app_users",
            {"photo_url": "https://example.test/valid-photo.png"},
            filters={"id": 42},
            returning=True,
        )

    async def test_identity_only_payload_does_not_write_storage(self):
        select = AsyncMock(return_value=deepcopy(self.user_42))
        update = AsyncMock()

        with patch.object(auth, "supabase_enabled", return_value=True), patch.object(
            auth,
            "supabase_select_one",
            new=select,
        ), patch.object(auth, "supabase_update", new=update):
            result = await auth.save_user_data(
                42,
                {
                    "id": 999,
                    "public_id": "usr_victim",
                    "display_name": "Victim",
                    "email": "victim@example.com",
                    "password_hash": "forged-hash",
                    "_fallbackName": "Victim",
                },
            )

        self.assertTrue(result)
        select.assert_awaited_once_with(
            "app_users",
            columns=SAFE_USER_COLUMNS,
            filters={"id": 42},
        )
        update.assert_not_awaited()

    async def test_strict_internal_getter_uses_safe_supabase_columns_and_id_filter(self):
        select = AsyncMock(return_value=deepcopy(self.user_42))
        getter = getattr(auth, "get_user_by_internal_id", None)
        self.assertIsNotNone(getter)

        with patch.object(auth, "supabase_enabled", return_value=True), patch.object(
            auth,
            "supabase_select_one",
            new=select,
        ):
            result = await getter(42)

        self.assertEqual(result, auth.normalize_user_row(self.user_42))
        self.assertNotIn("password_hash", result)
        select.assert_awaited_once_with(
            "app_users",
            columns=SAFE_USER_COLUMNS,
            filters={"id": 42},
        )

    async def test_strict_internal_getter_does_not_fallback_to_numeric_display_name(self):
        victim = deepcopy(self.user_999)
        victim["display_name"] = "42"
        auth._memory_users_by_id[999] = victim
        auth._memory_users_by_public_id[victim["public_id"]] = victim
        getter = getattr(auth, "get_user_by_internal_id", None)
        self.assertIsNotNone(getter)

        with patch.object(auth, "supabase_enabled", return_value=False):
            result = await getter(42)

        self.assertIsNone(result)

    def test_avatar_sanitizer_preserves_approved_round_trip_values(self):
        approved = (
            "👤",
            "🌿",
            "https://example.test/avatar.png?size=small",
            "data:image/png;base64,iVBORw0KGgo=",
            "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
        )

        for photo in approved:
            with self.subTest(photo=photo[:40]):
                model = auth.CurrentAccountUpdate.model_validate({"photoUrl": photo})
                self.assertEqual(
                    model.model_dump(exclude_unset=True),
                    {"photo_url": photo},
                )
                normalized = auth.normalize_user_row(
                    {**self.user_42, "photo_url": photo}
                )
                self.assertEqual(normalized["photo_url"], photo)

    def test_avatar_sanitizer_rejects_malicious_or_unapproved_legacy_values(self):
        malicious = (
            'data:image/png;base64,iVBORw0KGgo=" onerror="alert(1)',
            "javascript:alert(1)",
            "http://example.test/avatar.png",
            "data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+",
            "data:image/png;base64,not-valid-@@",
            '<img src=x onerror="alert(1)">',
        )

        for photo in malicious:
            with self.subTest(photo=photo[:40]):
                with self.assertRaises(ValidationError):
                    auth.CurrentAccountUpdate.model_validate({"photoUrl": photo})
                normalized = auth.normalize_user_row(
                    {**self.user_42, "photo_url": photo}
                )
                self.assertIsNone(normalized["photo_url"])
                self.assertIsNone(normalized["photoUrl"])

    def test_avatar_sanitizer_is_total_for_malformed_https_urls(self):
        for photo in MALFORMED_HTTPS_AVATARS:
            with self.subTest(photo=photo):
                with self.assertRaises(ValidationError):
                    auth.CurrentAccountUpdate.model_validate({"photoUrl": photo})
                try:
                    normalized = auth.normalize_user_row(
                        {**self.user_42, "photo_url": photo}
                    )
                except Exception as exc:
                    self.fail(f"normalize_user_row raised {exc!r}")
                self.assertIsNone(normalized["photo_url"])
                self.assertIsNone(normalized["photoUrl"])

    def test_normalizer_drops_malicious_legacy_coupons(self):
        valid = [
            {"code": "WELCOME"},
            {**_valid_coupon(), "code": "RL-ABC123-350"},
            {"code": "COUPON-0", "title": "Safe voucher", "image": "🎫"},
        ]
        malicious = [
            {"code": 'BAD\" onclick=\"alert(1)'},
            {"code": "COUPON-1", "title": '<img src=x onerror="alert(1)">'},
            {"code": "COUPON-2", "image": '\"><svg onload="alert(1)">'},
            {"code": "COUPON-3", "expiry": 'x\" onmouseover=\"alert(1)'},
            {"code": "COUPON-4", "admin": True},
            {"code": "COUPON-5", "description": "x" * 5_000},
        ]

        normalized = auth.normalize_user_row(
            {**self.user_42, "claimed_coupons": valid + malicious}
        )

        self.assertEqual(normalized["claimed_coupons"], valid)
        self.assertEqual(normalized["claimedCoupons"], valid)
        serialized = json.dumps(normalized, ensure_ascii=False)
        self.assertNotIn("alert(1)", serialized)
        self.assertNotIn("admin", serialized)

    def test_normalizer_caps_legacy_coupon_count_and_compact_json_size(self):
        coupons = [{"code": f"COUPON-{index}"} for index in range(101)]
        normalized = auth.normalize_user_row(
            {**self.user_42, "claimed_coupons": coupons}
        )

        self.assertEqual(len(normalized["claimed_coupons"]), 100)
        compact = json.dumps(
            normalized["claimed_coupons"],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertLessEqual(len(compact), 64 * 1024)

    async def test_memory_update_changes_only_internal_id_with_bounded_points(self):
        self._store_memory_users()
        victim_before = deepcopy(auth._memory_users_by_id[999])

        result = await auth.save_user_data(
            "42",
            {
                "public_id": "usr_victim",
                "display_name": "Victim",
                "spent_points": 0,
                "earnedPoints": INT_MAX,
            },
        )

        self.assertTrue(result)
        self.assertEqual(auth._memory_users_by_id[42]["spent_points"], 0)
        self.assertEqual(auth._memory_users_by_id[42]["earned_points"], INT_MAX)
        self.assertNotEqual(auth._memory_users_by_id[42]["updated_at"], "old-alice-time")
        self.assertEqual(auth._memory_users_by_id[999], victim_before)

    async def test_memory_coupon_update_accepts_100_fixed_schema_items_and_deep_copies(self):
        self._store_memory_users()
        coupons = [{"code": f"COUPON-{index}"} for index in range(100)]

        result = await auth.save_user_data(42, {"claimedCoupons": coupons})
        coupons[0]["code"] = "MUTATED"

        self.assertTrue(result)
        stored = auth._memory_users_by_id[42]["claimed_coupons"]
        self.assertEqual(len(stored), 100)
        self.assertEqual(stored[0]["code"], "COUPON-0")

    async def test_external_display_name_or_public_id_cannot_select_update_owner(self):
        for identifier in ("Alice", "usr_alice"):
            with self.subTest(identifier=identifier):
                self._store_memory_users()
                before = deepcopy(auth._memory_users_by_id)

                with self.assertRaises(ValueError):
                    await auth.save_user_data(identifier, {"photoUrl": "forged"})

                self.assertEqual(auth._memory_users_by_id, before)


class AccountFrontendXssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("static/app.js").read_text(encoding="utf-8")

    def _between(self, start: str, end: str) -> str:
        return self.source.split(start, 1)[1].split(end, 1)[0]

    def test_header_avatar_uses_dom_properties_without_profile_inner_html(self):
        section = self._between("function updateHeaderUI()", "function handleAvatarClick()")

        self.assertNotIn("innerHTML", section)
        self.assertNotIn("onerror=", section)
        self.assertIn("document.createElement('img')", section)
        self.assertIn("avatarImage.src =", section)
        self.assertIn("addEventListener('error'", section)
        self.assertIn("replaceChildren", section)

    def test_claimed_coupon_grid_uses_text_content_and_event_listeners(self):
        section = self._between("// Claimed coupons grid", "function redeemReward")

        self.assertNotIn("state.claimedCoupons.map(c => `", section)
        self.assertNotIn('onclick="showCouponTicket', section)
        self.assertNotIn("${c.", section)
        self.assertIn("document.createElement('button')", section)
        self.assertIn("textContent", section)
        self.assertIn("addEventListener('click'", section)
        self.assertIn("replaceChildren", section)

    def test_coupon_ticket_uses_text_content_without_coupon_inner_html(self):
        section = self._between("function showCouponTicket(code)", "function closeModal()")

        self.assertNotIn("innerHTML", section)
        self.assertNotIn("onclick=", section)
        self.assertNotIn("${coupon.", section)
        self.assertIn("document.createElement", section)
        self.assertIn("textContent", section)
        self.assertIn("addEventListener('click'", section)
        self.assertIn("replaceChildren", section)


class FrontendAuthorizationTests(unittest.TestCase):
    def test_frontend_uses_only_session_scoped_account_and_record_endpoints(self):
        supabase = Path("static/supabase.js").read_text(encoding="utf-8")
        app = Path("static/app.js").read_text(encoding="utf-8")
        records = Path("static/js/app-records.js").read_text(encoding="utf-8")

        for forbidden in (
            "function fallbackUserId",
            "function fallbackUserName",
            "getUserById",
            "getUserByName",
            "getUserByEmail",
            "getAllUsers",
            "async getUser(",
        ):
            self.assertNotIn(forbidden, supabase)
        self.assertIn('requestJson("/api/users/me")', supabase)
        self.assertIn('requestJson("/api/users/me", {', supabase)
        self.assertNotIn("async function showUserPicker", app)
        self.assertNotIn("async function loginAs", app)
        self.assertIn("const items = await FB.getItems();", records)


if __name__ == "__main__":
    unittest.main()
