from pathlib import Path
from inspect import signature
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from models import classifier_response, upload_image
from main import app
from nlp import build_tokenizer
from nlp.model import build_model
from storage import normalize_supabase_storage_url, supabase_storage_signed_url


class CnnScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_classifier_response_uses_waste_type_label(self):
        result = classifier_response("paper", 0.91, "dispose")

        self.assertEqual(result["classifier_source"], "cnn")
        self.assertEqual(result["waste_type"], "paper")
        self.assertEqual(result["name"], "Paper")
        self.assertEqual(result["description"], "")
        self.assertIn("paper", result["text"].lower())
        self.assertIsNone(result["alternative"])

    def test_upload_image_uses_supabase_storage_bucket(self):
        with patch("models.supabase_enabled", return_value=True), \
             patch("models.SUPABASE_STORAGE_BUCKET", "scan-images"), \
             patch("models.SUPABASE_URL", "https://example.supabase.co"), \
             patch("storage.SUPABASE_SERVICE_ROLE_KEY", "test-secret"), \
             patch("storage.time.time", return_value=1000), \
             patch("models.supabase_storage_upload", new=AsyncMock(return_value={"path": "scan.png"})) as upload_mock:
            url = asyncio.run(upload_image(b"image-bytes", "scan.png"))
            self.assertEqual(
                url,
                supabase_storage_signed_url("scan-images", "scan.png", ttl_seconds=86400),
            )
        upload_mock.assert_awaited_once_with("scan-images", "scan.png", b"image-bytes", "image/png")

    def test_legacy_supabase_storage_urls_are_normalized_to_proxy_paths(self):
        url = "https://example.supabase.co/storage/v1/object/public/imgs/31d6efaf-fb68-46c1-bbe4-45f3cee4ed17.jpg"
        with patch("storage.SUPABASE_SERVICE_ROLE_KEY", "test-secret"), patch("storage.time.time", return_value=1000):
            self.assertEqual(
                normalize_supabase_storage_url(url),
                supabase_storage_signed_url(
                    "imgs",
                    "31d6efaf-fb68-46c1-bbe4-45f3cee4ed17.jpg",
                    ttl_seconds=86400,
                ),
            )

    def test_scan_endpoint_tries_remote_llm_before_local_fallback(self):
        sample_dir = Path(__file__).resolve().parents[2] / "cnn_classifier" / "src" / "data" / "test" / "paper"
        sample = next(
            path for path in sorted(sample_dir.iterdir())
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

        with patch("main.ai_analyze", new=AsyncMock(side_effect=RuntimeError("remote unavailable"))) as remote_mock:
            with sample.open("rb") as image_file:
                response = self.client.post(
                    "/api/scan/ai",
                    files={"file": (sample.name, image_file, "image/jpeg")},
                    data={"mode": "dispose", "item_type": "food", "item_state": "new", "debug": "false"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(remote_mock.await_count, 1)
        result = response.json()
        self.assertEqual(result["ai_error"], "AI failed to call, using fallback.")
        self.assertEqual(result["classifier_source"], "cnn")
        self.assertEqual(result["model_source"], "transformer")
        self.assertEqual(result["runtime_source"], "onnxruntime")
        self.assertTrue(result["artifact"].endswith(".onnx"))
        self.assertIn(
            result["waste_type"],
            {"glass", "metal", "organic", "paper", "plastic", "ewaste"},
        )
        self.assertIsInstance(result["text"], str)
        self.assertGreater(len(result["tokens"]), 8)
        self.assertIn("waste", result["text"].lower())

    def test_scan_endpoint_uses_remote_llm_response_when_available(self):
        remote_result = {
            "name": "Bottle",
            "brand": "",
            "category": "beverage",
            "description": "Remote model identified a plastic bottle.",
            "material": "plastic",
            "eco_rate": 2,
            "recycle_rate": 3,
            "standard_type": "general",
            "weighted_scores": {"a": 81, "b": 77, "c": 73, "d": 69, "e": 85},
            "alternative": {"name": "Refill Bottle", "eco_rate": 5, "recycle_rate": 5},
            "waste_type": "plastic",
            "waste_label": "Plastic",
            "text": "Remote LLM says plastic waste.",
            "classifier_source": "openai",
            "model_source": "gpt-4o-mini",
            "runtime_source": "remote",
            "artifact": "gpt-4o-mini",
            "confidence": 0.91,
        }

        with patch("main.ai_analyze", new=AsyncMock(return_value=remote_result)) as remote_mock:
            with patch("main.local_scan_response", side_effect=AssertionError("local fallback should not run")):
                response = self.client.post(
                    "/api/scan/ai",
                    files={"file": ("sample.jpg", b"fake image bytes", "image/jpeg")},
                    data={"mode": "purchase", "item_type": "food", "item_state": "new", "debug": "false"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(remote_mock.await_count, 1)
        result = response.json()
        self.assertEqual(result["classifier_source"], "openai")
        self.assertEqual(result["model_source"], "gpt-4o-mini")
        self.assertEqual(result["runtime_source"], "remote")
        self.assertEqual(result["artifact"], "gpt-4o-mini")
        self.assertEqual(result["waste_type"], "plastic")
        self.assertEqual(result["waste_label"], "Plastic")
        self.assertIn("plastic", result["text"].lower())
        self.assertEqual(result["alternative"]["name"], "Refill Bottle")

    def test_tokenizer_vocab_expanded(self):
        tokenizer = build_tokenizer()

        self.assertGreaterEqual(tokenizer.vocab_size, 80)

    def test_training_defaults_use_pretrained_backbone(self):
        self.assertTrue(signature(build_model).parameters["pretrained"].default)

    def test_scan_ui_no_longer_allows_score_dragging(self):
        app = Path("static/app.js").read_text(encoding="utf-8")
        template = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertNotIn("item.classifier_source === 'cnn'", app)
        self.assertIn("item.name || item.waste_label || item.category", app)
        self.assertIn("item.text || item.description", app)
        self.assertNotIn("throw new Error('classifier_fallback')", app)
        self.assertNotIn("toggleWS()", app)
        self.assertNotIn("startBarDrag", app)
        self.assertNotIn("updateBarFromEvent", app)
        self.assertNotIn("stopBarDrag", app)
        self.assertNotIn("weighted-toggle", template)
