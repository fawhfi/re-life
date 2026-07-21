"""Validated, privacy-preserving access to regional recycling statistics."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
import math
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from backend.storage import supabase_select


MAX_REGIONAL_RECORDS = 100
SelectRows = Callable[..., Awaitable[list[dict] | None]]


class RegionalRecyclingUnavailable(RuntimeError):
    """The public regional dataset could not be read or safely validated."""

    def __init__(self, *_private_details: object):
        super().__init__("Regional recycling data is unavailable")


class RegionalRecyclingRecord(BaseModel):
    """One region's published recycled amount."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    region: StrictStr = Field(min_length=1, max_length=100)
    recycled_amount: float = Field(ge=0)

    @field_validator("region")
    @classmethod
    def normalize_region(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or any(ord(character) < 32 for character in normalized):
            raise ValueError("region contains invalid characters")
        return normalized

    @field_validator("recycled_amount", mode="before")
    @classmethod
    def require_finite_amount(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("recycled_amount must be a JSON number")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("recycled_amount must be finite")
        return value


class RegionalRecyclingMeta(BaseModel):
    """Public provenance and ordering guarantees for the regional dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    period: StrictStr = Field(min_length=1, max_length=100)
    unit: Literal["tonnes"]
    source: StrictStr = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    sorted_by: Literal["recycled_amount"] = "recycled_amount"
    sort_order: Literal["descending"] = "descending"
    record_count: int = Field(ge=1, le=MAX_REGIONAL_RECORDS)


class RegionalRecyclingResponse(BaseModel):
    """Stable JSON response returned by ``GET /api/data``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data: tuple[RegionalRecyclingRecord, ...] = Field(
        min_length=1,
        max_length=MAX_REGIONAL_RECORDS,
    )
    meta: RegionalRecyclingMeta


class _PublishedDataset(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    id: StrictInt = Field(gt=0)
    dataset_version: StrictStr = Field(min_length=1, max_length=64)
    period: StrictStr = Field(min_length=1, max_length=100)
    unit: Literal["tonnes"]
    source: StrictStr = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    published_at: StrictStr = Field(min_length=1, max_length=64)

    @field_validator("source_url")
    @classmethod
    def require_https_source(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("source_url must use HTTPS")
        return value


class _DatabaseRecord(RegionalRecyclingRecord):
    model_config = ConfigDict(extra="ignore", frozen=True)

    sort_order: StrictInt = Field(ge=1, le=MAX_REGIONAL_RECORDS)


class _DatabaseRecords(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[_DatabaseRecord, ...] = Field(
        min_length=1,
        max_length=MAX_REGIONAL_RECORDS,
    )

    @model_validator(mode="after")
    def require_unique_pre_sorted_rows(self):
        expected_positions = list(range(1, len(self.rows) + 1))
        positions = [row.sort_order for row in self.rows]
        if positions != expected_positions:
            raise ValueError("regional recycling sort_order must be contiguous")

        regions = [row.region.casefold() for row in self.rows]
        if len(regions) != len(set(regions)):
            raise ValueError("regional recycling regions must be unique")

        amounts = [row.recycled_amount for row in self.rows]
        if amounts != sorted(amounts, reverse=True):
            raise ValueError("regional recycling data must already be descending")
        return self


async def get_regional_recycling_response(
    *,
    select_rows: SelectRows | None = None,
) -> RegionalRecyclingResponse:
    """Read the latest published dataset using fixed, bounded database queries."""
    select = select_rows or supabase_select
    try:
        dataset_rows = await select(
            "regional_recycling_datasets",
            columns="id,dataset_version,period,unit,source,source_url,published_at",
            filters={"is_published": True},
            order="published_at.desc,id.desc",
            limit=1,
        )
        if not dataset_rows:
            raise RegionalRecyclingUnavailable()
        dataset = _PublishedDataset.model_validate(dataset_rows[0])

        raw_records = await select(
            "regional_recycling_data",
            columns="region,recycled_amount,sort_order",
            filters={"dataset_id": dataset.id},
            order="sort_order.asc",
            limit=MAX_REGIONAL_RECORDS,
        )
        if not raw_records:
            raise RegionalRecyclingUnavailable()
        database_records = _DatabaseRecords.model_validate({"rows": raw_records})
    except RegionalRecyclingUnavailable:
        raise
    except Exception:
        raise RegionalRecyclingUnavailable() from None

    public_records = tuple(
        RegionalRecyclingRecord(
            region=row.region,
            recycled_amount=row.recycled_amount,
        )
        for row in database_records.rows
    )
    return RegionalRecyclingResponse(
        data=public_records,
        meta=RegionalRecyclingMeta(
            period=dataset.period,
            unit=dataset.unit,
            source=dataset.source,
            source_url=dataset.source_url,
            record_count=len(public_records),
        ),
    )
