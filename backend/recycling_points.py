"""Nearby recycling point lookup backed by the official Hong Kong recycling map."""
from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import math
import re
from urllib.parse import unquote, urlencode

import httpx


RECYCLING_MAP_URL = "https://www.wastereduction.gov.hk/zh-hk/recycling-map"
RECYCLING_MAP_SOURCE = "wastereduction.gov.hk"
RECYCLING_MAP_TIMEOUT = 15.0

MATERIAL_FACETS = {
    "廢紙": "material:2021",
    "paper": "material:2021",
    "cardboard": "material:2021",
    "金屬": "material:2022",
    "metal": "material:2022",
    "can": "material:2022",
    "aluminium": "material:2022",
    "aluminum": "material:2022",
    "塑膠": "material:2023",
    "plastic": "material:2023",
    "pp_plastic": "material:2023",
    "玻璃樽": "material:2025",
    "glass": "material:2025",
    "膠樽": "material:2024",
    "plastic_bottle": "material:2024",
    "廚餘": "material:2033",
    "food": "material:2033",
    "organic": "material:2033",
    "compostable": "material:2033",
    "紙包飲品盒": "material:2032",
    "衣服": "material:2030",
    "小型電器": "material:2028",
    "充電池": "material:2027",
}


def material_to_recycling_map_facets(material: str | None) -> list[str]:
    text = (material or "").strip().lower().replace("-", "_")
    if not text:
        return []
    if "bottle" in text and ("plastic" in text or "pp" in text):
        return ["material:2024"]
    if "glass" in text:
        return ["material:2025"]
    if text == "bottle":
        return []
    for key, facet in MATERIAL_FACETS.items():
        if key in text:
            return [facet]
    return []


def build_recycling_map_url(latitude: float, longitude: float, *, material: str | None = None, distance_km: int = 3) -> str:
    params: list[tuple[str, str]] = [
        ("latlon[distance][from]", str(distance_km)),
        ("latlon[lat]", f"{latitude:.6f}".rstrip("0").rstrip(".")),
        ("latlon[lng]", f"{longitude:.6f}".rstrip("0").rstrip(".")),
    ]
    for facet in material_to_recycling_map_facets(material):
        params.append(("f[0]", facet))
    return f"{RECYCLING_MAP_URL}?{urlencode(params)}"


def _attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key: value or "" for key, value in attrs}


def _has_class(attrs: dict[str, str], token: str) -> bool:
    return token in attrs.get("class", "").split()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _absolute_detail_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.wastereduction.gov.hk{url}"
    return url


def _coordinates_from_maps_url(url: str) -> tuple[float, float] | None:
    decoded = unquote(url or "")
    match = re.search(r"[?&]daddr=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", decoded)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    radius_m = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return round(radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


class _RecyclingMapParser(HTMLParser):
    def __init__(self, latitude: float, longitude: float):
        super().__init__(convert_charrefs=True)
        self.latitude = latitude
        self.longitude = longitude
        self.points: list[dict] = []
        self._current: dict | None = None
        self._row_depth = 0
        self._capture_key: str | None = None
        self._capture_depth = 0
        self._capture_parts: list[str] = []
        self._recyclables_depth = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = _attrs_dict(attrs_list)
        if self._capture_key:
            self._capture_depth += 1

        if tag == "div" and _has_class(attrs, "views-row"):
            self._current = {"materials": []}
            self._row_depth = 1
            return

        if not self._current:
            return

        if tag == "div":
            self._row_depth += 1
            if self._recyclables_depth > 0:
                self._recyclables_depth += 1
            if _has_class(attrs, "recyclables"):
                self._recyclables_depth = 1
            elif _has_class(attrs, "field--name-name") and self._recyclables_depth > 0:
                self._start_capture("material")
            elif _has_class(attrs, "accessibility"):
                self._start_capture("accessibility")
        elif tag in {"a", "button"}:
            href = attrs.get("href", "")
            if _has_class(attrs, "accordion-button"):
                self._start_capture("name")
            if "google.com/maps" in href and "daddr=" in href:
                self._current["maps_url"] = href
                coords = _coordinates_from_maps_url(href)
                if coords:
                    self._current["latitude"], self._current["longitude"] = coords
                    self._current["distance_m"] = _distance_meters(self.latitude, self.longitude, coords[0], coords[1])
            elif "/recycling-point/" in href:
                self._current["detail_url"] = _absolute_detail_url(href)
        elif tag == "p" and _has_class(attrs, "contact"):
            self._start_capture("contact")
        elif tag == "p" and _has_class(attrs, "openhour"):
            self._start_capture("open_hours")

    def handle_endtag(self, tag: str) -> None:
        if self._capture_key:
            self._capture_depth -= 1
            if self._capture_depth <= 0:
                self._finish_capture()

        if self._current and tag == "div":
            if self._recyclables_depth > 0:
                self._recyclables_depth -= 1
            self._row_depth -= 1
            if self._row_depth <= 0:
                self._finish_row()

    def handle_data(self, data: str) -> None:
        if self._capture_key:
            self._capture_parts.append(data)

    def _start_capture(self, key: str) -> None:
        self._capture_key = key
        self._capture_depth = 1
        self._capture_parts = []

    def _finish_capture(self) -> None:
        if not self._current or not self._capture_key:
            return
        text = _clean_text(" ".join(self._capture_parts))
        key = self._capture_key
        if text:
            if key == "material":
                materials = self._current.setdefault("materials", [])
                if text not in materials:
                    materials.append(text)
            else:
                self._current[key] = text
        self._capture_key = None
        self._capture_depth = 0
        self._capture_parts = []

    def _finish_row(self) -> None:
        point = self._current or {}
        if point.get("name") and point.get("maps_url") and "distance_m" in point:
            point.setdefault("detail_url", "")
            point.setdefault("contact", "")
            point.setdefault("open_hours", "")
            point.setdefault("accessibility", "")
            self.points.append(point)
        self._current = None
        self._row_depth = 0
        self._recyclables_depth = 0


def parse_recycling_points_html(html: str, *, latitude: float, longitude: float, limit: int = 5) -> list[dict]:
    parser = _RecyclingMapParser(latitude, longitude)
    parser.feed(html or "")
    parser.close()
    points = sorted(parser.points, key=lambda point: point.get("distance_m", 10**9))
    return points[: max(0, limit)]


async def find_nearby_recycling_points(
    latitude: float,
    longitude: float,
    *,
    material: str | None = None,
    limit: int = 5,
    distance_km: int = 3,
) -> dict:
    source_url = build_recycling_map_url(latitude, longitude, material=material, distance_km=distance_km)
    headers = {"User-Agent": "Re-Life/1.0 (+https://www.wastereduction.gov.hk/zh-hk/recycling-map)"}
    async with httpx.AsyncClient(timeout=RECYCLING_MAP_TIMEOUT, follow_redirects=True, headers=headers) as client:
        response = await client.get(source_url)
        response.raise_for_status()
    points = parse_recycling_points_html(response.text, latitude=latitude, longitude=longitude, limit=limit)
    return {
        "points": points,
        "source_url": source_url,
        "source": RECYCLING_MAP_SOURCE,
    }
