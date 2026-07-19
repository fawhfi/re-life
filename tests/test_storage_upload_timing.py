import base64
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import data
import main
import scan_service
import sessions
from storage import supabase_storage_signed_url

JPEG_BYTES = b"\xff\xd8\xffminimal-jpeg"
PNG_BYTES = b"\x89PNG\r\n\x1a\nminimal-png"
WEBP_BYTES = b"RIFF\x04\x00\x00\x00WEBP"
VALID_IMAGES = (
    ("scan.jpg", "image/jpeg", JPEG_BYTES),
    ("scan.png", "image/png", PNG_BYTES),
    ("scan.webp", "image/webp", WEBP_BYTES),
)


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
        captured: dict[str, object] = {}
        image_data_url = "data:image/png;base64," + base64.b64encode(b"image-bytes").decode()

        async def fake_supabase_insert(table, values, *, returning=True):
            captured["table"] = table
            captured["values"] = values
            captured["returning"] = returning
            return [{"id": 99}]

        with patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "SUPABASE_STORAGE_BUCKET", "scan-images", create=True), \
             patch.object(data, "SUPABASE_URL", "https://example.supabase.co", create=True), \
             patch.object(data, "supabase_insert", new=fake_supabase_insert), \
             patch.object(data, "supabase_storage_upload", new=AsyncMock(return_value={"path": "scan-records/abc.png"}), create=True) as upload_mock, \
             patch.object(data, "uuid", SimpleNamespace(uuid4=lambda: "abc"), create=True), \
             patch("storage.SUPABASE_SERVICE_ROLE_KEY", "test-secret"), \
             patch("storage.time.time", return_value=1000):
            expected_url = supabase_storage_signed_url("scan-images", "scan-records/42/abc.png", ttl_seconds=86400)
            result = await data.add_item(
                {
                    "mode": "dispose",
                    "name": "Bottle",
                    "image_url": image_data_url,
                    "overall_score": 78,
                    "schema_id": "food_new",
                    "userId": 9001,
                    "user_id": 9002,
                    "userName": "Mallory",
                    "user_key": "forged-key-a",
                    "userKey": "forged-key-b",
                    "display_name": "Forged Display Name",
                },
                owner_id=42,
            )

        self.assertEqual(result, {"id": 99})
        upload_mock.assert_awaited_once_with("scan-images", "scan-records/42/abc.png", b"image-bytes", "image/png")
        self.assertEqual(captured["values"]["image_url"], expected_url)
        self.assertNotIn("data:image", captured["values"]["image_url"])

    async def test_direct_record_image_upload_requires_owner_key(self):
        with self.assertRaises(TypeError):
            await data.persist_record_image(b"image-bytes", "scan.png", "image/png")


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
        upload = source[source.index("async function uploadRecordImageIfNeeded"):source.index("function buildRecordPayload")]
        payload = source[source.index("function buildRecordPayload"):source.index("const FB =")]

        self.assertIn("async function uploadRecordImageIfNeeded", source)
        self.assertIn('requestFormJson("/api/records/image"', source)
        self.assertEqual(upload.count("form.append("), 1)
        for forbidden in ("user_id", "display_name", "user_key"):
            self.assertNotIn(forbidden, upload)
        for forbidden in ("userId:", "userName:", "userKey:"):
            self.assertNotIn(forbidden, payload)
        self.assertIn("const payload = buildRecordPayload(item || {});", source)
        self.assertLess(
            source.index("await uploadRecordImageIfNeeded(payload);"),
            source.index('requestJson("/api/records"'),
        )
        self.assertIn("body: payload", source)
        self.assertNotIn("body: item || {}", source)


class RecordImageUploadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.context = sessions.SessionContext(
            session_id="record-image-session",
            user={"id": 42, "public_id": "usr_alice", "display_name": "Alice"},
            refresh_cookie=False,
        )

    def tearDown(self):
        self.client.close()

    def test_record_image_upload_requires_authentication_before_multipart_parse(self):
        form_mock = AsyncMock(side_effect=AssertionError("multipart must not be parsed"))
        persist_mock = AsyncMock(return_value="unused")

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=None)), \
             patch.object(main.Request, "form", new=form_mock), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)) as rate_mock, \
             patch.object(main, "persist_record_image", new=persist_mock):
            response = self.client.post(
                "/api/records/image",
                files={"file": ("scan.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "AUTHENTICATION_REQUIRED"})
        form_mock.assert_not_awaited()
        rate_mock.assert_not_awaited()
        persist_mock.assert_not_awaited()

    def test_record_image_upload_endpoint_returns_storage_url(self):
        lookup_mock = AsyncMock(return_value={"id": 9001})
        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self.context)), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "get_user_by_id", new=lookup_mock, create=True), \
             patch.object(main, "persist_record_image", new=AsyncMock(return_value="/api/storage/scan-images/scan-records/42/abc.png?exp=1&sig=x")) as persist_mock:
            response = self.client.post(
                "/api/records/image",
                data={
                    "user_id": "9001",
                    "display_name": "Mallory",
                    "user_key": "forged",
                },
                files={"file": ("scan.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["image_url"], "/api/storage/scan-images/scan-records/42/abc.png?exp=1&sig=x")
        lookup_mock.assert_not_awaited()
        persist_mock.assert_awaited_once_with(
            PNG_BYTES,
            "scan.png",
            "image/png",
            owner_key=42,
        )

    def test_record_image_upload_rejects_oversized_content_length_before_form_parse(self):
        form_mock = AsyncMock(side_effect=AssertionError("multipart must not be parsed"))
        persist_mock = AsyncMock(return_value="unused")

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self.context)), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main.Request, "form", new=form_mock), \
             patch.object(main, "persist_record_image", new=persist_mock):
            response = self.client.post(
                "/api/records/image",
                headers={"content-length": str(main.MAX_MULTIPART_REQUEST_BYTES + 1)},
                files={"file": ("scan.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 413)
        form_mock.assert_not_awaited()
        persist_mock.assert_not_awaited()

    def test_record_image_upload_without_content_length_stops_oversized_receive_stream(self):
        boundary = "bounded-upload"
        prefix = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="scan.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        body = iter((prefix, PNG_BYTES, b"x" * 128, f"\r\n--{boundary}--\r\n".encode()))
        persist_mock = AsyncMock(return_value="unused")

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self.context)), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "MAX_MULTIPART_REQUEST_BYTES", 128), \
             patch.object(main, "persist_record_image", new=persist_mock):
            response = self.client.post(
                "/api/records/image",
                headers={"content-type": f"multipart/form-data; boundary={boundary}"},
                content=body,
            )

        self.assertEqual(response.status_code, 413)
        persist_mock.assert_not_awaited()

    def test_record_image_upload_reads_file_in_bounded_chunks(self):
        persist_mock = AsyncMock(return_value="unused")

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self.context)), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "MAX_UPLOAD_BYTES", len(PNG_BYTES) - 1), \
             patch.object(main, "MAX_MULTIPART_REQUEST_BYTES", 4096), \
             patch.object(main, "persist_record_image", new=persist_mock):
            response = self.client.post(
                "/api/records/image",
                files={"file": ("scan.png", PNG_BYTES, "image/png")},
            )

        self.assertEqual(response.status_code, 413)
        persist_mock.assert_not_awaited()

    def test_record_image_upload_rejects_missing_or_spoofed_mime(self):
        persist_mock = AsyncMock(return_value="unused")
        cases = (
            ("jpeg-spoof", "scan.jpg", "image/jpeg", PNG_BYTES),
            ("png-spoof", "scan.png", "image/png", JPEG_BYTES),
            ("webp-spoof", "scan.webp", "image/webp", PNG_BYTES),
        )
        boundary = "missing-mime"
        missing_mime_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="scan.png"\r\n'
            "\r\n"
        ).encode() + PNG_BYTES + f"\r\n--{boundary}--\r\n".encode()

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self.context)), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "persist_record_image", new=persist_mock):
            missing_mime_response = self.client.post(
                "/api/records/image",
                headers={"content-type": f"multipart/form-data; boundary={boundary}"},
                content=missing_mime_body,
            )
            self.assertEqual(missing_mime_response.status_code, 400)
            for label, filename, mime, contents in cases:
                with self.subTest(label=label):
                    response = self.client.post(
                        "/api/records/image",
                        files={"file": (filename, contents, mime)},
                    )
                    self.assertEqual(response.status_code, 400)

        persist_mock.assert_not_awaited()

    def test_record_image_upload_accepts_each_allowed_magic_signature(self):
        persist_mock = AsyncMock(return_value="/api/storage/scan-images/ok")

        with patch.object(sessions, "resolve_session", new=AsyncMock(return_value=self.context)), \
             patch.object(main, "check_rate_limit", new=AsyncMock(return_value=None)), \
             patch.object(main, "persist_record_image", new=persist_mock):
            for filename, mime, contents in VALID_IMAGES:
                with self.subTest(mime=mime):
                    persist_mock.reset_mock()
                    response = self.client.post(
                        "/api/records/image",
                        files={"file": (filename, contents, mime)},
                    )
                    self.assertEqual(response.status_code, 200)
                    persist_mock.assert_awaited_once_with(
                        contents,
                        filename,
                        mime,
                        owner_key=42,
                    )
