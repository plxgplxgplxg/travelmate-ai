"""Database seed script for Points of Interest (POI).

Reads data/seed/mock_poi_data.json (30 records) and inserts them into the 'poi' PostgreSQL
table using SQLAlchemy 2.0 async.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
import structlog

from src.travelmate.infrastructure.database.models import PoiModel
from src.travelmate.infrastructure.database.session import close_db, get_db_session, init_db

logger = structlog.get_logger(__name__)


from datetime import datetime


async def seed_poi(json_file: Path | str | None = None) -> int:
    """Seed POI records from JSON file into PostgreSQL table.

    Args:
        json_file: Optional explicit path to POI data JSON file.

    Returns:
        Number of seeded records.
    """
    candidate_paths = (
        [Path(json_file)]
        if json_file
        else [
            Path("data/seed/mock_poi_data_v1_3.json"),
            Path("data/seed/mock_poi_data.json"),
            Path("mock_poi_data_v1_3.json"),
            Path("mock_poi_data.json"),
        ]
    )

    resolved_path: Path | None = None
    for p in candidate_paths:
        if p.exists():
            resolved_path = p
            break

    if not resolved_path:
        raise FileNotFoundError(f"POI data file not found among candidates: {candidate_paths}")

    with open(resolved_path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    items: list[dict[str, Any]] = data.get("items", [])
    logger.info("Loaded POI items from JSON", file=str(resolved_path), count=len(items))

    await init_db()

    async with get_db_session() as session:
        for item in items:
            verified_at_val = None
            if item.get("verified_at"):
                try:
                    verified_at_val = datetime.strptime(item["verified_at"], "%Y-%m-%d").date()
                except ValueError:
                    verified_at_val = None

            stmt = insert(PoiModel).values(
                poi_id=item["id"],
                name=item["name"],
                address=item["address"],
                location=item["location"],
                category=item["category"],
                rating=float(item.get("rating", 0.0)),
                price_info=item.get("price_info", ""),
                price_numeric=int(item.get("price_numeric", 0)),
                attributes=item.get("attributes", []),
                source=item.get("source", "deterministic_mock_v1"),
                source_url=item.get("source_url"),
                source_type=item.get("source_type", "official"),
                verified_at=verified_at_val,
                city_alias=item.get("city_alias", []),
                scope_and_limitations=item.get("scope_and_limitations"),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["poi_id"],
                set_={
                    "name": stmt.excluded.name,
                    "address": stmt.excluded.address,
                    "location": stmt.excluded.location,
                    "category": stmt.excluded.category,
                    "rating": stmt.excluded.rating,
                    "price_info": stmt.excluded.price_info,
                    "price_numeric": stmt.excluded.price_numeric,
                    "attributes": stmt.excluded.attributes,
                    "source": stmt.excluded.source,
                    "source_url": stmt.excluded.source_url,
                    "source_type": stmt.excluded.source_type,
                    "verified_at": stmt.excluded.verified_at,
                    "city_alias": stmt.excluded.city_alias,
                    "scope_and_limitations": stmt.excluded.scope_and_limitations,
                },
            )
            await session.execute(stmt)

        await session.commit()

    logger.info("Successfully seeded POI records", count=len(items))
    await close_db()
    return len(items)


if __name__ == "__main__":
    asyncio.run(seed_poi())
