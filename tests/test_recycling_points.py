from unittest.mock import AsyncMock, patch
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from main import app


SAMPLE_RECYCLING_HTML = """
<div class="views-row">
  <div class="accordion-header">
    <button class="accordion-button collapsed">政府總部</button>
  </div>
  <div class="accordion-body">
    <div class="field field--name-name field--type-string field--label-hidden field__item">非物料名稱</div>
    <div class="direction"><a href="https://www.google.com/maps?daddr=22.280255,114.165827">導航</a></div>
    <div class="details"><a href="https://www.wastereduction.gov.hk/zh-hk/recycling-point/central-government-offices">詳情</a></div>
    <div class="remark"><p class="openhour">時間: 00:00 - 23:59</p></div>
    <div class="recyclables">
      <div class="field field--name-name field--type-string field--label-hidden field__item">金屬</div>
      <div class="field field--name-name field--type-string field--label-hidden field__item">廢紙</div>
      <div class="field field--name-name field--type-string field--label-hidden field__item">塑膠</div>
    </div>
    <div class="accessibility">註: 供公眾使用</div>
  </div>
</div>
<div class="views-row">
  <div class="accordion-header">
    <a class="accordion-button collapsed">添馬公園</a>
  </div>
  <div class="accordion-body">
    <div class="direction"><a href="https://www.google.com/maps?daddr=22.279987%2C114.165777">導航</a></div>
    <div class="details"><a href="https://www.wastereduction.gov.hk/zh-hk/recycling-point/tamar-park">詳情</a></div>
    <div class="recyclables">
      <div class="field field--name-name field--type-string field--label-hidden field__item">膠樽</div>
      <div class="field field--name-name field--type-string field--label-hidden field__item">塑膠</div>
    </div>
    <div class="accessibility">註: 供公眾使用</div>
  </div>
</div>
"""


class RecyclingPointParserTests(unittest.TestCase):
    def test_parse_recycling_map_rows_extracts_sorted_nearby_points(self):
        from recycling_points import parse_recycling_points_html

        points = parse_recycling_points_html(SAMPLE_RECYCLING_HTML, latitude=22.280255, longitude=114.165827, limit=2)

        self.assertEqual([point["name"] for point in points], ["政府總部", "添馬公園"])
        self.assertEqual(points[0]["materials"], ["金屬", "廢紙", "塑膠"])
        self.assertEqual(points[0]["maps_url"], "https://www.google.com/maps?daddr=22.280255,114.165827")
        self.assertEqual(points[0]["detail_url"], "https://www.wastereduction.gov.hk/zh-hk/recycling-point/central-government-offices")
        self.assertEqual(points[0]["open_hours"], "時間: 00:00 - 23:59")
        self.assertLess(points[0]["distance_m"], points[1]["distance_m"])

    def test_material_names_map_to_official_recycling_map_facets(self):
        from recycling_points import material_to_recycling_map_facets

        self.assertEqual(material_to_recycling_map_facets("plastic"), ["material:2023"])
        self.assertEqual(material_to_recycling_map_facets("pp_plastic bottle"), ["material:2024"])
        self.assertEqual(material_to_recycling_map_facets("塑膠"), ["material:2023"])
        self.assertEqual(material_to_recycling_map_facets("膠樽"), ["material:2024"])
        self.assertEqual(material_to_recycling_map_facets("玻璃樽"), ["material:2025"])
        self.assertEqual(material_to_recycling_map_facets("廢紙"), ["material:2021"])
        self.assertEqual(material_to_recycling_map_facets("金屬"), ["material:2022"])
        self.assertEqual(material_to_recycling_map_facets("paper"), ["material:2021"])
        self.assertEqual(material_to_recycling_map_facets("metal can"), ["material:2022"])
        self.assertEqual(material_to_recycling_map_facets("glass"), ["material:2025"])
        self.assertEqual(material_to_recycling_map_facets("bottle"), [])

    def test_build_recycling_map_url_uses_location_distance_and_material(self):
        from recycling_points import build_recycling_map_url

        url = build_recycling_map_url(22.280255, 114.165827, material="plastic", distance_km=3)

        self.assertIn("https://www.wastereduction.gov.hk/zh-hk/recycling-map?", url)
        self.assertIn("latlon%5Blat%5D=22.280255", url)
        self.assertIn("latlon%5Blng%5D=114.165827", url)
        self.assertIn("latlon%5Bdistance%5D%5Bfrom%5D=3", url)
        self.assertIn("f%5B0%5D=material%3A2023", url)


