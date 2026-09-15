"""Parameter Resolver Node implementation (CMP-05).

Extracts structured travel parameters (location, categories, budget, preferences, companions)
from user input using LLMClientProtocol, merges them with previous context state,
and initializes cyclic loop parameters for multi-intent support.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Literal

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.travelmate.clients.llm_client import LLMClientProtocol
from src.travelmate.graph.state import TravelMateState
from src.travelmate.schemas.context import ContextState, LocationState

logger = structlog.get_logger(__name__)

# Closed vocabulary for preferences (aligned with mock_poi_data_v1_3.json)
ALLOWED_PREFERENCES = [
    "boutique",
    "budget",
    "cafe",
    "central_location",
    "children_friendly",
    "cozy",
    "culture",
    "elderly_friendly",
    "family_friendly",
    "garden",
    "hotpot",
    "local_food",
    "luxury",
    "nature",
    "near_beach",
    "new_opening",
    "night_life",
    "night_market",
    "pet_friendly",
    "pool",
    "quiet",
    "riverside",
    "seafood",
    "signature",
    "social",
    "street_food",
    "suitable_for_elderly",
    "tourist_friendly",
    "traditional",
    "vegetarian_friendly",
    "view",
    "wifi",
]

# Closed vocabulary for traveler companion types
ALLOWED_TRAVELER_TYPES = [
    "elderly",
    "children",
    "couple",
    "solo",
    "group",
    "family",
]


class ExtractedParameters(BaseModel):
    """Structured travel parameters extracted from user query (CMP-05)."""

    location: str | None = Field(
        default=None,
        description="Destination province or city in Vietnam (e.g., 'Hà Nội', 'Đà Nẵng', 'Hội An')",
    )
    categories: list[Literal["ACCOM", "FOOD", "ATTRACTION"]] = Field(
        default_factory=list,
        description="List of categories: 'ACCOM', 'FOOD', 'ATTRACTION'",
    )
    budget_max: int | None = Field(
        default=None,
        description="Maximum budget in VND integer (e.g., '2 triệu' -> 2000000, '500k' -> 500000)",
    )
    budget_min: int | None = Field(
        default=None,
        description="Minimum budget in VND integer if specified",
    )
    budget_scope: Literal["per_night", "per_person", "total_trip"] | None = Field(
        default=None,
        description="Scope of budget: 'per_night', 'per_person', 'total_trip'",
    )
    preferences: list[str] = Field(
        default_factory=list,
        description="Preference tags from closed list (e.g., ['near_beach', 'quiet'])",
    )
    traveler_types: list[str] = Field(
        default_factory=list,
        description="Traveler companions from closed list (e.g., ['elderly', 'children'])",
    )
    num_travelers: int | None = Field(
        default=None,
        description="Specific number of travelers if mentioned (e.g., 4)",
    )
    duration_days: int | None = Field(
        default=None,
        description="Duration in days if mentioned (e.g., '3N2Đ' -> 3, 'cuối tuần' -> 2)",
    )
    travel_date: str | None = Field(
        default=None,
        description="Travel timing if mentioned (e.g., 'cuối tuần này', '2/9')",
    )
    needs_clarification: bool = Field(
        default=False,
        description="Flag indicating missing critical parameters requiring user clarification",
    )


RESOLVER_SYSTEM_PROMPT = """Bạn là chuyên gia bóc tách tham số du lịch cho TravelMate AI.
Trích xuất thông tin có cấu trúc từ câu nói của người dùng. Nếu một field không được nhắc đến hoặc không suy luận được chắc chắn, để null (không tự bịa giá trị).

1. location: Tên Tỉnh/Thành phố hoặc địa danh tại Việt Nam là ĐIỂM ĐẾN người dùng muốn tìm/đi tới (không phải điểm xuất phát). VD: "Đà Nẵng", "Hội An", "Huế", "Phú Quốc".
   Nếu câu có cả điểm đi và điểm đến (vd "từ Hà Nội đi Đà Nẵng"), lấy điểm đến. Nếu câu không nhắc đến địa điểm, để null.

