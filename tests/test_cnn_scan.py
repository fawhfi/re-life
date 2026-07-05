from pathlib import Path
from inspect import signature
import asyncio
import contextlib
import io
import json
import unittest
from unittest.mock import ANY, AsyncMock, patch

from fastapi.testclient import TestClient
import httpx

from models import ai_analyze, classifier_response, upload_image
import models
from main import app
from nlp import build_tokenizer
from nlp.infer import DEFAULT_MODEL_PATH
from nlp.model import build_model
from storage import normalize_supabase_storage_url, supabase_storage_signed_url


class CnnScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def _remote_json(self, name="Custom Bottle"):
        return json.dumps({
            "name": name,
            "brand": "",
            "category": "beverage",
            "description": "Custom model identified a reusable bottle.",
            "ecoRate": 4,
            "recycleRate": 5,
            "standardType": "general",
            "material": "plastic",
            "disposalGuide": "Rinse and reuse before recycling.",
            "precaution": "",
            "weightedScores": {"a": 80, "b": 82, "c": 78, "d": 76, "e": 90},
            "alternative": {"name": "Refill Bottle", "ecoRate": 5, "recycleRate": 5},
        })

    def _failing_async_client(self, status_code=401, body=None, text=None, content_type="application/json"):
        response_body = body or {"error": {"message": "bad key"}}

        class FailingAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, headers=None, json=None):
                if text is not None:
                    return httpx.Response(
                        status_code,
                        text=text,
                        request=httpx.Request("POST", url),
                        headers={"content-type": content_type},
                    )
                return httpx.Response(
                    status_code,
                    json=response_body,
                    request=httpx.Request("POST", url),
                    headers={"content-type": "application/json"},
                )

        return FailingAsyncClient

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

    def test_nlp_artifacts_are_synced_from_training_repo(self):
        artifacts = Path("nlp/artifacts")

        self.assertEqual(DEFAULT_MODEL_PATH.name, "model_fp16.onnx")
        self.assertTrue((artifacts / "model_fp16.onnx").exists())
        self.assertTrue((artifacts / "tokenizer.json").exists())
        self.assertTrue((artifacts / "metadata.json").exists())

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
        self.assertEqual(result["classifier_source"], "nlp")
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

    def test_scan_endpoint_debug_mode_forces_local_transformer(self):
        sample_dir = Path(__file__).resolve().parents[2] / "cnn_classifier" / "src" / "data" / "test" / "paper"
        sample = next(
            path for path in sorted(sample_dir.iterdir())
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

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
            with patch("main.local_scan_response", return_value={
                "name": "Paper",
                "brand": "",
                "category": "paper",
                "waste_type": "paper",
                "waste_label": "Paper",
                "classifier_source": "nlp",
                "model_source": "transformer",
                "runtime_source": "onnxruntime",
                "artifact": "model_fp16.onnx",
                "text": "This looks like paper waste.",
                "tokens": ["this", "looks", "like", "paper", "waste"],
                "confidence": 0.99,
                "standard_type": "general",
                "description": "",
                "material": "paper",
                "eco_rate": 5,
                "recycle_rate": 5,
                "weighted_scores": {"a": 90, "b": 90, "c": 90, "d": 90, "e": 90},
                "disposal_guide": "Keep dry, no grease, flatten",
                "precaution": "",
                "alternative": None,
            }) as local_mock:
                with sample.open("rb") as image_file:
                    response = self.client.post(
                        "/api/scan/ai",
                        files={"file": (sample.name, image_file, "image/jpeg")},
                        data={"mode": "dispose", "item_type": "food", "item_state": "new", "debug": "true"},
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(remote_mock.await_count, 0)
        local_mock.assert_called_once()
        result = response.json()
        self.assertEqual(result["classifier_source"], "nlp")
        self.assertEqual(result["model_source"], "transformer")
        self.assertEqual(result["runtime_source"], "onnxruntime")
        self.assertEqual(result["artifact"], "model_fp16.onnx")

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

    def test_ai_analyze_uses_custom_openai_compatible_endpoint(self):
        with patch("models.DEFAULT_AI_MODEL", "custom"), \
             patch("models.CUSTOM_METHOD", "openai"), \
             patch("models.CUSTOM_API_KEY", "custom-key"), \
             patch("models.CUSTOM_BASE_URL", "https://llm.example.com/v1"), \
             patch("models.CUSTOM_MODEL", "vision-model"), \
             patch("models._compress_image", return_value=(b"compressed", "image/png")), \
             patch("models._call_openai_compat", new=AsyncMock(return_value=self._remote_json())) as custom_mock:
            result = asyncio.run(ai_analyze(b"image-bytes", "sid-custom"))

        custom_mock.assert_awaited_once_with(
            "custom-key",
            "https://llm.example.com/v1",
            "vision-model",
            ANY,
            "Y29tcHJlc3NlZA==",
            "image/png",
        )
        self.assertEqual(result["name"], "Custom Bottle")
        self.assertEqual(result["alternative"]["name"], "Refill Bottle")

    def test_ai_analyze_uses_custom_anthropic_endpoint(self):
        with patch("models.DEFAULT_AI_MODEL", "custom"), \
             patch("models.CUSTOM_METHOD", "anthropic"), \
             patch("models.CUSTOM_API_KEY", "custom-key"), \
             patch("models.CUSTOM_BASE_URL", "https://anthropic-proxy.example.com/v1"), \
             patch("models.CUSTOM_MODEL", "claude-proxy-model"), \
             patch("models._compress_image", return_value=(b"compressed", "image/png")), \
             patch("models._call_anthropic_compat", new=AsyncMock(return_value=self._remote_json("Proxy Bottle"))) as custom_mock:
            result = asyncio.run(ai_analyze(b"image-bytes", "sid-custom"))

        custom_mock.assert_awaited_once_with(
            "custom-key",
            "https://anthropic-proxy.example.com/v1",
            "claude-proxy-model",
            ANY,
            "Y29tcHJlc3NlZA==",
            "image/png",
        )
        self.assertEqual(result["name"], "Proxy Bottle")

    def test_ai_analyze_keeps_builtin_claude_provider_working(self):
        with patch("models.DEFAULT_AI_MODEL", "claude"), \
             patch("models.CLAUDE_API_KEY", "claude-key"), \
             patch("models.CLAUDE_MODEL", "claude-test-model"), \
             patch("models._compress_image", return_value=(b"compressed", "image/png")), \
             patch("models._call_anthropic_compat", new=AsyncMock(return_value=self._remote_json("Claude Bottle"))) as claude_mock:
            result = asyncio.run(ai_analyze(b"image-bytes", "sid-claude"))

        claude_mock.assert_awaited_once_with(
            "claude-key",
            "https://api.anthropic.com/v1",
            "claude-test-model",
            ANY,
            "Y29tcHJlc3NlZA==",
            "image/png",
        )
        self.assertEqual(result["name"], "Claude Bottle")

    def test_openai_compatible_root_base_url_uses_v1_chat_completions(self):
        self.assertEqual(
            models._openai_chat_url("https://ai.furry.edu.gr"),
            "https://ai.furry.edu.gr/v1/chat/completions",
        )
        self.assertEqual(
            models._openai_chat_url("https://ai.furry.edu.gr/v1"),
            "https://ai.furry.edu.gr/v1/chat/completions",
        )

    def test_openai_compatible_failure_raises_without_debug_prints(self):
        stream = io.StringIO()

        with patch("models.httpx.AsyncClient", self._failing_async_client(401)), \
             contextlib.redirect_stdout(stream), \
             self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(models._call_openai_compat(
                "secret-api-key",
                "https://llm.example.com/v1",
                "vision-model",
                "prompt",
                "base64-image-payload",
                "image/png",
            ))

        output = stream.getvalue()
        self.assertEqual(output, "")
        self.assertNotIn("secret-api-key", output)
        self.assertNotIn("base64-image-payload", output)

    def test_openai_compatible_200_non_json_raises_without_debug_prints(self):
        stream = io.StringIO()

        with patch("models.httpx.AsyncClient", self._failing_async_client(
                200,
                text="not-json response from proxy",
                content_type="text/plain",
             )), \
             contextlib.redirect_stdout(stream), \
             self.assertRaisesRegex(Exception, "non-JSON"):
            asyncio.run(models._call_openai_compat(
                "secret-api-key",
                "https://ai.furry.edu.gr",
                "vision-model",
                "prompt",
                "base64-image-payload",
                "image/png",
            ))

        output = stream.getvalue()
        self.assertEqual(output, "")
        self.assertNotIn("secret-api-key", output)
        self.assertNotIn("base64-image-payload", output)

    def test_openai_compatible_html_response_reports_frontend_url_hint(self):
        stream = io.StringIO()
        html = '<!doctype html><html><head><title>PawsAI - AI API Gateway</title></head></html>'

        with patch("models.httpx.AsyncClient", self._failing_async_client(
                200,
                text=html,
                content_type="text/html; charset=utf-8",
             )), \
             contextlib.redirect_stdout(stream), \
             self.assertRaisesRegex(Exception, "returned HTML"):
            asyncio.run(models._call_openai_compat(
                "secret-api-key",
                "https://ai.furry.edu.gr",
                "vision-model",
                "prompt",
                "base64-image-payload",
                "image/png",
            ))

        output = stream.getvalue()
        self.assertEqual(output, "")
        self.assertNotIn("secret-api-key", output)
        self.assertNotIn("base64-image-payload", output)

    def test_anthropic_compatible_failure_raises_without_debug_prints(self):
        stream = io.StringIO()

        with patch("models.httpx.AsyncClient", self._failing_async_client(502, {"error": "upstream overloaded"})), \
             contextlib.redirect_stdout(stream), \
             self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(models._call_anthropic_compat(
                "secret-api-key",
                "https://anthropic-proxy.example.com/v1",
                "claude-proxy-model",
                "prompt",
                "base64-image-payload",
                "image/png",
            ))

        output = stream.getvalue()
        self.assertEqual(output, "")
        self.assertNotIn("secret-api-key", output)
        self.assertNotIn("base64-image-payload", output)
