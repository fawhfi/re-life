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
        self.assertIn("/static/js/app-weather.js", home.text)
        self.assertIn("/static/js/app-records.js", home.text)
        self.assertIn("/static/supabase.js", home.text)
        self.assertNotIn("/static/firebase.js", home.text)
        self.assertIn("gsap.min.js", home.text)
        self.assertNotIn('gsap@3.12.5/dist/gsap.min.js" defer', home.text)
        self.assertLess(
            home.text.index("gsap.min.js"),
            home.text.index("/static/app.js"),
        )
        self.assertLess(home.text.index("/static/app.js"), home.text.index("/static/js/app-weather.js"))
        self.assertLess(home.text.index("/static/js/app-weather.js"), home.text.index("/static/js/app-records.js"))

    def test_header_permissions_policy_keeps_optional_geolocation(self):
        home = self.client.get("/")
        policy = home.headers.get("permissions-policy", "")

        self.assertIn("geolocation=(self)", policy)

    def test_geolocation_prompt_is_not_blocked_by_permissions_api(self):
        app_js = Path("static/js/app-weather.js").read_text(encoding="utf-8")

        self.assertIn("async function resolveWeatherCoordinates(forcePrompt = false)", app_js)
        self.assertIn("if (!forcePrompt && navigator.permissions && navigator.permissions.query)", app_js)
        self.assertIn("async function refreshHeaderWeather()", app_js)
        self.assertIn("commitHeaderWeather(requestId, true)", app_js)
        self.assertIn("permission.state === 'denied'", app_js)
        self.assertIn("navigator.geolocation.getCurrentPosition(", app_js)

    def test_glass_surfaces_are_not_forced_into_composited_layers(self):
        style = Path("static/style.css").read_text(encoding="utf-8")

        self.assertNotIn(
            ".card, .scan-btn, .tab, .modal, .nav-btn-icon {",
            style,
        )
        self.assertIn(".scan-btn, .nav-btn-icon {", style)

    def test_weather_details_panel_is_wired_into_the_template(self):
        template = Path("templates/index.html").read_text(encoding="utf-8")
        app_js = Path("static/app.js").read_text(encoding="utf-8")
        weather_js = Path("static/js/app-weather.js").read_text(encoding="utf-8")
        en_i18n = Path("static/i18n/en.json").read_text(encoding="utf-8")
        zh_i18n = Path("static/i18n/zh_simplified.json").read_text(encoding="utf-8")
        zh_traditional_i18n = Path("static/i18n/zh_traditional.json").read_text(encoding="utf-8")
        style = Path("static/style.css").read_text(encoding="utf-8")
        theme = Path("static/css/theme.css").read_text(encoding="utf-8")

        self.assertIn('id="weather-overlay"', template)
        self.assertIn('id="weather-panel"', template)
        self.assertIn('onclick="toggleWeatherDetails()"', template)
        self.assertIn('id="weather-detail-callout-title"', template)
        self.assertIn('id="lbl-weather-temperature"', template)
        self.assertIn('id="lbl-weather-location"', template)
        self.assertIn('id="lbl-weather-updated"', template)
        self.assertIn('id="lbl-weather-source"', template)
        self.assertIn('id="lbl-weather-close"', template)
        self.assertIn('weather-panel-stat--primary', template)
        self.assertIn('weather-panel-stat--meta', template)
        self.assertIn('function toggleWeatherDetails()', weather_js)
        self.assertIn('function openWeatherDetails()', weather_js)
        self.assertIn('function closeWeatherDetails()', weather_js)
        self.assertNotIn('function toggleWeatherDetails()', app_js)
        self.assertNotIn('async function resolveWeatherCoordinates(forcePrompt = false)', app_js)
        self.assertLess(app_js.index('loadTips();'), app_js.index('await initAccounts();'))
        self.assertIn('NEWS_CACHE_KEY', app_js)
        self.assertIn('applyTips(NEWS_FALLBACK_ITEMS)', app_js)
        self.assertIn('AbortController', app_js)
        self.assertNotIn('WEATHER_SUMMARY_TEXT', app_js)
        self.assertNotIn('WEATHER_CALLOUT_TEXT', app_js)
        self.assertIn('localizeWeatherSummary', weather_js)
        self.assertIn('localizeWeatherCallout', weather_js)
        self.assertIn('"weather": {', en_i18n)
        self.assertIn('"weather": {', zh_i18n)
        self.assertIn('"weather": {', zh_traditional_i18n)
        self.assertIn('"tapForDetails": "Tap for details"', en_i18n)
        self.assertIn('"tapForDetails": "轻触查看详情"', zh_i18n)
        self.assertIn('"tapForDetails": "輕觸查看詳情"', zh_traditional_i18n)
        self.assertIn("weather.detail.temperature", app_js)
        self.assertIn("weather.detail.close", app_js)
        self.assertIn('.weather-panel-stat--primary .weather-panel-stat-value', style)
        self.assertIn('[data-theme="midnight"] .weather-panel', theme)
        self.assertIn('[data-theme="midnight"] .weather-panel-callout-body', theme)
