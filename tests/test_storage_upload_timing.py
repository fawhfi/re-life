import base64
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import data
import scan_service
from storage import supabase_storage_signed_url


class StorageUploadTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_scan_payload_keeps_image_local_and_does_not_upload_to_storage(self):
        source = Path("scan_service.py").read_text(encoding="utf-8")
        self.assertNotIn("upload_image", source)

        result = await scan_service.normalize_scan_payload(
            {"name": "Bottle", "material": "plastic"},
            b"image-bytes",
            "scan.jpg",
            "dispose",
            "food_new",
        )

        self.assertNotIn("image_url", result)

    async def test_add_item_uploads_data_url_to_storage_before_record_insert(self):
        owner = {"id": 42, "displayName": "Alice"}
        captured: dict[str, object] = {}
        image_data_url = "data:image/png;base64," + base64.b64encode(b"image-bytes").decode()

        async def fake_supabase_insert(table, values, *, returning=True):
            captured["table"] = table
            captured["values"] = values
            captured["returning"] = returning
            return [{"id": 99}]

        with patch.object(data, "_resolve_user_id", new=AsyncMock(return_value=owner)), \
             patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "SUPABASE_STORAGE_BUCKET", "scan-images", create=True), \
             patch.object(data, "SUPABASE_URL", "https://example.supabase.co", create=True), \
             patch.object(data, "supabase_insert", new=fake_supabase_insert), \
             patch.object(data, "supabase_storage_upload", new=AsyncMock(return_value={"path": "scan-records/abc.png"}), create=True) as upload_mock, \
             patch.object(data, "uuid", SimpleNamespace(uuid4=lambda: "abc"), create=True), \
             patch("storage.SUPABASE_SERVICE_ROLE_KEY", "test-secret"), \
             patch("storage.time.time", return_value=1000):
            expected_url = supabase_storage_signed_url("scan-images", "scan-records/abc.png", ttl_seconds=86400)
            result = await data.add_item(
                {
                    "mode": "dispose",
                    "name": "Bottle",
                    "image_url": image_data_url,
                    "overall_score": 78,
                    "schema_id": "food_new",
                    "userId": 42,
                    "userName": "Alice",
                }
            )

        self.assertEqual(result, {"id": 99})
        upload_mock.assert_awaited_once_with("scan-images", "scan-records/abc.png", b"image-bytes", "image/png")
        self.assertEqual(captured["values"]["image_url"], expected_url)
        self.assertNotIn("data:image", captured["values"]["image_url"])


class FrontendImageCacheTests(unittest.TestCase):
    def test_scan_result_uses_selected_file_data_url_until_record_save(self):
        source = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("selectedFileDataUrl: ''", source)
        self.assertIn("state.selectedFileDataUrl = reader.result;", source)
        self.assertIn("data.image_url = state.selectedFileDataUrl;", source)
        self.assertLess(
            source.index("data.image_url = state.selectedFileDataUrl;"),
            source.index("showScanResult(data);"),
        )

    def test_add_item_uploads_local_data_url_before_record_json_request(self):
        source = Path("static/supabase.js").read_text(encoding="utf-8")

        self.assertIn("async function uploadRecordImageIfNeeded", source)
        self.assertIn('requestFormJson("/api/records/image"', source)
        self.assertIn("const payload = buildRecordPayload(item || {});", source)
        self.assertLess(
            source.index("await uploadRecordImageIfNeeded(payload);"),
            source.index('requestJson("/api/records"'),
        )
        self.assertIn("body: payload", source)
        self.assertNotIn("body: item || {}", source)


class RecordImageUploadEndpointTests(unittest.TestCase):
    def test_record_image_upload_endpoint_returns_storage_url(self):
        from fastapi.testclient import TestClient
        from main import app

        with patch("main.check_rate_limit", new=AsyncMock(return_value=None)), \
             patch("main.get_user_by_id", new=AsyncMock(return_value={"id": 42})), \
             patch("main.persist_record_image", new=AsyncMock(return_value="/api/storage/scan-images/scan-records/abc.png?exp=1&sig=x")) as persist_mock:
            response = TestClient(app).post(
                "/api/records/image",
                data={"user_id": "42"},
                files={"file": ("scan.png", b"image-bytes", "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["image_url"], "/api/storage/scan-images/scan-records/abc.png?exp=1&sig=x")
        persist_mock.assert_awaited_once_with(b"image-bytes", "scan.png", "image/png")
