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
                "apiKey",
                "authDomain",
                "projectId",
                "storageBucket",
                "messagingSenderId",
                "appId",
                "databaseURL",
            },
        )

    def test_config_route_reads_system_env(self):
        overrides = {
            "FIREBASE_API_KEY": "test-api-key",
            "FIREBASE_AUTH_DOMAIN": "test-auth-domain",
            "FIREBASE_PROJECT_ID": "test-project-id",
            "FIREBASE_STORAGE_BUCKET": "test-storage-bucket",
            "FIREBASE_MESSAGING_SENDER_ID": "test-sender-id",
            "FIREBASE_APP_ID": "test-app-id",
            "FIREBASE_DATABASE_URL": "https://example.firebaseio.test",
        }
        with patch.dict(os.environ, overrides, clear=False):
            response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "apiKey": "test-api-key",
            "authDomain": "test-auth-domain",
            "projectId": "test-project-id",
            "storageBucket": "test-storage-bucket",
            "messagingSenderId": "test-sender-id",
            "appId": "test-app-id",
            "databaseURL": "https://example.firebaseio.test",
        })

    def test_main_no_html_injection_helper(self):
        source = Path("main.py").read_text(encoding="utf-8")
        self.assertNotIn("_inject_firebase_config", source)
        self.assertNotIn("window.FIREBASE_CONFIG", source)
