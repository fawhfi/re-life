from pathlib import Path
import unittest

from models import classifier_response


class CnnScanTests(unittest.TestCase):
    def test_classifier_response_uses_waste_type_label(self):
        result = classifier_response("paper", 0.91, "dispose")

        self.assertEqual(result["classifier_source"], "cnn")
        self.assertEqual(result["waste_type"], "paper")
        self.assertEqual(result["name"], "Paper")
        self.assertEqual(result["description"], "")
        self.assertIsNone(result["alternative"])

    def test_scan_ui_no_longer_allows_score_dragging(self):
        app = Path("static/app.js").read_text(encoding="utf-8")
        template = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("item.classifier_source === 'cnn'", app)
        self.assertNotIn("toggleWS()", app)
        self.assertNotIn("startBarDrag", app)
        self.assertNotIn("updateBarFromEvent", app)
        self.assertNotIn("stopBarDrag", app)
        self.assertNotIn("weighted-toggle", template)
