"""Context State and Intent Schemas (CMP-03, CMP-04, CMP-05).

Models multi-turn conversation memory, constraint parameters, and provenance classes
for state evolution across turns.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class IntentEnum(str, Enum):
    """Classified intent labels supported by Router (CMP-04)."""
    UC01_FIND_PLACE = "UC01_FIND_PLACE"
    UC02_RECOMMEND = "UC02_RECOMMEND"
    UC03_CONTEXT_FLOW = "UC03_CONTEXT_FLOW"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ParamProvenance(str, Enum):
    """Provenance origin classification for resolved parameters (CMP-05)."""
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    DERIVED = "DERIVED"
    CONTEXT = "CONTEXT"
    FORBIDDEN = "FORBIDDEN"


class LocationState(BaseModel):
    """Location parameter representation with origin tracking."""
    value: str | None = Field(default=None, description="Province or city name")
    source: Literal["explicit", "context", "derived"] = Field(
        default="explicit",
        description="Source of this location value",
    )


class BudgetState(BaseModel):
    """Budget constraint representation preserving original currency."""
    amount: int | None = Field(default=None, description="Monetary amount in numeric VND")
    currency: str | None = Field(default="VND", description="Currency code (e.g., VND)")
    scope: Literal["total", "per_person", "per_night", "unknown"] = Field(
        default="unknown",
        description="Scope of the budget constraint",
    )


class TravelerState(BaseModel):
    """Traveler companion profile."""
    types: list[str] = Field(
        default_factory=list,
        description="List of traveler types (elderly, children, couple, solo, group)",
    )


class DurationState(BaseModel):
    """Trip duration representation."""
    value: int | None = Field(default=None, description="Duration numeric value")
    unit: Literal["day", "night", "weekend", "unknown"] = Field(
        default="unknown",
        description="Duration time unit",
    )


class ResultItem(BaseModel):
    """Cached summary item from previous query results for reference resolution."""
    id: str = Field(description="Unique entity identifier")
    name: str = Field(description="Entity name")
    category: str = Field(description="Entity category")
    source: Literal["tool", "knowledge"] = Field(
        default="tool",
        description="Source data provider",
    )


class ContextState(BaseModel):
    """Global conversational context state schema (CMP-03).

    Persisted in Redis at ctx:{session_id} and synchronized into LangGraph State.
    """
    session_id: str = Field(description="Unique conversation session ID")
    current_intent: IntentEnum = Field(
        default=IntentEnum.UC01_FIND_PLACE,
        description="Active intent for this session",
    )
    location: LocationState = Field(
        default_factory=LocationState,
        description="Active destination location",
    )
    budget: BudgetState = Field(
        default_factory=BudgetState,
        description="Active budget constraint",
    )
    traveler: TravelerState = Field(
        default_factory=TravelerState,
        description="Traveler companion profiles",
    )
    preferences: list[str] = Field(
        default_factory=list,
        description="Preferences list (quiet, near_beach, pool, food, unique)",
    )
    duration: DurationState = Field(
        default_factory=DurationState,
        description="Trip duration constraint",
    )
    last_results: list[ResultItem] = Field(
        default_factory=list,
        description="Entity summaries returned in the previous turn",
    )
    context_version: str = Field(
        default="1.0",
        description="Schema or state migration version",
    )
