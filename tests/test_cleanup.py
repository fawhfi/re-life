from pathlib import Path
import unittest


class CleanupTests(unittest.TestCase):
    def test_legacy_cloudflare_trees_removed(self):
        self.assertFalse(Path("frontend").exists())
        self.assertFalse(Path("functions").exists())
        self.assertFalse(Path("CLOUDFLARE.md").exists())

    def test_main_no_cloudflare_origins(self):
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertNotIn("web.app", source)
        self.assertNotIn("firebaseapp.com", source)
