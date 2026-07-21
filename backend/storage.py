"""Shared storage helpers for Supabase-backed tables."""
from __future__ import annotations

from urllib.parse import quote, unquote, urlencode, urlsplit
import hashlib
import hmac
import os
import time

import httpx

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

SUPABASE_REST_TIMEOUT = 15.0
SUPABASE_STORAGE_TIMEOUT = 30.0
STORAGE_LINK_TTL_SECONDS = int(os.getenv("SUPABASE_STORAGE_LINK_TTL_SECONDS", "86400"))


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


def _postgrest_scalar(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return str(value)


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
        raise RuntimeError(
            f"Supabase REST request failed with HTTP {response.status_code}"
        )
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
            params[key] = f"eq.{_postgrest_scalar(value)}"
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
            params[key] = f"eq.{_postgrest_scalar(value)}"
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
            params[key] = f"eq.{_postgrest_scalar(value)}"
    prefer = "return=representation" if returning else None
    data = await supabase_request("DELETE", table, params=params, prefer=prefer)
    return data if isinstance(data, list) else ([] if data is None else [data])


def _storage_path(value: object) -> str:
    return "/".join(quote(part, safe="") for part in str(value).split("/"))


def _storage_signature(bucket: str, path: str, expires_at: int) -> str:
    secret = SUPABASE_SERVICE_ROLE_KEY or ""
    payload = f"{bucket}|{path}|{expires_at}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def supabase_storage_signed_url(bucket: str, path: str, *, ttl_seconds: int | None = None) -> str:
    bucket_name = str(bucket).strip("/")
    object_path = _storage_path(unquote(str(path)))
    expires_at = int(time.time()) + int(ttl_seconds or STORAGE_LINK_TTL_SECONDS)
    signature = _storage_signature(bucket_name, object_path, expires_at)
    query = urlencode({"exp": str(expires_at), "sig": signature})
    return f"/api/storage/{quote(bucket_name, safe='')}/{object_path}?{query}"


def _extract_storage_parts(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    path = parsed.path or ""
    for marker in ("/storage/v1/s3/object/public/", "/storage/v1/object/public/", "/api/storage/"):
        if marker in path:
            remainder = path.split(marker, 1)[1]
            bucket, _, object_path = remainder.partition("/")
            if bucket and object_path:
                return unquote(bucket), unquote(object_path)
    return None


def normalize_supabase_storage_url(url: str | None) -> str | None:
    if not url:
        return url
    if url.startswith("/api/storage/"):
        parts = _extract_storage_parts(url)
        if parts:
            bucket, object_path = parts
            return supabase_storage_signed_url(bucket, object_path)
        return url
    parts = _extract_storage_parts(url)
    if parts:
        bucket, object_path = parts
        return supabase_storage_signed_url(bucket, object_path)
    return url


def verify_supabase_storage_signature(bucket: str, path: str, exp: str | int | None, sig: str | None) -> bool:
    if not sig or exp is None:
        return False
    try:
        expires_at = int(exp)
    except Exception:
        return False
    if expires_at < int(time.time()):
        return False
    bucket_name = str(bucket).strip("/")
    object_path = _storage_path(unquote(str(path)))
    expected = _storage_signature(bucket_name, object_path, expires_at)
    try:
        return hmac.compare_digest(expected, str(sig))
    except Exception:
        return False


def supabase_storage_proxy_url(bucket: str, path: str) -> str:
    return supabase_storage_signed_url(bucket, path)


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
        raise RuntimeError(
            f"Supabase storage upload failed with HTTP {response.status_code}"
        )
    if response.status_code == 204 or not response.text:
        return None
    try:
        return response.json()
    except Exception:
        return response.text


async def supabase_storage_download(
    bucket: str,
    path: str,
) -> tuple[bytes, str]:
    if not supabase_enabled():
        raise RuntimeError("Supabase storage unavailable")

    bucket_path = quote(str(bucket), safe="")
    object_path = _storage_path(path)
    url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket_path}/{object_path}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "*/*",
    }

    async with httpx.AsyncClient(timeout=SUPABASE_STORAGE_TIMEOUT) as client:
        response = await client.get(url, headers=headers)

    if response.status_code >= 400:
        raise RuntimeError(
            f"Supabase storage download failed with HTTP {response.status_code}"
        )
    return response.content, response.headers.get("content-type", "application/octet-stream")


def encode_id(value: object) -> str:
    return _encode_path_arg(value)
