"""Strict read-only HTTP interface for public Re-Life statistics."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import logging
import math

from backend.auth import check_rate_limit
from backend.domain.regional_recycling import (
    RegionalRecyclingResponse,
    RegionalRecyclingUnavailable,
    get_regional_recycling_response,
)


router = APIRouter(tags=["Public data"])
logger = logging.getLogger(__name__)


def _accepts_json(request: Request) -> bool:
    value = request.headers.get("accept", "").strip().lower()
    if not value:
        return True
    for part in value.split(","):
        media_type, *parameters = (item.strip() for item in part.split(";"))
        quality = next(
            (
                parameter.removeprefix("q=")
                for parameter in parameters
                if parameter.startswith("q=")
            ),
            "1",
        )
        try:
            quality_value = float(quality)
            if not math.isfinite(quality_value) or not 0 < quality_value <= 1:
                continue
        except ValueError:
            continue
        if (
            media_type in {"*/*", "application/*", "application/json"}
            or (
                media_type.startswith("application/")
                and media_type.endswith("+json")
            )
        ):
            return True
    return False


def _has_request_input(request: Request) -> bool:
    if request.scope.get("query_string"):
        return True
    if request.headers.get("transfer-encoding"):
        return True
    content_length = request.headers.get("content-length")
    if content_length is None:
        return False
    try:
        return int(content_length) != 0
    except ValueError:
        return True


@router.get(
    "/api/data",
    response_model=RegionalRecyclingResponse,
    summary="Get regional recycling amounts",
    description=(
        "Returns the complete, pre-sorted regional recycling dataset as JSON. "
        "This endpoint accepts no query parameters, request body, GPS coordinates, "
        "IP address, sorting expression, or filtering expression."
    ),
    responses={
        400: {"description": "The request included input that this read-only endpoint rejects."},
        406: {"description": "The client did not accept a JSON response."},
        429: {"description": "Request rate limit exceeded."},
        503: {"description": "No validated regional recycling dataset is available."},
    },
)
async def regional_recycling_data(request: Request):
    await check_rate_limit(request, 60, 60)
    if _has_request_input(request):
        return JSONResponse(
            {"error": "DATA_REQUEST_INPUT_NOT_ALLOWED"},
            status_code=400,
        )
    if not _accepts_json(request):
        return JSONResponse(
            {"error": "JSON_RESPONSE_REQUIRED"},
            status_code=406,
        )

    try:
        payload = (await get_regional_recycling_response()).model_dump(mode="json")
    except RegionalRecyclingUnavailable:
        logger.error("Regional recycling dataset is unavailable")
        response = JSONResponse(
            {"error": "DATASET_UNAVAILABLE"},
            status_code=503,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Retry-After"] = "300"
        return response

    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response
