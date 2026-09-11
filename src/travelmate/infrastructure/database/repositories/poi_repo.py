"""Concrete repository implementation for Point of Interest (POI) entities.

Provides relational queries, price range filtering, location matching,
and JSONB attribute filtering over PostgreSQL using SQLAlchemy 2.0 async.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.travelmate.infrastructure.database.models import PoiModel
from src.travelmate.infrastructure.database.repositories.base import PoiRepositoryProtocol

logger = structlog.get_logger(__name__)


class PoiRepository(PoiRepositoryProtocol):
    """PostgreSQL adapter implementing PoiRepositoryProtocol."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an active AsyncSession.

        Args:
            session: SQLAlchemy AsyncSession for executing queries.
        """
        self._session = session

    async def search_poi(
        self,
        location: str,
        category: str,
        budget_min: int | None = None,
        budget_max: int | None = None,
        preferences: list[str] | None = None,
        limit: int = 5,
    ) -> list[PoiModel]:
        """Search POI entities using relational filters.

        Args:
            location: Province or city name (e.g., 'Đà Nẵng').
            category: Domain category (e.g., 'ACCOM', 'FOOD', 'ATTRACTION').
            budget_min: Minimum price in VND.
            budget_max: Maximum price in VND.
            preferences: Attribute keywords to filter.
            limit: Maximum items to return.

        Returns:
            List of matching PoiModel instances.
        """
        loc_clean = location.strip().lower()
        stmt = select(PoiModel).where(
            (func.lower(PoiModel.location).contains(loc_clean))
            | (PoiModel.city_alias.cast(func.text()).ilike(f"%{loc_clean}%")),
            func.upper(PoiModel.category) == category.strip().upper(),
        )

        if budget_min is not None and budget_min > 0:
            stmt = stmt.where(PoiModel.price_numeric >= budget_min)

        if budget_max is not None and budget_max > 0:
            stmt = stmt.where(PoiModel.price_numeric <= budget_max)

        if preferences:
            # Filter if any of the preferences are present in JSONB attributes
            for pref in preferences:
                pref_clean = pref.strip().lower()
                if pref_clean:
                    # Match JSONB containment or text search within json array
                    stmt = stmt.where(
                        PoiModel.attributes.cast(func.text()).ilike(f"%{pref_clean}%")
                    )

        # Sort by rating descending, then price ascending
        stmt = stmt.order_by(PoiModel.rating.desc(), PoiModel.price_numeric.asc()).limit(limit)

        result = await self._session.execute(stmt)
        items = list(result.scalars().all())

        logger.debug(
            "Executed POI search",
            location=location,
            category=category,
            budget_max=budget_max,
            matched_count=len(items),
        )
        return items

    async def get_by_id(self, poi_id: str) -> PoiModel | None:
        """Fetch a specific POI by primary key.

        Args:
            poi_id: Unique identifier string.

        Returns:
            PoiModel instance if found, None otherwise.
        """
        stmt = select(PoiModel).where(PoiModel.poi_id == poi_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
