import inspect
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import data
import main
import sessions
from config import SESSION_COOKIE_NAME


class RecordAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        data._memory_records_by_id.clear()
        data._memory_record_seq = 1

    def tearDown(self):
        data._memory_records_by_id.clear()
        data._memory_record_seq = 1

    async def test_record_modes_are_canonicalized_on_legacy_read_and_new_write(self):
        malicious_mode = 'x" onmouseover="alert(1)'
        normalized = data._normalize_record_row({"id": 7, "mode": malicious_mode})
        captured: dict[str, object] = {}

        async def fake_supabase_insert(table, values, *, returning=True):
            captured.update(values)
            return [{"id": 8, **values}]

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_insert", new=fake_supabase_insert):
            await data.add_item({"mode": malicious_mode}, owner_id=42)

        self.assertEqual(normalized["status"], "dispose")
        self.assertEqual(captured["mode"], "dispose")
        self.assertEqual(data.canonicalize_record_mode("purchase"), "purchase")

    async def test_add_item_ignores_all_forged_identity_fields(self):
        captured: dict[str, object] = {}

        async def fake_supabase_insert(table, values, *, returning=True):
            captured["table"] = table
            captured["values"] = values
            captured["returning"] = returning
            return [{"id": 99, **values}]

        forged_item = {
            "name": "Bottle",
            "image_url": "https://example.test/bottle.png",
            "userId": 9001,
            "user_id": 9002,
            "userName": "Mallory",
            "user_key": "forged-key-a",
            "userKey": "forged-key-b",
            "display_name": "Forged Display Name",
        }

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_insert", new=fake_supabase_insert):
            result = await data.add_item(forged_item, owner_id="42")

        self.assertEqual(result, {"id": 99})
        self.assertEqual(captured["table"], "scan_records")
        self.assertEqual(captured["values"]["user_id"], 42)

    async def test_get_items_filters_only_authenticated_owner(self):
        captured: dict[str, object] = {}

        async def fake_supabase_select(table, *, columns="*", filters=None, order=None, limit=None):
            captured["table"] = table
            captured["filters"] = filters
            captured["order"] = order
            return [{"id": 7, "user_id": 42, "name": "Bottle"}]

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_select", new=fake_supabase_select):
            rows = await data.get_items(owner_id="42")

        self.assertEqual(captured, {
            "table": "scan_records",
            "filters": {"user_id": 42},
            "order": "created_at.desc",
        })
        self.assertEqual([row["id"] for row in rows], [7])
        self.assertEqual(rows[0]["userId"], 42)

    async def test_delete_item_filters_owner_and_record_and_requests_returning_rows(self):
        captured: dict[str, object] = {}

        async def fake_supabase_delete(table, *, filters=None, returning=False):
            captured["table"] = table
            captured["filters"] = filters
            captured["returning"] = returning
            return [{"id": 7, "user_id": 42}]

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_delete", new=fake_supabase_delete):
            deleted = await data.delete_item("7", owner_id="42")

        self.assertTrue(deleted)
        self.assertEqual(captured, {
            "table": "scan_records",
            "filters": {"id": 7, "user_id": 42},
            "returning": True,
        })

    async def test_delete_item_returns_false_when_supabase_deletes_zero_rows(self):
        async def fake_supabase_delete(table, *, filters=None, returning=False):
            return []

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_delete", new=fake_supabase_delete):
            self.assertFalse(await data.delete_item(7, owner_id=42))

    async def test_memory_delete_canonicalizes_string_record_id(self):
        data._memory_records_by_id[7] = {"id": 7, "user_id": 42}

        with patch.object(data, "supabase_enabled", return_value=False):
            deleted = await data.delete_item("7", owner_id="42")

        self.assertTrue(deleted)
        self.assertNotIn(7, data._memory_records_by_id)

    async def test_memory_delete_refuses_cross_owner_record(self):
        data._memory_records_by_id[7] = {"id": 7, "user_id": 99}

        with patch.object(data, "supabase_enabled", return_value=False):
            deleted = await data.delete_item("7", owner_id="42")

        self.assertFalse(deleted)
        self.assertIn(7, data._memory_records_by_id)

    async def test_memory_delete_invalid_record_id_fails_closed(self):
        data._memory_records_by_id[7] = {"id": 7, "user_id": 42}

        with patch.object(data, "supabase_enabled", return_value=False):
            deleted = await data.delete_item("not-a-record-id", owner_id=42)

        self.assertFalse(deleted)
        self.assertIn(7, data._memory_records_by_id)

    async def test_memory_clear_removes_only_authenticated_owner_records(self):
        data._memory_records_by_id.update({
            1: {"id": 1, "user_id": 42},
            2: {"id": 2, "user_id": 99},
            3: {"id": 3, "user_id": 42},
        })

        with patch.object(data, "supabase_enabled", return_value=False):
            await data.clear_all_items(owner_id="42")

        self.assertEqual(set(data._memory_records_by_id), {2})

    async def test_supabase_clear_filters_only_authenticated_owner(self):
        captured: dict[str, object] = {}

        async def fake_supabase_delete(table, *, filters=None, returning=False):
            captured["table"] = table
            captured["filters"] = filters
            captured["returning"] = returning
            return None

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_delete", new=fake_supabase_delete):
            await data.clear_all_items(owner_id="42")

        self.assertEqual(captured, {
            "table": "scan_records",
            "filters": {"user_id": 42},
            "returning": False,
        })

    async def test_supabase_add_outage_propagates_without_memory_fallback(self):
        async def unavailable(*args, **kwargs):
            raise RuntimeError("insert unavailable")

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_insert", new=unavailable):
            with self.assertRaisesRegex(RuntimeError, "insert unavailable"):
                await data.add_item({"name": "Bottle"}, owner_id=42)

        self.assertEqual(data._memory_records_by_id, {})

    async def test_supabase_select_outage_propagates_without_memory_fallback(self):
        data._memory_records_by_id[1] = {"id": 1, "user_id": 42}

        async def unavailable(*args, **kwargs):
            raise RuntimeError("select unavailable")

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_select", new=unavailable):
            with self.assertRaisesRegex(RuntimeError, "select unavailable"):
                await data.get_items(owner_id=42)

        self.assertIn(1, data._memory_records_by_id)

    async def test_supabase_delete_outage_propagates_without_memory_fallback(self):
        data._memory_records_by_id[7] = {"id": 7, "user_id": 42}

        async def unavailable(*args, **kwargs):
            raise RuntimeError("delete unavailable")

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_delete", new=unavailable):
            with self.assertRaisesRegex(RuntimeError, "delete unavailable"):
                await data.delete_item(7, owner_id=42)

        self.assertIn(7, data._memory_records_by_id)

    async def test_supabase_clear_outage_propagates_without_memory_fallback(self):
        data._memory_records_by_id[7] = {"id": 7, "user_id": 42}

        async def unavailable(*args, **kwargs):
            raise RuntimeError("clear unavailable")

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_delete", new=unavailable):
            with self.assertRaisesRegex(RuntimeError, "clear unavailable"):
                await data.clear_all_items(owner_id=42)

        self.assertIn(7, data._memory_records_by_id)

    def test_record_functions_expose_only_keyword_owner_identity(self):
        expected = {
            data.add_item: [
                ("item", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                ("owner_id", inspect.Parameter.KEYWORD_ONLY),
            ],
            data.get_items: [("owner_id", inspect.Parameter.KEYWORD_ONLY)],
            data.delete_item: [
                ("item_id", inspect.Parameter.POSITIONAL_OR_KEYWORD),
                ("owner_id", inspect.Parameter.KEYWORD_ONLY),
            ],
            data.clear_all_items: [("owner_id", inspect.Parameter.KEYWORD_ONLY)],
        }

        for function, expected_parameters in expected.items():
            with self.subTest(function=function.__name__):
                parameters = inspect.signature(function).parameters.values()
                self.assertEqual(
                    [(parameter.name, parameter.kind) for parameter in parameters],
                    expected_parameters,
                )

    async def test_record_functions_reject_positional_owner_and_legacy_identity_kwargs(self):
        invalid_calls = [
            lambda: data.add_item({}, 42),
            lambda: data.get_items(42),
            lambda: data.delete_item(7, 42),
            lambda: data.clear_all_items(42),
            lambda: data.add_item({}, owner_id=42, user_id=99),
            lambda: data.get_items(owner_id=42, display_name="Mallory"),
            lambda: data.delete_item(7, owner_id=42, user_key="forged"),
            lambda: data.clear_all_items(owner_id=42, userName="Mallory"),
        ]

        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call):
                with self.assertRaises(TypeError):
                    await invalid_call()

    def test_normalized_record_keeps_display_fields_without_inventing_owner(self):
        normalized = data._normalize_record_row(
            {"id": 7, "name": "Bottle", "display_name": "Mallory"},
            user_name="Alice",
        )

        self.assertIsNone(normalized["userId"])
        self.assertEqual(normalized["userName"], "Alice")

    def test_owner_id_canonicalizer_accepts_only_positive_postgres_bigints(self):
        maximum = 9_223_372_036_854_775_807

        for value, expected in ((1, 1), ("1", 1), (maximum, maximum), (str(maximum), maximum)):
            with self.subTest(value=value):
                self.assertEqual(data.canonicalize_owner_id(value), expected)

    def test_owner_id_canonicalizer_rejects_noncanonical_or_out_of_range_values(self):
        maximum = 9_223_372_036_854_775_807
        invalid_values = (
            True,
            False,
            1.0,
            " 1",
            "1 ",
            "+1",
            "01",
            "0",
            0,
            -1,
            maximum + 1,
            str(maximum + 1),
            None,
            {},
            [],
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    data.canonicalize_owner_id(value)

    async def test_all_record_storage_boundaries_use_strict_owner_canonicalization(self):
        invalid_owner = "01"
        calls = (
            lambda: data.add_item({}, owner_id=invalid_owner),
            lambda: data.get_items(owner_id=invalid_owner),
            lambda: data.delete_item(1, owner_id=invalid_owner),
            lambda: data.clear_all_items(owner_id=invalid_owner),
            lambda: data._persist_record_image_url(None, owner_id=invalid_owner),
            lambda: data.persist_record_image(
                b"image-bytes",
                "scan.png",
                "image/png",
                owner_key=invalid_owner,
            ),
        )

        with patch.object(data, "supabase_enabled", return_value=False):
            for call in calls:
                with self.subTest(call=call):
                    with self.assertRaises(ValueError):
                        await call()

    async def test_supabase_insert_requires_a_returned_valid_record_id(self):
        invalid_results = ([], [{}], [{"id": None}], [{"id": 0}], [{"id": "01"}])

        for rows in invalid_results:
            async def fake_supabase_insert(*args, **kwargs):
                return rows

            with self.subTest(rows=rows), \
                 patch.object(data, "supabase_enabled", return_value=True), \
                 patch.object(data, "supabase_insert", new=fake_supabase_insert):
                with self.assertRaisesRegex(RuntimeError, "valid record id"):
                    await data.add_item({"name": "Bottle"}, owner_id=42)


class RecordRouteAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.raw_user = {
            "id": 42,
            "public_id": "usr_alice",
            "display_name": "Alice",
            "email": "alice@example.com",
        }

    def tearDown(self):
        self.client.close()

    def _context(self, user=None):
        return sessions.SessionContext(
            session_id="record-route-session",
            user=dict(user or self.raw_user),
            refresh_cookie=False,
        )

    def test_record_routes_require_a_verified_session(self):
        get_mock = AsyncMock(return_value=[])
        add_mock = AsyncMock(return_value={"id": 7})
        clear_mock = AsyncMock(return_value=None)
        delete_mock = AsyncMock(return_value=True)
        rate_mock = AsyncMock(return_value=None)

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=None)), \
             patch.object(main, "check_rate_limit", new=rate_mock), \
             patch.object(main, "get_items", new=get_mock), \
             patch.object(main, "add_item", new=add_mock), \
             patch.object(main, "clear_all_items", new=clear_mock), \
             patch.object(main, "delete_item", new=delete_mock):
            responses = (
                self.client.get("/api/records?user_id=9001&display_name=Mallory"),
                self.client.post("/api/records", json={"name": "Bottle", "userId": 9001}),
                self.client.delete("/api/records?user_key=forged"),
                self.client.delete("/api/records/7"),
            )

        for response in responses:
            with self.subTest(path=response.request.url.path):
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {"detail": "AUTHENTICATION_REQUIRED"})
        get_mock.assert_not_awaited()
        add_mock.assert_not_awaited()
        clear_mock.assert_not_awaited()
        delete_mock.assert_not_awaited()
        rate_mock.assert_not_awaited()

    def test_record_routes_use_only_session_owner_and_strip_forged_body_identity(self):
        get_mock = AsyncMock(return_value=[])
        add_mock = AsyncMock(return_value={"id": 7})
        clear_mock = AsyncMock(return_value=None)
        delete_mock = AsyncMock(return_value=True)

        forged_body = {
            "name": "Bottle",
            "user_id": 9001,
            "userId": 9002,
            "userName": "Mallory",
            "user_key": "forged-a",
            "userKey": "forged-b",
            "display_name": "Forged Display Name",
        }

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self._context())), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "get_items", new=get_mock), \
             patch.object(main, "add_item", new=add_mock), \
             patch.object(main, "clear_all_items", new=clear_mock), \
             patch.object(main, "delete_item", new=delete_mock):
            list_response = self.client.get(
                "/api/records?user_id=9001&display_name=Mallory&user_key=forged"
            )
            create_response = self.client.post("/api/records", json=forged_body)
            clear_response = self.client.delete(
                "/api/records?user_id=9001&display_name=Mallory&user_key=forged"
            )
            delete_response = self.client.delete("/api/records/7")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        get_mock.assert_awaited_once_with(owner_id=42)
        add_mock.assert_awaited_once_with({"name": "Bottle"}, owner_id=42)
        clear_mock.assert_awaited_once_with(owner_id=42)
        delete_mock.assert_awaited_once_with("7", owner_id=42)

    def test_cross_owner_and_missing_record_deletes_return_identical_404(self):
        delete_mock = AsyncMock(side_effect=[False, False])

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self._context())), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "delete_item", new=delete_mock):
            cross_owner = self.client.delete("/api/records/7")
            missing = self.client.delete("/api/records/999")

        self.assertEqual(cross_owner.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(cross_owner.json(), {"error": "Record not found"})
        self.assertEqual(missing.json(), cross_owner.json())

    def test_noncanonical_session_owner_is_rejected_without_calling_storage(self):
        get_mock = AsyncMock(return_value=[])
        malformed_user = {**self.raw_user, "id": "042"}

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self._context(malformed_user))), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "get_items", new=get_mock):
            response = self.client.get("/api/records")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "AUTHENTICATION_REQUIRED"})
        get_mock.assert_not_awaited()

    def test_record_insert_storage_failure_returns_non_success_response(self):
        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self._context())), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "add_item", new=AsyncMock(side_effect=RuntimeError("record insert did not return a valid record id"))):
            response = self.client.post("/api/records", json={"name": "Bottle"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"error": "Record save failed"})
        self.assertNotIn("ok", response.json())

    def test_reward_redeem_requires_a_verified_session(self):
        reward_id = data.REWARDS_CATALOG[0]["id"]

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=None)), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)) as rate_mock:
            response = self.client.post("/api/rewards/redeem", json={"reward_id": reward_id})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "AUTHENTICATION_REQUIRED"})
        rate_mock.assert_not_awaited()

    def test_authenticated_reward_redeem_preserves_simulated_coupon_rules(self):
        reward = data.REWARDS_CATALOG[0]

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self._context())), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main.uuid, "uuid4", return_value=type("FixedUuid", (), {"hex": "abcdef123456"})()):
            response = self.client.post("/api/rewards/redeem", json={"reward_id": reward["id"]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["coupon"]["code"], f"RL-ABCDEF-{reward['cost']}")
        self.assertEqual(response.json()["coupon"]["cost"], reward["cost"])


class CrossAccountExploitTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.alice_token = "alice-record-session-token"
        self.bob_token = "bob-record-session-token"
        self.contexts = {
            self.alice_token: sessions.SessionContext(
                session_id="alice-record-session",
                user={"id": 1, "public_id": "usr_alice", "display_name": "Alice"},
                refresh_cookie=False,
            ),
            self.bob_token: sessions.SessionContext(
                session_id="bob-record-session",
                user={"id": 2, "public_id": "usr_bob", "display_name": "Bob"},
                refresh_cookie=False,
            ),
        }
        data._memory_records_by_id.clear()
        data._memory_record_seq = 1

    def tearDown(self):
        data._memory_records_by_id.clear()
        data._memory_record_seq = 1
        self.client.close()

    async def _resolve_session(self, token):
        return self.contexts.get(token)

    def _use_session(self, token):
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def test_forged_identity_cannot_cross_account_record_boundary(self):
        forged_bob_identity = {
            "name": "Alice Bottle",
            "user_id": 2,
            "userId": 2,
            "userName": "Bob",
            "user_key": "usr_bob",
            "userKey": "usr_bob",
            "display_name": "Bob",
        }

        with patch.object(
            sessions,
            "resolve_session",
            new=AsyncMock(side_effect=self._resolve_session),
        ), patch.object(
            main,
            "check_rate_limit",
            new=AsyncMock(return_value=None),
        ), patch.object(data, "supabase_enabled", return_value=False):
            self._use_session(self.alice_token)
            created = self.client.post("/api/records", json=forged_bob_identity)
            self.assertEqual(created.status_code, 200)
            record_id = created.json()["id"]
            self.assertEqual(data._memory_records_by_id[record_id]["user_id"], 1)

            self._use_session(self.bob_token)
            self.assertEqual(self.client.get("/api/records").json(), [])
            cross_owner_delete = self.client.delete(f"/api/records/{record_id}")
            missing_delete = self.client.delete("/api/records/999999")
            self.assertEqual(cross_owner_delete.status_code, 404)
            self.assertEqual(missing_delete.status_code, 404)
            self.assertEqual(cross_owner_delete.json(), missing_delete.json())
            self.assertEqual(cross_owner_delete.json(), {"error": "Record not found"})

            bob_clear = self.client.delete("/api/records")
            self.assertEqual(bob_clear.status_code, 200)

            self._use_session(self.alice_token)
            alice_records = self.client.get("/api/records")
            self.assertEqual(alice_records.status_code, 200)
            self.assertEqual([record["id"] for record in alice_records.json()], [record_id])

            alice_delete = self.client.delete(f"/api/records/{record_id}")
            self.assertEqual(alice_delete.status_code, 200)
            self.assertEqual(self.client.get("/api/records").json(), [])


if __name__ == "__main__":
    unittest.main()
