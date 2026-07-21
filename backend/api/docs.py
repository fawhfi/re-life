"""Human-oriented usage guide for the public Re-Life Data API."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(include_in_schema=False)
_DOCS_PAGE = Path(__file__).resolve().parents[2] / "templates" / "api-docs.html"


@router.get("/docs", response_class=HTMLResponse)
async def api_usage_guide() -> HTMLResponse:
    """Explain how to call the public API with runnable examples."""
    return HTMLResponse(
        _DOCS_PAGE.read_text(encoding="utf-8"),
        headers={"Cache-Control": "public, max-age=300"},
    )