2. categories: Mảng gồm một hoặc nhiều trong: "ACCOM" (lưu trú), "FOOD" (ăn uống/cafe), "ATTRACTION" (tham quan/vui chơi). Một câu có thể chứa nhiều category cùng lúc.
   Nếu câu không nhắc category cụ thể nào (vd chỉ hỏi lịch trình tổng thể), để mảng rỗng [].

3. budget_max: Số tiền tối đa bằng VND (nguyên số).
   Quy đổi: "2 triệu"/"2tr" -> 2000000, "1tr5"/"1.5tr" -> 1500000, "500k" -> 500000.
   budget_min: Số tiền tối thiểu bằng VND nếu có nhắc, không nhắc thì null.
   budget_scope: PHẢI xác định kèm theo khi có budget_max, một trong: "per_night", "per_person", "total_trip".
   Suy luận dựa trên ngữ cảnh (vd "khách sạn 2 triệu" -> per_night; "5 triệu đi Huế cuối tuần" -> total_trip; "ăn 200k/người" -> per_person). Nếu không rõ, để "total_trip". Nếu không có budget, để null.

4. preferences: Mảng, CHỈ chọn từ danh sách đóng sau (không tự tạo nhãn mới):
   ["boutique", "budget", "cafe", "central_location", "children_friendly", "cozy", "culture", "elderly_friendly", "family_friendly", "garden", "hotpot", "local_food", "luxury", "nature", "near_beach", "new_opening", "night_life", "night_market", "pet_friendly", "pool", "quiet", "riverside", "seafood", "signature", "social", "street_food", "suitable_for_elderly", "tourist_friendly", "traditional", "vegetarian_friendly", "view", "wifi"]
   Quy đổi ngữ nghĩa thực tế:
   - "hải sản" -> "seafood"
   - "ăn chay", "quán chay" -> "vegetarian_friendly"
   - "quán lẩu" -> "hotpot"
   - "đặc sản", "món địa phương" -> "local_food"
   - "quán cafe", "cà phê" -> "cafe"
   - "chợ đêm" -> "night_market"
   - "người già", "người lớn tuổi" -> "elderly_friendly"
   - "trẻ em", "con nhỏ" -> "children_friendly"
   - "view đẹp", "ngắm cảnh" -> "view"
   - "ven sông", "bờ sông" -> "riverside"
   - "khuôn viên vườn", "sân vườn" -> "garden"

5. traveler_types: Mảng, CHỈ chọn từ: ["elderly", "children", "couple", "solo", "group", "family"]

6. num_travelers: Số người đi cụ thể nếu được nhắc (vd "đi 4 người" -> 4). Nếu không có, null.

7. duration_days: Số ngày đi. "3 ngày 2 đêm" -> 3, "2 đêm" -> 3, "cuối tuần" -> 2. Nếu không nhắc, null.

8. travel_date: Thời điểm đi nếu được nhắc (chuẩn hóa dạng mô tả ngắn, vd "cuối tuần này", "2/9", "tháng sau"). Nếu không nhắc, null.

Ví dụ:
Input: "Tìm khách sạn 2 triệu gần biển ở Đà Nẵng cho gia đình có con nhỏ, đi 4 người"
Output: {"location": "Đà Nẵng", "categories": ["ACCOM"], "budget_max": 2000000, "budget_min": null, "budget_scope": "per_night", "preferences": ["near_beach", "children_friendly", "family_friendly"], "traveler_types": ["children", "family"], "num_travelers": 4, "duration_days": null, "travel_date": null}

