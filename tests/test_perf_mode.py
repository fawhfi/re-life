from pathlib import Path
import unittest


class PerformanceModeTests(unittest.TestCase):
    def test_low_end_mode_is_wired_into_templates(self):
        index = Path("templates/index.html").read_text(encoding="utf-8")
        login = Path("templates/login.html").read_text(encoding="utf-8")
        register = Path("templates/register.html").read_text(encoding="utf-8")

        for html in (index, login, register):
            self.assertIn("perf-lite", html)
            self.assertNotIn("hardwareConcurrency", html)

    def test_motion_heavy_paths_use_lightweight_gates(self):
        style = Path("static/style.css").read_text(encoding="utf-8")
        utils = Path("static/js/utils.js").read_text(encoding="utf-8")
        app = Path("static/app.js").read_text(encoding="utf-8")
        records = Path("static/js/app-records.js").read_text(encoding="utf-8")

        self.assertIn("window.RELIFE_PERF", utils)
        self.assertNotIn("hardwareConcurrency", utils)
        self.assertIn("MOTION_ENABLED", app)
        self.assertIn("loading=\"lazy\"", records)
        self.assertIn("decoding=\"async\"", records)
        self.assertIn("html.perf-lite", style)
        self.assertIn("will-change: transform", style)
        self.assertNotIn("html.perf-lite nav.nav", style)
        self.assertNotIn("html.perf-lite .app-nav", style)
        self.assertNotIn("html.perf-lite .nav-indicator", style)
        self.assertNotIn("html.perf-lite .nav-btn.is-active .nav-btn-icon", style)
        self.assertNotIn("html.perf-lite .nav-btn--pop .nav-btn-icon", style)
        self.assertNotIn("html.perf-lite .nav-btn-icon {\n    will-change: auto;\n    transform: none;", style)
        self.assertNotIn("will-change: left, width", style)
        self.assertNotIn("transition: left 0.4s", style)
        self.assertNotIn("void el.offsetWidth", app)
