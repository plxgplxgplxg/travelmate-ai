"""Concrete repository implementation for Point of Interest (POI) entities.

Provides relational queries, price range filtering, location matching,
and JSONB attribute filtering over PostgreSQL using SQLAlchemy 2.0 async.
"""

from __future__ import annotations

import structlog
from sqlalchemy import Text, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
        loc_raw = location.strip()
        stmt = select(PoiModel).where(
            (func.lower(PoiModel.location).contains(loc_clean))
            | (PoiModel.city_alias.contains([loc_raw]))
            | (PoiModel.city_alias.cast(Text).ilike(f"%{loc_clean}%")),
            func.upper(PoiModel.category) == category.strip().upper(),
        )

        cat_upper = category.strip().upper()
        if budget_min is not None and budget_min > 0:
            if cat_upper == "ATTRACTION":
                # Free attractions (price 0) are kept unless expressly excluded
                stmt = stmt.where(
                    (PoiModel.price_numeric >= budget_min) | (PoiModel.price_numeric == 0)
                )
            else:
                stmt = stmt.where(PoiModel.price_numeric >= budget_min)

        if budget_max is not None and budget_max > 0:
            stmt = stmt.where(PoiModel.price_numeric <= budget_max)

        clean_prefs = [p.strip().lower() for p in (preferences or []) if p.strip()]
        if clean_prefs:
            # Match entities having any of the preferences, using GIN containment where possible
            pref_conditions = [
                PoiModel.attributes.contains([p]) | PoiModel.attributes.cast(Text).ilike(f"%{p}%")
                for p in clean_prefs
            ]
            stmt = stmt.where(or_(*pref_conditions))
            # Rank candidates by number of matched preferences descending, then rating desc, price asc
            pref_score = sum(
                case((PoiModel.attributes.contains([p]), 1), else_=0) for p in clean_prefs
            )
            stmt = stmt.order_by(
                pref_score.desc(), PoiModel.rating.desc(), PoiModel.price_numeric.asc()
            )
        else:
            # Sort by rating descending, then price ascending
            stmt = stmt.order_by(PoiModel.rating.desc(), PoiModel.price_numeric.asc())

        stmt = stmt.limit(limit)

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