Input: "5 triệu đi Huế cuối tuần này chơi gì, ăn hải sản và bún bò"
Output: {"location": "Huế", "categories": ["FOOD", "ATTRACTION"], "budget_max": 5000000, "budget_min": null, "budget_scope": "total_trip", "preferences": ["seafood", "local_food"], "traveler_types": [], "num_travelers": null, "duration_days": 2, "travel_date": "cuối tuần này"}

Input: "Tìm homestay ven sông và quán cafe view đẹp ở Hội An"
Output: {"location": "Hội An", "categories": ["ACCOM", "FOOD"], "budget_max": null, "budget_min": null, "budget_scope": null, "preferences": ["riverside", "cafe", "view"], "traveler_types": [], "num_travelers": null, "duration_days": null, "travel_date": null}

Input: "Gợi ý quán ăn chay và khách sạn yên tĩnh cho người lớn tuổi ở Đà Lạt"
Output: {"location": "Đà Lạt", "categories": ["ACCOM", "FOOD"], "budget_max": null, "budget_min": null, "budget_scope": null, "preferences": ["vegetarian_friendly", "quiet", "elderly_friendly"], "traveler_types": ["elderly"], "num_travelers": null, "duration_days": null, "travel_date": null}

Chỉ trả về JSON hợp lệ đúng schema, không thêm văn bản khác."""


def normalize_text(text: str) -> str:
    """Normalize text to lowercase without Vietnamese diacritics."""
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


MULTI_INTENT_KEYWORDS: dict[str, list[str]] = {
    "ACCOM": [
        "khach san",
        "resort",
        "homestay",
        "nha nghi",
        "phong o",
        "luu tru",
        "cho o",
        "villa",
        "hostel",
        "biet thu",
        "can ho dich vu",
    ],
    "FOOD": [
        "an gi",
        "quan an",
        "nha hang",
        "am thuc",
        "quan cafe",
        "cafe",
        "dac san",
        "bun",
        "pho",
        "com",
        "hai san",
        "buffet",
        "quan nhau",
        "tra sua",
    ],
    "ATTRACTION": [
        "tham quan",
        "diem den",
        "choi gi",
        "vui choi",
        "danh lam",
        "bao tang",
        "cong vien",
        "cho dem",
        "pho co",
        "khu du lich",
    ],
}


def match_categories(text: str) -> list[str]:
    """Fast-path fallback: return matching categories from keyword dictionary.

    Args:
        text: Raw user query string.

    Returns:
        List of matching categories ("ACCOM", "FOOD", "ATTRACTION").
    """
    normalized = normalize_text(text)
    matched: list[str] = []
    for category, keywords in MULTI_INTENT_KEYWORDS.items():
        if any(kw in normalized for kw in keywords):
            matched.append(category)
    return matched


async def resolver_node(
    state: TravelMateState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Execute Parameter Resolver node logic.

    Extracts parameters via LLMClientProtocol, merges with conversation context,
    enforces business rules (BR-UC01-01), and initializes pending_intents for ReAct loop.

    Args:
        state: Current TravelMateState snapshot.
        config: LangGraph runtime configuration with injected dependencies.

    Returns:
        State update dictionary containing 'extracted_params', updated 'context',
        and cyclic loop control fields.

    Raises:
        ValueError: If llm_client is missing in config['configurable'].
    """
    raw_input = state.get("raw_user_input", "")
    session_id = state.get("session_id", "default_session")
    context_data = state.get("context") or {}
    if not context_data.get("session_id"):
        ctx_obj = ContextState(session_id=session_id)
    else:
        ctx_obj = ContextState.model_validate(context_data)

    configurable = config.get("configurable") or {}
    llm_client: LLMClientProtocol | None = configurable.get("llm_client")
    if llm_client is None:
        raise ValueError("llm_client must be provided in RunnableConfig['configurable']")

    messages = [
        {"role": "system", "content": RESOLVER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Câu người dùng: {raw_input}"},
    ]

    try:
        content = await llm_client.complete(messages=messages, temperature=0.0, json_mode=True)
        parsed = json.loads(content)
        extracted = ExtractedParameters.model_validate(parsed)
        logger.info("Extracted parameters via LLM", extracted=extracted.model_dump())
    except Exception as exc:
        logger.warning(
            "LLM parameter extraction failed, falling back to heuristics", error=str(exc)
        )
        extracted = ExtractedParameters()

    # 1. Resolve Multi-Category: Use LLM output as primary, fallback to keyword matching
    resolved_categories: list[Literal["ACCOM", "FOOD", "ATTRACTION"]] = list(extracted.categories)
    if not resolved_categories:
        fallback_matched = match_categories(raw_input)
        for cat in fallback_matched:
            if cat in ("ACCOM", "FOOD", "ATTRACTION"):
                resolved_categories.append(cat)  # type: ignore[arg-type]

    # If still empty, default to ACCOM for safety
    if not resolved_categories:
        resolved_categories = ["ACCOM"]

    extracted.categories = resolved_categories

    # 2. Rule BR-UC01-01: Explicit Location overwrites Context; Missing Location inherits Context
    loc_source: Literal["explicit", "context", "derived"] = "explicit"
    if extracted.location and extracted.location.strip():
        final_location = extracted.location.strip()
        loc_source = "explicit"
        ctx_obj.location = LocationState(value=final_location, source=loc_source)
    elif ctx_obj.location and ctx_obj.location.value and ctx_obj.location.value.strip():
        final_location = ctx_obj.location.value.strip()
        loc_source = "context"
    else:
        final_location = None
        loc_source = "explicit"
        extracted.needs_clarification = True

    extracted.location = final_location

    # 3. Rule BR-UC01-03: Merge Budget into Context if provided
    if extracted.budget_max is not None:
        ctx_obj.budget.amount = extracted.budget_max
        if extracted.budget_scope:
            ctx_obj.budget.scope = extracted.budget_scope

    # 4. Merge Preferences (filter against closed vocabulary)
    valid_prefs = [p for p in extracted.preferences if p in ALLOWED_PREFERENCES]
    for pref in valid_prefs:
        if pref not in ctx_obj.preferences:
            ctx_obj.preferences.append(pref)

    # 5. Merge Traveler companions and map to companion preferences
    valid_travelers = [t for t in extracted.traveler_types if t in ALLOWED_TRAVELER_TYPES]
    for t in valid_travelers:
        if t not in ctx_obj.traveler.types:
            ctx_obj.traveler.types.append(t)
    extracted.traveler_types = valid_travelers

    # Map companion types into corresponding POI attribute preferences if not present
    companion_pref_map = {
        "elderly": "elderly_friendly",
        "children": "children_friendly",
        "family": "family_friendly",
    }
    for t in valid_travelers:
        mapped_pref = companion_pref_map.get(t)
        if mapped_pref and mapped_pref not in valid_prefs:
            valid_prefs.append(mapped_pref)
        if mapped_pref and mapped_pref not in ctx_obj.preferences:
            ctx_obj.preferences.append(mapped_pref)
    extracted.preferences = valid_prefs

    # 6. Merge Duration
    if extracted.duration_days is not None:
        ctx_obj.duration.value = extracted.duration_days

    # 7. Setup cyclic loop state: pending_intents from resolved categories
    pending_intents: list[str] = [cat for cat in resolved_categories]

    logger.info(
        "Resolved parameters successfully",
        location=final_location,
        location_source=loc_source,
        categories=resolved_categories,
        pending_intents=pending_intents,
        budget_max=extracted.budget_max,
        budget_scope=extracted.budget_scope,
        needs_clarification=extracted.needs_clarification,
    )

    return {
        "extracted_params": extracted.model_dump(),
        "context": ctx_obj.model_dump(),
        "pending_intents": pending_intents,
        "completed_tools": [],
        "tool_iterations": 0,
        "needs_more_tools": bool(len(pending_intents) > 1),
    }
