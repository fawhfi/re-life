from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from main import app


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_api_index_shim_removed(self):
        self.assertFalse(Path("api/index.py").exists())

    def test_pages_render_and_keep_gsap(self):
        home = self.client.get("/")
        login = self.client.get("/login")
        register = self.client.get("/register")
        schemas = self.client.get("/api/schemas")
        config = self.client.get("/api/config")

        self.assertEqual(home.status_code, 200)
        self.assertEqual(login.status_code, 200)
        self.assertEqual(register.status_code, 200)
        self.assertEqual(schemas.status_code, 200)
        self.assertEqual(config.status_code, 200)
        self.assertIn("/static/app.js", home.text)
        self.assertIn("/static/firebase.js", home.text)
        self.assertIn("gsap.min.js", home.text)
        self.assertNotIn('gsap@3.12.5/dist/gsap.min.js" defer', home.text)
        self.assertLess(
            home.text.index("gsap.min.js"),
            home.text.index("/static/app.js"),
        )
