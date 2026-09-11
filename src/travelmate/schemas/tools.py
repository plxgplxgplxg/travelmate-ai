"""Tool contract request and response schemas (CMP-07, CMP-08).

Defines structured payloads for poi_search and knowledge_search tools, ensuring
strict interface segregation and evidence normalization.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ToolError(BaseModel):
    """Standardized error structure for tool failures."""
    code: str | None = Field(default=None, description="System error code (e.g., ERR-TOOL-01)")
    message: str | None = Field(default=None, description="Human readable error message")


# === POI Search Contracts ===

class PoiSearchRequest(BaseModel):
    """Request parameters for poi_search tool."""
    location: str = Field(description="Province or city name (e.g., 'Đà Nẵng')")
    category: str = Field(
        default="ACCOM",
        description="One of ACCOM, FOOD, ATTRACTION, OTHER",
    )
    query: str | None = Field(default=None, description="Optional raw text query")
    budget_min: int | None = Field(default=None, description="Minimum price filter in VND")
    budget_max: int | None = Field(default=None, description="Maximum price filter in VND")
    preferences: list[str] = Field(
        default_factory=list,
        description="Filter keywords (e.g., ['quiet', 'near_beach', 'pool'])",
    )
    radius_m: int | None = Field(default=None, description="Search radius in meters")
    limit: int = Field(default=5, description="Maximum number of POIs to return")


class PoiItem(BaseModel):
    """Normalized point of interest item returned to Agent."""
    id: str = Field(description="POI identifier")
    name: str = Field(description="Display name")
    address: str = Field(description="Full address")
    category: str = Field(description="Category (ACCOM, FOOD, ATTRACTION)")
    rating: float = Field(default=0.0, description="Customer rating out of 5")
    price_info: str = Field(default="", description="Display price string")
    price_numeric: int = Field(default=0, description="Numeric price in VND")
    attributes: list[str] = Field(default_factory=list, description="Tag attributes")
    source: str = Field(default="poi_database", description="Origin source tag")
    source_url: str | None = Field(default=None, description="Official website URL")
    source_type: str = Field(default="official", description="Source trust category")
    verified_at: str | None = Field(default=None, description="Verification date YYYY-MM-DD")
    scope_and_limitations: str | None = Field(default=None, description="Seasonal volatility or limitations note")


class PoiSearchResponse(BaseModel):
    """Normalized response payload from poi_search tool."""
    status: Literal["OK", "EMPTY", "TIMEOUT", "BAD_REQUEST", "PROVIDER_ERROR"] = Field(
        default="OK",
        description="Execution status code",
    )
    items: list[PoiItem] = Field(default_factory=list, description="Matched POI records")
    error: ToolError | None = Field(default=None, description="Error detail if status is not OK")


# === Knowledge Search Contracts ===

class KnowledgeSearchRequest(BaseModel):
    """Request parameters for knowledge_search (RAG) tool."""
    query: str = Field(description="Search query string")
    top_k: int = Field(default=3, description="Maximum chunk count to retrieve")
    category: str | None = Field(default=None, description="Optional category filter")
    location: str | None = Field(default=None, description="Optional location filter")


class KnowledgeChunkItem(BaseModel):
    """Individual retrieved and ranked knowledge chunk."""
    chunk_id: str = Field(description="Chunk primary identifier")
    source_id: str = Field(description="Source document identifier")
    title: str = Field(description="Article title")
    content: str = Field(description="Grounding text content")
    score: float = Field(default=0.0, description="Combined RRF relevance score")
    source_url: str | None = Field(default=None, description="Official or public source URL")
    source_type: str = Field(default="official", description="Source authority classification")
    last_updated: str | None = Field(default=None, description="Last update date YYYY-MM-DD")
    scope_and_limitations: str | None = Field(default=None, description="Scope and seasonal note")


class KnowledgeSearchResponse(BaseModel):
    """Normalized response payload from knowledge_search tool."""
    status: Literal["OK", "EMPTY", "ERROR"] = Field(
        default="OK",
        description="Execution status code",
    )
    chunks: list[KnowledgeChunkItem] = Field(
        default_factory=list,
        description="Ranked knowledge chunks",
    )
    error: ToolError | None = Field(default=None, description="Error detail if status is ERROR")
