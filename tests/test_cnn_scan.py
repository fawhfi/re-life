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
from nlp.infer import DEFAULT_MODEL_PATH, predict_image
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

    def test_local_nlp_predict_image_uses_prompted_text(self):
        sample_dir = Path(__file__).resolve().parents[2] / "cnn_classifier" / "src" / "data" / "test" / "plastic"
        sample = next(
            path for path in sorted(sample_dir.iterdir())
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

        result = predict_image(sample, prompt="Return JSON with disposal and reuse_tip.")

        self.assertEqual(result["runtime_source"], "onnxruntime")
        self.assertEqual(result["artifact"], "model_fp16.onnx")
        self.assertTrue(result["text"].startswith("{"))
        self.assertIn('"waste_type"', result["text"])
        self.assertIn('"reuse_tip"', result["text"])

    def test_scan_endpoint_passes_prompt_to_local_transformer(self):
        local_result = {
            "name": "Plastic",
            "brand": "",
            "category": "plastic",
            "waste_type": "plastic",
            "waste_label": "Plastic",
            "classifier_source": "nlp",
            "model_source": "transformer",
            "runtime_source": "onnxruntime",
            "artifact": "model_fp16.onnx",
            "text": '{"waste_type":"plastic","disposal":"rinse recycle plastic","reuse_tip":"refill or planter"}',
            "tokens": ["{", "waste_type", "plastic", "reuse_tip"],
            "confidence": 0.99,
            "standard_type": "general",
            "description": "",
            "material": "plastic",
            "eco_rate": 2,
            "recycle_rate": 3,
            "weighted_scores": {"a": 80, "b": 80, "c": 80, "d": 80, "e": 80},
            "disposal_guide": "Rinse and recycle.",
            "precaution": "",
            "alternative": None,
        }

        with patch("main.local_scan_response", return_value=local_result) as local_mock:
            response = self.client.post(
                "/api/scan/ai",
                files={"file": ("sample.jpg", b"fake image bytes", "image/jpeg")},
                data={
                    "mode": "dispose",
                    "item_type": "food",
                    "item_state": "new",
                    "debug": "true",
                    "prompt": "Return JSON with disposal and reuse_tip.",
                },
            )

        self.assertEqual(response.status_code, 200)
        local_mock.assert_called_once()
        self.assertEqual(local_mock.call_args.args[2], "Return JSON with disposal and reuse_tip.")

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

    def test_scan_endpoint_passes_language_to_remote_llm(self):
        remote_result = {
            "name": "膠樽",
            "brand": "",
            "category": "beverage",
            "description": "遠端模型以中文回覆。",
            "material": "plastic",
            "eco_rate": 2,
            "recycle_rate": 3,
            "standard_type": "general",
            "weighted_scores": {"a": 81, "b": 77, "c": 73, "d": 69, "e": 85},
            "alternative": None,
            "waste_type": "plastic",
            "waste_label": "Plastic",
            "text": "遠端模型以中文回覆。",
            "classifier_source": "openai",
            "model_source": "gpt-4o-mini",
            "runtime_source": "remote",
            "artifact": "gpt-4o-mini",
            "confidence": 0.91,
        }

        with patch("main.ai_analyze", new=AsyncMock(return_value=remote_result)) as remote_mock:
            response = self.client.post(
                "/api/scan/ai",
                files={"file": ("sample.jpg", b"fake image bytes", "image/jpeg")},
                data={"mode": "dispose", "item_type": "food", "item_state": "new", "debug": "false", "lang": "zh_simplified"},
            )

        self.assertEqual(response.status_code, 200)
        remote_mock.assert_awaited_once()
        self.assertEqual(remote_mock.await_args.args[2], "zh_simplified")

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

    def test_ai_prompt_requests_grounded_actionable_scan_details(self):
        source = Path("models.py").read_text(encoding="utf-8")

        self.assertIn("do not invent a brand", source.lower())
        self.assertIn("Hong Kong recycling or disposal route", source)
        self.assertIn("material-specific", source)
        self.assertIn('"reuseTip"', source)
        self.assertIn('"reuse_tip": j.get("reuseTip", "")', source)
        self.assertIn("integer 0-100", source)

    def test_scan_request_sends_selected_language(self):
        source = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn("fd.append('lang', state.lang);", source)

    def test_navbar_has_polished_selected_motion(self):
        app = Path("static/app.js").read_text(encoding="utf-8")
        style = Path("static/style.css").read_text(encoding="utf-8")
        theme = Path("static/css/theme.css").read_text(encoding="utf-8")
        template = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("nav.classList.add('nav-btn--pop')", app)
        self.assertIn("setTimeout(() => nav.classList.remove('nav-btn--pop')", app)
        self.assertIn(".nav-btn.is-active .nav-btn-icon", style)
        self.assertIn("scale(1.12)", style)
        self.assertIn("navSelectedPop", style)
        self.assertIn('id="nav-shell-clip"', template)
        self.assertIn('id="nav-shell-clip-path"', template)
        self.assertIn('class="nav-shell-svg"', template)
        self.assertIn('id="nav-shell-path"', template)
        self.assertIn("--nav-shell-radius: 24px", style)
        self.assertIn("--nav-indicator-inset: 5px", style)
        self.assertIn("--nav-arch: 8px", style)
        self.assertIn("--nav-lift: 10px", style)
        self.assertIn("--nav-bulge-active: 8px", style)
        self.assertIn("--nav-indicator-y-offset: 0px", style)
        self.assertIn("--nav-indicator-window-width: 80px", style)
        self.assertIn("--nav-indicator-window-height: 42px", style)
        self.assertIn("--nav-indicator-hold-width: 90px", style)
        self.assertIn("--nav-indicator-hold-height: 48px", style)
        self.assertIn("--nav-shell-safe-inset: 2px", style)
        self.assertIn("--nav-shell-x-bleed: 0px", style)
        self.assertIn("--nav-indicator-bg:", style)
        self.assertIn("--nav-indicator-bg-active:", style)
        self.assertIn("--nav-indicator-ring:", style)
        self.assertIn("--nav-indicator-shadow:", style)
        self.assertIn("--nav-shell-shadow:", style)
        self.assertIn("drop-shadow(0 8px 18px rgba(0,0,0,0.20))", style)
        self.assertIn("fill: transparent;", style)
        self.assertIn("stroke: transparent;", style)
        self.assertIn("stroke-width: 0;", style)
        self.assertIn("width: calc(100% - 36px)", style)
        self.assertIn("max-width: 392px", style)
        self.assertIn("--nav-indicator-radius: calc(var(--nav-shell-radius) - var(--nav-indicator-inset))", style)
        self.assertIn("--nav-indicator-hold-radius: var(--nav-indicator-radius)", style)
        self.assertRegex(
            style,
            r"nav\.nav::before, \.app-nav::before \{[\s\S]*backdrop-filter: blur\(20px\) brightness\(1\.15\) saturate\(150%\);",
        )
        self.assertRegex(
            style,
            r"nav\.nav, \.app-nav \{[\s\S]*box-shadow:\s*none;",
        )
        self.assertRegex(
            style,
            r"nav\.nav::before, \.app-nav::before \{[\s\S]*clip-path: url\(#nav-shell-clip\);",
        )
        self.assertRegex(
            style,
            r"nav\.nav::before, \.app-nav::before \{[\s\S]*filter: var\(--nav-shell-shadow\);",
        )
        self.assertNotRegex(style, r"nav\.nav, \.app-nav \{[^}]*box-shadow:\s*0 4px 24px")
        self.assertNotRegex(style, r"nav\.nav, \.app-nav \{[^}]*clip-path: url\(#nav-shell-clip\);")
        self.assertIn(".nav-shell-svg", style)
        self.assertRegex(style, r"\.nav-shell-svg \{[\s\S]*overflow: visible;")
        self.assertNotRegex(style, r"\.nav-shell-svg \{[^}]*filter: var\(--nav-shell-shadow\);")
        self.assertIn(".nav-indicator::after", style)
        self.assertIn("width: 100%;", style)
        self.assertIn(".nav-is-holding .nav-indicator,", style)
        self.assertIn("function getIndicatorWidth", app)
        self.assertIn("function getIndicatorYOffset", app)
        self.assertIn("function getNavShellSafeInset", app)
        self.assertIn("function getNavShellXBleed", app)
        self.assertIn("function smoothstep", app)
        self.assertIn("function applyEdgeCompression", app)
        self.assertIn("const startX = -horizontalBleed;", app)
        self.assertIn("getCssPx('--nav-shell-x-bleed', 0)", app)
        self.assertIn("const width = getIndicatorWidth(isHolding);", app)
        self.assertIn("const x = clamp(center - width / 2, edge, maxX) - edge;", app)
        self.assertIn("mesh.centerY - getIndicatorYOffset()", app)
        self.assertIn("border-radius: var(--nav-indicator-radius)", style)
        self.assertIn("border-radius: var(--nav-indicator-hold-radius)", style)
        self.assertIn("background: var(--nav-indicator-bg);", style)
        self.assertIn("background: var(--nav-indicator-bg-active);", style)
        self.assertIn("inset 0 -1px 0 var(--nav-indicator-ring)", style)
        self.assertIn("0 1px 5px var(--nav-indicator-shadow)", style)
        self.assertNotIn("0 6px 18px var(--nav-indicator-shadow)", style)
        self.assertIn("[data-theme=\"forest\"] nav.nav", theme)
        self.assertIn("--nav-indicator-ring: rgba(45,90,30,0.26);", theme)
        self.assertIn("[data-theme=\"ocean\"] nav.nav", theme)
        self.assertIn("--nav-indicator-ring: rgba(26,74,106,0.24);", theme)
        self.assertIn("[data-theme=\"sunset\"] nav.nav", theme)
        self.assertIn("--nav-indicator-ring: rgba(138,58,42,0.24);", theme)
        self.assertIn("function generateNavShellPath", app)
        self.assertIn("function drawNavShell", app)
        self.assertIn("const yLimit = mesh.height - safeInset;", app)
        self.assertIn("liquidShell.setBulge(getCssPx('--nav-bulge-active', 8));", app)
        self.assertIn("navbar.classList.add('nav-is-holding');", app)
        self.assertIn("navbar.classList.remove('nav-is-holding', 'nav-is-dragging');", app)
        self.assertIn("--nav-indicator-radius: calc(var(--nav-indicator-window-height) / 2);", theme)
        self.assertIn("--nav-indicator-hold-radius: calc(var(--nav-indicator-hold-height) / 2);", theme)
        self.assertNotIn("--nav-indicator-y-offset: 3px;", theme)
        self.assertIn("[data-theme=\"midnight\"] .nav-indicator", theme)
        self.assertRegex(theme, r"\[data-theme=\"dark\"\] nav\.nav,[\s\S]*box-shadow:\s*none;")
        self.assertRegex(theme, r"\[data-theme=\"dark\"\] nav\.nav,[\s\S]*border:\s*0;")
        self.assertRegex(style, r"\[data-theme=\"dark\"\] nav\.nav,[\s\S]*border:\s*0;")
        self.assertNotRegex(
            style,
            r"\[data-theme=\"dark\"\] \.app-header,\s*\[data-theme=\"dark\"\] nav\.nav,[\s\S]*border:\s*1px solid rgba\(255, 255, 255, 0\.06\);",
        )
        self.assertIn("drop-shadow(0 8px 18px rgba(0,0,0,0.32))", theme)
        self.assertNotIn("stroke: rgba(255,255,255,0.06)", theme)
        self.assertNotIn("drop-shadow(0 1px 0", style)
        self.assertNotIn("drop-shadow(0 1px 0", theme)
        self.assertNotIn("inset 0 -2px 10px", theme)
        self.assertNotIn("x = 0;", app)
        self.assertNotIn("scale(1.28)", style)
        self.assertNotIn("scale(1.38)", style)

    def test_grade_tags_use_white_text_on_colored_backgrounds(self):
        style = Path("static/style.css").read_text(encoding="utf-8")
        theme = Path("static/css/theme.css").read_text(encoding="utf-8")

        self.assertRegex(style, r"\.grade-tag \{[\s\S]*color:\s*#fff;")
        self.assertRegex(theme, r"\[data-theme=\"dark\"\] \.grade-tag,[\s\S]*\[data-theme=\"midnight\"\] \.grade-tag \{[\s\S]*color:\s*#fff;")

    def test_alternative_product_card_is_prominent(self):
        style = Path("static/style.css").read_text(encoding="utf-8")

        self.assertRegex(style, r"\.alternative-card \{[\s\S]*padding:\s*18px 16px;")
        self.assertRegex(style, r"\.alternative-card \{[\s\S]*min-height:\s*104px;")
        self.assertRegex(style, r"\.alternative-card-name \{[\s\S]*font-size:\s*16px;")
        self.assertRegex(style, r"\.alternative-card-ratings \{[\s\S]*gap:\s*18px;")

    def test_ai_analyze_adds_simplified_chinese_instruction_for_zh_simplified_language(self):
        with patch("models.DEFAULT_AI_MODEL", "custom"), \
             patch("models.CUSTOM_METHOD", "openai"), \
             patch("models.CUSTOM_API_KEY", "custom-key"), \
             patch("models.CUSTOM_BASE_URL", "https://llm.example.com/v1"), \
             patch("models.CUSTOM_MODEL", "vision-model"), \
             patch("models._compress_image", return_value=(b"compressed", "image/png")), \
             patch("models._call_openai_compat", new=AsyncMock(return_value=self._remote_json())) as custom_mock:
            asyncio.run(ai_analyze(b"image-bytes", "sid-custom", language="zh_simplified"))

        prompt = custom_mock.await_args.args[3]
        self.assertIn("Simplified Chinese", prompt)
        self.assertIn("zh-CN", prompt)
        self.assertIn("Keep JSON property names", prompt)
        self.assertIn("human-readable JSON string values", prompt)

    def test_ai_analyze_adds_traditional_chinese_instruction_for_zh_traditional_language(self):
        with patch("models.DEFAULT_AI_MODEL", "custom"), \
             patch("models.CUSTOM_METHOD", "openai"), \
             patch("models.CUSTOM_API_KEY", "custom-key"), \
             patch("models.CUSTOM_BASE_URL", "https://llm.example.com/v1"), \
             patch("models.CUSTOM_MODEL", "vision-model"), \
             patch("models._compress_image", return_value=(b"compressed", "image/png")), \
             patch("models._call_openai_compat", new=AsyncMock(return_value=self._remote_json())) as custom_mock:
            asyncio.run(ai_analyze(b"image-bytes", "sid-custom", language="zh_traditional"))

        prompt = custom_mock.await_args.args[3]
        self.assertIn("Traditional Chinese", prompt)
        self.assertIn("zh-HK", prompt)
        self.assertIn("Keep JSON property names", prompt)
        self.assertIn("human-readable JSON string values", prompt)


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
