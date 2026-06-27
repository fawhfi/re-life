import unittest

from weather import build_header_weather_payload, map_weather_icon_to_emoji


class WeatherTests(unittest.TestCase):
    def test_hko_icon_codes_map_to_weather_emoji(self):
        self.assertEqual(map_weather_icon_to_emoji(60), "☁️")
        self.assertEqual(map_weather_icon_to_emoji(65), "⛈️")
        self.assertEqual(map_weather_icon_to_emoji(None), "🌤️")

    def test_build_header_weather_payload_prefers_nearby_station(self):
        report = {
            "icon": [63],
            "updateTime": "2026-06-27T20:02:00+08:00",
            "iconUpdateTime": "2026-06-27T18:00:00+08:00",
            "temperature": {
                "recordTime": "2026-06-27T20:00:00+08:00",
                "data": [
                    {"place": "Hong Kong Observatory", "value": 29, "unit": "C"},
                    {"place": "Sai Kung", "value": 28, "unit": "C"},
                ],
            },
            "humidity": {
                "recordTime": "2026-06-27T20:00:00+08:00",
                "data": [{"place": "Hong Kong Observatory", "value": 84, "unit": "percent"}],
            },
        }

        payload = build_header_weather_payload(report, latitude=22.3829, longitude=114.2701)

        self.assertEqual(payload["emoji"], "🌧️")
        self.assertEqual(payload["temperature"], 28)
        self.assertEqual(payload["location"], "Sai Kung")
        self.assertEqual(payload["temperature_place"], "Sai Kung")
        self.assertEqual(payload["source"], "HKO Open Data")

    def test_build_header_weather_payload_uses_hong_kong_fallback_without_location(self):
        report = {
            "icon": [60],
            "updateTime": "2026-06-27T20:02:00+08:00",
            "temperature": {
                "recordTime": "2026-06-27T20:00:00+08:00",
                "data": [
                    {"place": "Hong Kong Observatory", "value": 29, "unit": "C"},
                    {"place": "Sai Kung", "value": 28, "unit": "C"},
                ],
            },
            "humidity": {
                "recordTime": "2026-06-27T20:00:00+08:00",
                "data": [{"place": "Hong Kong Observatory", "value": 84, "unit": "percent"}],
            },
        }

        payload = build_header_weather_payload(report)

        self.assertEqual(payload["emoji"], "☁️")
        self.assertEqual(payload["temperature"], 29)
        self.assertEqual(payload["location"], "Hong Kong")
        self.assertEqual(payload["temperature_place"], "Hong Kong Observatory")
