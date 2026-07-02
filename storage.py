"""Shared storage helpers for Supabase-backed tables."""
from __future__ import annotations

from urllib.parse import quote

import httpx

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

SUPABASE_REST_TIMEOUT = 15.0
SUPABASE_STORAGE_TIMEOUT = 30.0


def supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _rest_url(path: str) -> str:
    base = SUPABASE_URL.rstrip("/")
    return f"{base}/rest/v1/{path.lstrip('/')}"


def _headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _encode_path_arg(value: object) -> str:
    return quote(str(value), safe="")


async def supabase_request(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    json: object | None = None,
    prefer: str | None = None,
) -> object | None:
    if not supabase_enabled():
        return None

    async with httpx.AsyncClient(timeout=SUPABASE_REST_TIMEOUT) as client:
        response = await client.request(
            method,
            _rest_url(path),
            params=params,
            json=json,
            headers=_headers(prefer),
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase HTTP {response.status_code}: {response.text[:300]}")
    if response.status_code == 204 or not response.text:
        return None
    try:
        return response.json()
    except Exception:
        return response.text


async def supabase_select(
    table: str,
    *,
    columns: str = "*",
    filters: dict[str, object] | None = None,
    order: str | None = None,
    limit: int | None = None,
) -> list[dict] | None:
    params: dict[str, str] = {"select": columns}
    if filters:
        for key, value in filters.items():
            params[key] = f"eq.{value}"
    if order:
        params["order"] = order
    if limit is not None:
        params["limit"] = str(limit)
    data = await supabase_request("GET", table, params=params)
    return data if isinstance(data, list) else ([] if data is None else [data])


async def supabase_select_one(
    table: str,
    *,
    columns: str = "*",
    filters: dict[str, object] | None = None,
    order: str | None = None,
) -> dict | None:
    rows = await supabase_select(table, columns=columns, filters=filters, order=order, limit=1)
    return rows[0] if rows else None


async def supabase_insert(
    table: str,
    values: dict | list[dict],
    *,
    returning: bool = True,
) -> list[dict] | None:
    prefer = "return=representation" if returning else None
    data = await supabase_request("POST", table, json=values, prefer=prefer)
    return data if isinstance(data, list) else ([] if data is None else [data])


async def supabase_update(
    table: str,
    values: dict,
    *,
    filters: dict[str, object] | None = None,
    returning: bool = True,
) -> list[dict] | None:
    params: dict[str, str] = {}
    if filters:
        for key, value in filters.items():
            params[key] = f"eq.{value}"
    prefer = "return=representation" if returning else None
    data = await supabase_request("PATCH", table, params=params, json=values, prefer=prefer)
    return data if isinstance(data, list) else ([] if data is None else [data])


async def supabase_delete(
    table: str,
    *,
    filters: dict[str, object] | None = None,
    returning: bool = False,
) -> list[dict] | None:
    params: dict[str, str] = {}
    if filters:
        for key, value in filters.items():
            params[key] = f"eq.{value}"
    prefer = "return=representation" if returning else None
    data = await supabase_request("DELETE", table, params=params, prefer=prefer)
    return data if isinstance(data, list) else ([] if data is None else [data])


def _storage_path(value: object) -> str:
    return "/".join(quote(part, safe="") for part in str(value).split("/"))


async def supabase_storage_upload(
    bucket: str,
    path: str,
    contents: bytes,
    content_type: str,
    *,
    upsert: bool = True,
) -> object | None:
    if not supabase_enabled():
        return None

    bucket_path = quote(str(bucket), safe="")
    object_path = _storage_path(path)
    url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket_path}/{object_path}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": content_type or "application/octet-stream",
        "Accept": "application/json",
        "cache-control": "3600",
        "x-upsert": "true" if upsert else "false",
    }

    async with httpx.AsyncClient(timeout=SUPABASE_STORAGE_TIMEOUT) as client:
        response = await client.post(url, content=contents, headers=headers)

    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage HTTP {response.status_code}: {response.text[:300]}")
    if response.status_code == 204 or not response.text:
        return None
    try:
        return response.json()
    except Exception:
        return response.text


def encode_id(value: object) -> str:
    return _encode_path_arg(value)
