from pathlib import Path
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class ConfigRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_config_route_returns_expected_keys(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json().keys()),
            {
                "supabaseUrl",
                "supabasePublishableKey",
                "supabaseAnonKey",
            },
        )

    def test_config_route_reads_system_env(self):
        overrides = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "test-publishable-key",
        }
        with patch.dict(os.environ, overrides, clear=False):
            response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "supabaseUrl": "https://example.supabase.co",
            "supabasePublishableKey": "test-publishable-key",
            "supabaseAnonKey": "test-publishable-key",
        })

    def test_main_no_html_injection_helper(self):
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertNotIn("_inject_firebase_config", source)
        self.assertNotIn("window.FIREBASE_CONFIG", source)
