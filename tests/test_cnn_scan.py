from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from models import classifier_response
from main import app
from nlp import build_tokenizer


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

    def test_scan_endpoint_returns_transformer_text_and_tokens(self):
        sample_dir = Path(__file__).resolve().parents[2] / "cnn_classifier" / "src" / "data" / "test" / "paper"
        sample = next(
            path for path in sorted(sample_dir.iterdir())
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

        with sample.open("rb") as image_file:
            response = self.client.post(
                "/api/scan/ai",
                files={"file": (sample.name, image_file, "image/jpeg")},
                data={"mode": "dispose", "item_type": "food", "item_state": "new", "debug": "false"},
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
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

    def test_tokenizer_vocab_expanded(self):
        tokenizer = build_tokenizer()

        self.assertGreaterEqual(tokenizer.vocab_size, 80)

    def test_scan_ui_no_longer_allows_score_dragging(self):
        app = Path("static/app.js").read_text(encoding="utf-8")
        template = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("item.classifier_source === 'cnn'", app)
        self.assertIn("item.text || item.description", app)
        self.assertNotIn("toggleWS()", app)
        self.assertNotIn("startBarDrag", app)
        self.assertNotIn("updateBarFromEvent", app)
        self.assertNotIn("stopBarDrag", app)
        self.assertNotIn("weighted-toggle", template)