class RecyclingPointEndpointTests(unittest.TestCase):
    def test_nearby_recycling_endpoint_returns_points_and_source(self):
        payload = {
            "points": [{"name": "政府總部", "distance_m": 0, "materials": ["塑膠"]}],
            "source_url": "https://www.wastereduction.gov.hk/zh-hk/recycling-map?x=1",
            "source": "wastereduction.gov.hk",
        }

        with patch("main.check_rate_limit", new=AsyncMock(return_value=None)), \
             patch("main.find_nearby_recycling_points", new=AsyncMock(return_value=payload)) as finder:
            response = TestClient(app).get("/api/recycling/nearby?lat=22.280255&lon=114.165827&material=plastic")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        finder.assert_awaited_once_with(22.280255, 114.165827, material="plastic", limit=5, distance_km=3)

    def test_nearby_recycling_endpoint_rejects_invalid_coordinates(self):
        response = TestClient(app).get("/api/recycling/nearby?lat=200&lon=114.165827")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Valid Hong Kong coordinates required")

    def test_nearby_recycling_endpoint_clamps_limit_and_distance(self):
        payload = {"points": [], "source_url": "https://www.wastereduction.gov.hk/zh-hk/recycling-map", "source": "wastereduction.gov.hk"}

        with patch("main.check_rate_limit", new=AsyncMock(return_value=None)), \
             patch("main.find_nearby_recycling_points", new=AsyncMock(return_value=payload)) as finder:
            response = TestClient(app).get("/api/recycling/nearby?lat=22.3&lon=114.2&limit=99&distance_km=99")

        self.assertEqual(response.status_code, 200)
        finder.assert_awaited_once_with(22.3, 114.2, material=None, limit=8, distance_km=10)

    def test_nearby_recycling_endpoint_reports_upstream_failure(self):
        with patch("main.check_rate_limit", new=AsyncMock(return_value=None)), \
             patch("main.find_nearby_recycling_points", new=AsyncMock(side_effect=RuntimeError("timeout"))):
            response = TestClient(app).get("/api/recycling/nearby?lat=22.3&lon=114.2")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Recycling map unavailable")


class RecyclingPointFrontendTests(unittest.TestCase):
    def test_scan_result_wires_nearby_recycling_points_ui(self):
        template = Path("templates/index.html").read_text(encoding="utf-8")
        app_js = Path("static/app.js").read_text(encoding="utf-8")
        recycling_js = Path("static/js/app-recycling.js").read_text(encoding="utf-8")
        style = Path("static/style.css").read_text(encoding="utf-8")
        theme = Path("static/css/theme.css").read_text(encoding="utf-8")
        en_i18n = Path("static/i18n/en.json").read_text(encoding="utf-8")
        zh_i18n = Path("static/i18n/zh.json").read_text(encoding="utf-8")

        self.assertIn('id="nearby-recycling"', template)
        self.assertIn("/static/js/app-recycling.js", template)
        self.assertLess(template.index('id="disp-guide"'), template.index('id="nearby-recycling"'))
        self.assertLess(template.index('id="nearby-recycling"'), template.index('id="disp-prec"'))
        self.assertLess(template.index("/static/js/app-weather.js"), template.index("/static/js/app-recycling.js"))
        self.assertLess(template.index("/static/js/app-recycling.js"), template.index("/static/js/app-records.js"))
        self.assertIn("nearbyRecyclingPoints: []", app_js)
        self.assertIn("state.nearbyRecyclingPoints", recycling_js)
        self.assertIn("resetNearbyRecyclingUI();", app_js)
        self.assertIn("loadNearbyRecyclingPointsForScan(item);", app_js)
        self.assertIn("async function loadNearbyRecyclingPointsForScan(item)", recycling_js)
        self.assertIn("resolveWeatherCoordinates(true)", recycling_js)
        self.assertIn("/api/recycling/nearby", recycling_js)
        self.assertIn("new URLSearchParams", recycling_js)
        self.assertIn("state.nearbyRecyclingRequestId", recycling_js)
        self.assertIn("requestId !== state.nearbyRecyclingRequestId", recycling_js)
        self.assertIn("renderNearbyRecyclingPoints", recycling_js)
        self.assertIn("recycling.nearbyTitle", recycling_js)
        self.assertIn("recycling.locationUnavailable", recycling_js)
        self.assertIn("recycling.unavailable", recycling_js)
        self.assertIn('"recycling": {', en_i18n)
        self.assertIn('"recycling": {', zh_i18n)
        self.assertIn('"navigate": "Navigate"', en_i18n)
        self.assertIn('"navigate": "導航"', zh_i18n)
        self.assertIn(".nearby-recycling", style)
        self.assertIn(".nearby-recycling-card", style)
        self.assertIn(".nearby-recycling-actions a", style)
        self.assertIn("@media (max-width: 380px)", style)
        self.assertIn('[data-theme="dark"] .nearby-recycling', theme)
        self.assertIn('[data-theme="midnight"] .nearby-recycling-card', theme)
