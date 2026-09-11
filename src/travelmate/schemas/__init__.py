"""Pydantic v2 schemas package for TravelMate AI contracts and data shapes."""

from src.travelmate.schemas.context import ContextState, IntentEnum, LocationState, ParamProvenance
from src.travelmate.schemas.evidence import Evidence, EvidenceCollection
from src.travelmate.schemas.tools import (
    KnowledgeChunkItem,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    PoiItem,
    PoiSearchRequest,
    PoiSearchResponse,
    ToolError,
)
from src.travelmate.schemas.trace import TraceRecord

__all__ = [
    "ContextState",
    "Evidence",
    "EvidenceCollection",
    "IntentEnum",
    "KnowledgeChunkItem",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResponse",
    "LocationState",
    "ParamProvenance",
    "PoiItem",
    "PoiSearchRequest",
    "PoiSearchResponse",
    "ToolError",
    "TraceRecord",
]
