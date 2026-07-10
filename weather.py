from __future__ import annotations

import asyncio
import math
import time
from typing import Any

import httpx

HKO_WEATHER_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
HKO_WARNING_SUMMARY_URL = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=en"
WEATHER_CACHE_TTL_SECONDS = 600.0
WARNING_CACHE_TTL_SECONDS = 300.0

DEFAULT_LOCATION_LABEL = "Hong Kong"
DEFAULT_SUMMARY = "Hong Kong weather"
DEFAULT_EMOJI = "🌤️"
HKO_WEATHER_ICON_BASE_URL = "https://www.hko.gov.hk/images/HKOWxIconOutline"
HKO_WARNING_ICON_BASE_URL = "https://www.hko.gov.hk/en/wxinfo/dailywx/images"
TYPHOON_EMOJI = "🌀"
WARNING_EMOJI = "⚠️"

WARNING_ICON_FILENAMES: dict[str, str] = {
    "TC1": "tc1.gif",
    "TC3": "tc3.gif",
    "TC8NE": "tc8ne.gif",
    "TC8SE": "tc8b.gif",
    "TC8NW": "tc8d.gif",
    "TC8SW": "tc8c.gif",
    "TC9": "tc9.gif",
    "TC10": "tc10.gif",
    "WRAINA": "raina.gif",
    "WRAINR": "rainr.gif",
    "WRAINB": "rainb.gif",
    "WTS": "ts.gif",
    "WHOT": "vhot.gif",
    "WCOLD": "cold.gif",
    "WMSGNL": "sms.gif",
    "WFROST": "frost.gif",
    "WFIRER": "firer.gif",
    "WFIREY": "firey.gif",
    "WL": "landslip.gif",
    "WFNTSA": "ntfl.gif",
    "WTMW": "tsunami-warn.gif",
}

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

WEATHER_CALLOUTS: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("thunderstorm", "thunderstorms", "heavy rain", "rain", "shower", "showers"),
        "Rainy day",
        "Too much greenhouse gas traps more heat and moisture. Recycling helps keep the buildup in check.",
    ),
    (
        ("sunny periods with showers", "sunny periods", "sunny intervals", "sunny", "fine"),
        "Sunny day",
        "If you want more days like this, keep recycling so the Earth can stay lighter and cleaner.",
    ),
    (
        ("fog", "mist", "haze"),
        "Hazy air",
        "When the air hangs heavy, every recycled item helps reduce the pressure on the atmosphere.",
    ),
    (
        ("cloudy", "overcast", "mainly cloudy"),
        "Cloudy day",
        "Grey skies still deserve a cleaner city. Small recycling habits add up faster than they look.",
    ),
    (
        ("hot", "warm", "dry"),
        "Hot day",
        "Hotter days are easier to live with when we cut waste and emissions together. Recycle what you can.",
    ),
    (
        ("cool", "cold"),
        "Cool day",
        "Cool weather feels better when we keep carbon down. Recycling is one small part of that.",
    ),
    (
        ("windy",),
        "Windy day",
        "Fresh wind feels better when the air stays clean. Recycling helps keep the long game on track.",
    ),
]

DEFAULT_CALLOUT_TITLE = "Hong Kong weather"
DEFAULT_CALLOUT_BODY = "Small habits make the city easier to breathe in. Recycle what you can and keep the air cleaner."
TYPHOON_WARNING_TITLE = "Typhoon warning"
TYPHOON_WARNING_BODY = "A tropical cyclone warning is in force. Secure loose items, avoid exposed waterfronts, and check official advice before going out."
TYPHOON_CALLOUT_TITLE = "Safety first"
TYPHOON_CALLOUT_BODY = "Leave recycling trips for calmer weather. Keep loose recyclables indoors so they do not become flying debris."
WEATHER_WARNING_TITLE = "Weather warning"
WEATHER_WARNING_BODY = "Bad weather warning is in force. Check conditions before going out and keep recycling plans flexible."

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
_WARNING_SUMMARY_CACHE: dict[str, Any] = {"expires_at": 0.0, "summary": None}
_REPORT_LOCK = asyncio.Lock()
_WARNING_SUMMARY_LOCK = asyncio.Lock()


def map_weather_icon_to_emoji(icon: int | None) -> str:
    return WEATHER_ICON_EMOJI.get(int(icon) if icon is not None else -1, DEFAULT_EMOJI)


def map_weather_icon_to_summary(icon: int | None) -> str:
    return WEATHER_ICON_SUMMARY.get(int(icon) if icon is not None else -1, DEFAULT_SUMMARY)


def weather_icon_url(icon: int | None) -> str:
    if icon is None:
        return ""
    try:
        icon_number = int(icon)
    except (TypeError, ValueError):
        return ""
    if icon_number not in WEATHER_ICON_SUMMARY:
        return ""
    return f"{HKO_WEATHER_ICON_BASE_URL}/pic{icon_number}.png"


def warning_icon_url(code: str | None) -> str:
    filename = WARNING_ICON_FILENAMES.get(str(code or "").upper())
    return f"{HKO_WARNING_ICON_BASE_URL}/{filename}" if filename else ""


