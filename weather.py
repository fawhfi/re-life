from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import httpx

HKO_WEATHER_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
WEATHER_CACHE_TTL_SECONDS = 600.0

DEFAULT_LOCATION_LABEL = "Hong Kong"
DEFAULT_SUMMARY = "Hong Kong weather"
DEFAULT_EMOJI = "🌤️"

WEATHER_ICON_EMOJI: dict[int, str] = {
    50: "☀️",
    51: "🌤️",
    52: "⛅",
    53: "🌦️",
    54: "🌦️",
    60: "☁️",
    61: "☁️",
    62: "🌧️",
    63: "🌧️",
    64: "🌧️",
    65: "⛈️",
    70: "🌙",
    71: "🌙",
    72: "🌙",
    73: "🌙",
    74: "🌙",
    75: "🌙",
    76: "🌙",
    77: "🌙",
    80: "💨",
    81: "☀️",
    82: "💧",
    83: "🌫️",
    84: "🌫️",
    85: "🌫️",
    90: "🔥",
    91: "🌤️",
    92: "🧥",
    93: "🧊",
}

WEATHER_ICON_SUMMARY: dict[int, str] = {
    50: "Sunny",
    51: "Sunny periods",
    52: "Sunny intervals",
    53: "Sunny intervals with showers",
    54: "Sunny periods with showers",
    60: "Cloudy",
    61: "Overcast",
    62: "Light rain",
    63: "Rain",
    64: "Heavy rain",
    65: "Thunderstorms",
    70: "Fine",
    71: "Mainly cloudy",
    72: "Cloudy at night",
    73: "Fine with mist",
    74: "Cloudy with mist",
    75: "Hazy",
    76: "Mainly cloudy at night",
    77: "Fine at night",
    80: "Windy",
    81: "Dry",
    82: "Humid",
    83: "Fog",
    84: "Mist",
    85: "Haze",
    90: "Hot",
    91: "Warm",
    92: "Cool",
    93: "Cold",
}

# Approximate coordinates for the HKO temperature stations shown in rhrread.
_HK_WEATHER_STATIONS: list[tuple[str, float, float]] = [
    ("Hong Kong Observatory", 22.3022, 114.1740),
    ("King's Park", 22.3111, 114.1717),
    ("Wong Chuk Hang", 22.2472, 114.1692),
    ("Ta Kwu Ling", 22.5120, 114.1525),
    ("Lau Fau Shan", 22.4737, 113.9845),
    ("Tai Po", 22.4500, 114.1650),
    ("Sha Tin", 22.3797, 114.1974),
    ("Tuen Mun", 22.3914, 113.9777),
    ("Tseung Kwan O", 22.3107, 114.2570),
    ("Sai Kung", 22.3830, 114.2701),
    ("Cheung Chau", 22.2087, 114.0302),
    ("Chek Lap Kok", 22.3080, 113.9185),
    ("Tsing Yi", 22.3585, 114.1070),
    ("Tsuen Wan Ho Koon", 22.3735, 114.1042),
    ("Tsuen Wan Shing Mun Valley", 22.3730, 114.1360),
    ("Hong Kong Park", 22.2799, 114.1620),
    ("Shau Kei Wan", 22.2797, 114.2280),
    ("Kowloon City", 22.3311, 114.1915),
    ("Happy Valley", 22.2695, 114.1840),
    ("Wong Tai Sin", 22.3413, 114.1950),
    ("Stanley", 22.2180, 114.2130),
    ("Kwun Tong", 22.3130, 114.2260),
    ("Sham Shui Po", 22.3300, 114.1620),
    ("Kai Tak Runway Park", 22.3070, 114.2007),
    ("Yuen Long Park", 22.4450, 114.0300),
    ("Tai Mei Tuk", 22.4620, 114.1840),
]

_REPORT_CACHE: dict[str, Any] = {"expires_at": 0.0, "report": None}
_REPORT_LOCK = asyncio.Lock()


def map_weather_icon_to_emoji(icon: int | None) -> str:
    return WEATHER_ICON_EMOJI.get(int(icon) if icon is not None else -1, DEFAULT_EMOJI)


def map_weather_icon_to_summary(icon: int | None) -> str:
    return WEATHER_ICON_SUMMARY.get(int(icon) if icon is not None else -1, DEFAULT_SUMMARY)


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _nearest_station(latitude: float | None, longitude: float | None) -> str | None:
    if latitude is None or longitude is None:
        return None
    best_name: str | None = None
    best_distance = math.inf
    for name, station_lat, station_lon in _HK_WEATHER_STATIONS:
        distance = (latitude - station_lat) ** 2 + (longitude - station_lon) ** 2
        if distance < best_distance:
            best_distance = distance
            best_name = name
    return best_name


def _select_temperature_record(report: dict[str, Any], latitude: float | None, longitude: float | None) -> dict[str, Any] | None:
    temperature_block = report.get("temperature") or {}
    records = temperature_block.get("data") or []
    if not records:
        return None

    record_map = {
        str(record.get("place")): record
        for record in records
        if record.get("place") and record.get("value") is not None
    }
    if not record_map:
        return None

    nearest_station = _nearest_station(latitude, longitude)
    if nearest_station and nearest_station in record_map:
        return record_map[nearest_station]

    for fallback in ("Hong Kong Observatory", "King's Park"):
        if fallback in record_map:
            return record_map[fallback]

    return next(iter(record_map.values()))


def build_header_weather_payload(
    report: dict[str, Any] | None,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    report = report or {}
    icon_values = report.get("icon") or []
    icon = icon_values[0] if icon_values else None
    emoji = map_weather_icon_to_emoji(icon)
    summary = map_weather_icon_to_summary(icon)
    record = _select_temperature_record(report, latitude, longitude)
    temperature = None
    temperature_place = DEFAULT_LOCATION_LABEL
    if record:
        temperature = record.get("value")
        temperature_place = str(record.get("place") or DEFAULT_LOCATION_LABEL)

    if latitude is None or longitude is None:
        location = DEFAULT_LOCATION_LABEL
    else:
        location = temperature_place

    updated_at = report.get("updateTime") or report.get("iconUpdateTime")

    return {
        "emoji": emoji,
        "summary": summary,
        "temperature": temperature,
        "temperature_place": temperature_place,
        "location": location,
        "updated_at": updated_at,
        "source": "HKO Open Data",
    }


async def _fetch_report() -> dict[str, Any]:
    now = time.monotonic()
    cached = _REPORT_CACHE.get("report")
    if cached is not None and now < float(_REPORT_CACHE.get("expires_at") or 0.0):
        return cached

    async with _REPORT_LOCK:
        cached = _REPORT_CACHE.get("report")
        if cached is not None and now < float(_REPORT_CACHE.get("expires_at") or 0.0):
            return cached

        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
            response = await client.get(HKO_WEATHER_URL, headers={"Accept": "application/json"})
            response.raise_for_status()
            report = response.json()

        _REPORT_CACHE["report"] = report
        _REPORT_CACHE["expires_at"] = now + WEATHER_CACHE_TTL_SECONDS
        return report


async def get_header_weather(latitude: float | None = None, longitude: float | None = None) -> dict[str, Any]:
    try:
        report = await _fetch_report()
        return build_header_weather_payload(report, latitude=latitude, longitude=longitude)
    except Exception:
        fallback = build_header_weather_payload({}, latitude=latitude, longitude=longitude)
        fallback["source"] = "Fallback"
        return fallback
