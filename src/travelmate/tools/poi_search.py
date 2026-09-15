"""POI Search Tool implementation (CMP-07).

Searches for accommodations, restaurants, and attractions using structured filters
over PostgreSQL relational tables via PoiRepositoryProtocol.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.travelmate.infrastructure.database.repositories.base import PoiRepositoryProtocol
from src.travelmate.schemas.tools import (
    PoiItem,
    PoiSearchRequest,
    PoiSearchResponse,
    ToolError,
)
from src.travelmate.tools.base import ToolProtocol

logger = structlog.get_logger(__name__)


class PoiSearchTool(ToolProtocol):
    """Tool for querying points of interest matching structured constraints."""

    name: str = "poi_search"
    description: str = (
        "Search points of interest (hotels, restaurants, attractions) by location, "
        "category, budget_max, and preference keywords. Returns real, un-fabricated data."
    )

    def __init__(self, poi_repo: PoiRepositoryProtocol) -> None:
        """Initialize tool with injected repository dependency.

        Args:
            poi_repo: Repository implementing PoiRepositoryProtocol.
        """
        self.poi_repo = poi_repo

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute POI search using validated request parameters.

        Args:
            params: Dictionary containing location, category, budget_max, preferences.

        Returns:
            PoiSearchResponse dictionary with status 'OK', 'EMPTY', or 'PROVIDER_ERROR'.
        """
        try:
            req = PoiSearchRequest.model_validate(params)
        except Exception as exc:
            logger.warning("Invalid poi_search parameters", error=str(exc))
            return PoiSearchResponse(
                status="BAD_REQUEST",
                error=ToolError(code="ERR-PARAM-01", message=str(exc)),
            ).model_dump()

        try:
            records = await self.poi_repo.search_poi(
                location=req.location,
                category=req.category,
                budget_min=req.budget_min,
                budget_max=req.budget_max,
                preferences=req.preferences,
                limit=req.limit,
            )

            if not records:
                logger.info(
                    "POI search returned zero results", location=req.location, category=req.category
                )
                return PoiSearchResponse(status="EMPTY", items=[]).model_dump()

            items = [
                PoiItem(
                    id=rec.poi_id,
                    name=rec.name,
                    address=rec.address,
                    category=rec.category,
                    rating=float(rec.rating),
                    price_info=rec.price_info,
                    price_numeric=rec.price_numeric,
                    attributes=rec.attributes,
                    source=rec.source,
                    source_url=rec.source_url,
                    source_type=rec.source_type,
                    verified_at=str(rec.verified_at) if rec.verified_at else None,
                    scope_and_limitations=rec.scope_and_limitations,
                )
                for rec in records
            ]

            return PoiSearchResponse(status="OK", items=items).model_dump()

        except Exception as exc:
            logger.error("poi_search database execution error", error=str(exc))
            return PoiSearchResponse(
                status="PROVIDER_ERROR",
                error=ToolError(code="ERR-TOOL-01", message=str(exc)),
            ).model_dump()