def build_weather_callout(summary: str | None, icon: int | None = None) -> dict[str, str]:
    haystack = " ".join(
        part
        for part in (
            summary or "",
            map_weather_icon_to_summary(icon),
        )
        if part
    ).lower()
    for keywords, title, body in WEATHER_CALLOUTS:
        if any(keyword in haystack for keyword in keywords):
            return {"title": title, "body": body}
    return {"title": DEFAULT_CALLOUT_TITLE, "body": DEFAULT_CALLOUT_BODY}


def _is_typhoon_warning(key: str, item: dict[str, Any]) -> bool:
    code = str(item.get("code") or "").upper()
    text = " ".join(str(part or "") for part in (key, code, item.get("name"))).lower()
    return key == "WTCSGNL" or code.startswith("TC") or "tropical cyclone" in text or "typhoon" in text


def _normalize_warning_items(summary: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(summary, dict):
        return []

    items: list[dict[str, str]] = []
    for key, value in summary.items():
        if not isinstance(value, dict):
            continue
        action = str(value.get("actionCode") or "").upper()
        if action == "CANCEL":
            continue
        title = str(value.get("name") or key)
        code = str(value.get("code") or key)
        items.append(
            {
                "key": key,
                "code": code,
                "title": title,
                "type": "typhoon" if _is_typhoon_warning(key, value) else "weather",
                "icon_url": warning_icon_url(code),
            }
        )
    return items


def build_weather_warning(summary: dict[str, Any] | None) -> dict[str, Any]:
    items = _normalize_warning_items(summary)
    if not items:
        return {"active": False, "type": "", "emoji": "", "title": "", "body": "", "items": []}

    primary = next((item for item in items if item["type"] == "typhoon"), items[0])
    if primary["type"] == "typhoon":
        return {
            "active": True,
            "type": "typhoon",
            "emoji": TYPHOON_EMOJI,
            "icon_url": primary.get("icon_url") or "",
            "title": primary["title"] or TYPHOON_WARNING_TITLE,
            "body": TYPHOON_WARNING_BODY,
            "items": items,
        }

    return {
        "active": True,
        "type": "weather",
        "emoji": WARNING_EMOJI,
        "icon_url": primary.get("icon_url") or "",
        "title": primary["title"] or WEATHER_WARNING_TITLE,
        "body": WEATHER_WARNING_BODY,
        "items": items,
    }


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
    warning_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = report or {}
    icon_values = report.get("icon") or []
    icon = icon_values[0] if icon_values else None
    emoji = map_weather_icon_to_emoji(icon)
    icon_url = weather_icon_url(icon)
    summary = map_weather_icon_to_summary(icon)
    callout = build_weather_callout(summary, icon)
    warning = build_weather_warning(warning_summary)
    if warning.get("active") and warning.get("type") == "typhoon":
        emoji = TYPHOON_EMOJI
        icon_url = warning.get("icon_url") or icon_url
        summary = "Tropical Cyclone Warning"
        callout = {"title": TYPHOON_CALLOUT_TITLE, "body": TYPHOON_CALLOUT_BODY}
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
        "icon_url": icon_url,
        "summary": summary,
        "temperature": temperature,
        "temperature_place": temperature_place,
        "location": location,
        "updated_at": updated_at,
        "source": "HKO Open Data",
        "warning": warning,
        "callout": callout,
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


async def _fetch_warning_summary() -> dict[str, Any]:
    now = time.monotonic()
    cached = _WARNING_SUMMARY_CACHE.get("summary")
    if cached is not None and now < float(_WARNING_SUMMARY_CACHE.get("expires_at") or 0.0):
        return cached

    async with _WARNING_SUMMARY_LOCK:
        cached = _WARNING_SUMMARY_CACHE.get("summary")
        if cached is not None and now < float(_WARNING_SUMMARY_CACHE.get("expires_at") or 0.0):
            return cached

        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
            response = await client.get(HKO_WARNING_SUMMARY_URL, headers={"Accept": "application/json"})
            response.raise_for_status()
            summary = response.json()

        _WARNING_SUMMARY_CACHE["summary"] = summary if isinstance(summary, dict) else {}
        _WARNING_SUMMARY_CACHE["expires_at"] = now + WARNING_CACHE_TTL_SECONDS
        return _WARNING_SUMMARY_CACHE["summary"]


async def get_header_weather(latitude: float | None = None, longitude: float | None = None) -> dict[str, Any]:
    report_result, warning_result = await asyncio.gather(
        _fetch_report(),
        _fetch_warning_summary(),
        return_exceptions=True,
    )
    report_failed = isinstance(report_result, Exception)
    warning_summary = {} if isinstance(warning_result, Exception) else warning_result
    payload = build_header_weather_payload(
        {} if report_failed else report_result,
        latitude=latitude,
        longitude=longitude,
        warning_summary=warning_summary,
    )
    if report_failed:
        payload["source"] = "Fallback"
    return payload
