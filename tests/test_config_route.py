from pathlib import Path
import importlib
import os
import unittest
from unittest.mock import patch

import config
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

    def test_custom_endpoint_env_adds_custom_ai_model(self):
        overrides = {
            "CUSTOM_BASE_URL": "https://llm.example.com/v1",
            "CUSTOM_API": "custom-key",
            "CUSTOM_ENDPOINT_MODEL": "vision-model",
            "CUSTOM_ENDPOINT_METHOD": "openai",
            "DEFAULT_AI_MODEL": "custom",
        }

        try:
            with patch.dict(os.environ, overrides, clear=True):
                reloaded = importlib.reload(config)
                self.assertIn("custom", reloaded.AVAILABLE_MODELS)
                self.assertEqual(reloaded.DEFAULT_AI_MODEL, "custom")
                self.assertEqual(reloaded.CUSTOM_METHOD, "openai")
        finally:
            importlib.reload(config)

    def test_custom_endpoint_debug_script_is_available(self):
        source = Path("scripts/debug_custom_endpoint.py").read_text(encoding="utf-8")

        self.assertIn("CUSTOM_BASE_URL", source)
        self.assertIn("CUSTOM_ENDPOINT_METHOD", source)
        self.assertIn("body_preview", source)
        self.assertIn('api_key="SET"', source)
        self.assertIn("--probe-paths", source)
        self.assertIn("candidate_base_urls", source)
        self.assertNotIn("print(api_key", source)

    def test_main_no_html_injection_helper(self):
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertNotIn("_inject_firebase_config", source)
        self.assertNotIn("window.FIREBASE_CONFIG", source)
