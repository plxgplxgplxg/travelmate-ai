# Phase 2 — Router (CMP-04) & Parameter Resolver (CMP-05)

---

## 1. Mục Tiêu & Nghiệp Vụ Cốt Lõi

1. **Router (CMP-04)**:
   - Phân loại ý định người dùng thành 1 trong 4 nhãn:
     - `UC01_FIND_PLACE`: Tìm kiếm cụ thể phòng khách sạn, homestay, quán ăn, quán cafe hoặc điểm tham quan.
     - `UC02_RECOMMEND`: Tư vấn lịch trình, gợi ý chuyến đi hoặc so sánh các phương án dựa trên nhiều ràng buộc (người già, trẻ nhỏ, ngân sách,...).
     - `UC03_CONTEXT_FLOW`: Hỏi tiếp, làm rõ hoặc cập nhật context hội thoại đa lượt.
     - `OUT_OF_SCOPE`: Câu hỏi ngoài phạm vi du lịch.
   - **Tuân thủ Rule 4**: Gọi LLM thông qua `LLMClientProtocol` từ `src.travelmate.clients.llm_client`, không import trực tiếp SDK OpenAI/Anthropic trong node.

2. **Parameter Resolver (CMP-05)**:
   - Trích xuất các tham số thực tế từ query hiện tại kết hợp với `context` đang lưu:
     - `location` (bắt buộc: nếu có trong câu hỏi hiện tại thì ghi đè theo **BR-UC01-01**).
     - `category` (suy luận `ACCOM`, `FOOD`, `ATTRACTION`).
     - `budget_max` (chuyển đổi "2 triệu" -> `2000000`, giữ nguyên giá trị theo **BR-UC01-03**).
     - `preferences` (mảng từ khóa: `near_beach`, `quiet`, `pool`,...).
     - `traveler` (loại du khách: `elderly`, `children`,...).
   - Sử dụng `LLMClientProtocol.complete(..., json_mode=True)`.

---

## 2. Sơ Đồ Luồng Router & Resolver

```mermaid
graph TD
    IN["TravelMateState (raw_user_input, context)"] --> RT["Router Node (CMP-04)"]
    RT -->|complete(json_mode=True)| CLIENT["LLMClient (clients/llm_client.py)"]
    CLIENT -->|DeepSeek-V3 API| CLIENT_RES["RouteClassification JSON"]
    CLIENT_RES --> RT
    
    RT -->|OUT_OF_SCOPE| END_OOS["Rẽ nhánh: Trả lời từ chối lịch sự"]
    RT -->|UC01 / UC02 / UC03| PR["Parameter Resolver Node (CMP-05)"]
    
    PR -->|complete(json_mode=True)| CLIENT
    CLIENT -->|DeepSeek-V3 API| PARAMS["Extracted Parameters JSON"]
    PARAMS --> PR
    
    PR --> MERGE{"Quy tắc Nghiệp vụ BR-UC01"}
    MERGE -->|Query có Location mới| OVERWRITE["Ghi đè Location mới"]
    MERGE -->|Query thiếu Location| KEEP["Giữ Location từ Context cũ"]
    
    OVERWRITE --> UPDATED["Cập nhật State (extracted_params, context)"]
    KEEP --> UPDATED
    UPDATED --> NEXT["Chuyển tiếp sang Tool Orchestrator"]
```

---

## 3. Mã Nguồn Cần Code Trong Phase Này

### File 1: `src/travelmate/graph/nodes/router.py`

> **Vị trí tạo file**: `src/travelmate/graph/nodes/router.py`  
> **Giải thích**: Node phân loại intent sử dụng `LLMClientProtocol` thay vì import trực tiếp SDK OpenAI, có prompt rõ ràng và fallback an toàn.

```python
"""Router Node implementation (CMP-04).

Classifies incoming user intent into UC01_FIND_PLACE, UC02_RECOMMEND,
UC03_CONTEXT_FLOW, or OUT_OF_SCOPE using LLMClientProtocol.
"""

from __future__ import annotations

import json
from typing import Any, Literal
from pydantic import BaseModel, Field
import structlog

from src.travelmate.clients.llm_client import LLMClientProtocol
from src.travelmate.graph.state import TravelMateState
from src.travelmate.schemas.context import IntentEnum

logger = structlog.get_logger(__name__)


class RouteClassification(BaseModel):
    """Structured LLM output for intent routing."""
    intent: Literal["UC01_FIND_PLACE", "UC02_RECOMMEND", "UC03_CONTEXT_FLOW", "OUT_OF_SCOPE"] = Field(
        description="Classified user intent label",
    )
    confidence: float = Field(default=1.0, description="Model confidence score between 0.0 and 1.0")
    reasoning: str = Field(description="Short rationale for this classification")


ROUTER_SYSTEM_PROMPT = """Bạn là Router phân loại ý định người dùng cho Trợ lý Du lịch TravelMate AI.
Nhiệm vụ của bạn là phân loại câu nói của người dùng vào chính xác 1 trong 4 nhãn sau:

1. UC01_FIND_PLACE: Người dùng muốn tìm kiếm địa điểm cụ thể (khách sạn, resort, homestay, quán ăn, nhà hàng, quán cafe, điểm tham quan, vui chơi).
   Ví dụ: "Tìm khách sạn ở Đà Nẵng", "Chỉ tôi quán cafe đẹp ở Hội An", "Có homestay nào dưới 1 triệu gần biển không?"

2. UC02_RECOMMEND: Người dùng cần tư vấn, lập phương án du lịch, gợi ý lịch trình tổng thể hoặc so sánh có nhiều ràng buộc phức tạp (ngân sách tổng, người già, trẻ nhỏ, số ngày đi).
   Ví dụ: "Gia đình có người già đi Đà Nẵng 3N2Đ nên đi đâu", "Có 5 triệu đi Huế cuối tuần thì chơi gì", "Tư vấn lịch trình nghỉ dưỡng".

3. UC03_CONTEXT_FLOW: Người dùng đang tiếp tục hội thoại trước đó, hỏi thêm thông tin về địa điểm vừa tìm thấy, hoặc thay đổi/bổ sung một tiêu chí nhỏ.
   Ví dụ: "Thế chỗ thứ 2 có bể bơi không?", "Còn chỗ nào khác nữa không?", "Đổi sang tìm quán ăn gần đấy".

4. OUT_OF_SCOPE: Câu hỏi hoàn toàn không liên quan đến du lịch (lập trình, giải toán, chính trị, y tế, viết văn không liên quan, hack, tấn công).
   Ví dụ: "Viết cho tôi hàm Python quicksort", "Thủ đô của Pháp là gì?", "Bạn nghĩ sao về kinh tế toàn cầu?".

Bắt buộc trả về đúng cấu trúc JSON với các trường: intent, confidence, reasoning."""


async def router_node(state: TravelMateState, llm_client: LLMClientProtocol | None = None) -> dict[str, Any]:
    """Execute Router node classifying intent.

    Args:
        state: Current TravelMateState snapshot.
        llm_client: Optional injected LLM client. If None, resolves from dependencies.

    Returns:
        State update dictionary containing 'current_intent'.
    """
    raw_input = state.get("raw_user_input", "")
    session_id = state.get("session_id", "default_session")

    if not raw_input.strip():
        return {"current_intent": IntentEnum.OUT_OF_SCOPE.value}

    if llm_client is None:
        from src.travelmate.api.deps import get_llm_client
        llm_client = get_llm_client()

    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Câu người dùng: {raw_input}"},
    ]

    try:
        content = await llm_client.complete(messages=messages, temperature=0.0, json_mode=True)
        parsed = json.loads(content)
        route_obj = RouteClassification.model_validate(parsed)
        selected_intent = route_obj.intent

        logger.info(
            "Router classified intent",
            session_id=session_id,
            intent=selected_intent,
            confidence=route_obj.confidence,
        )
    except Exception as exc:
        logger.warning("LLM router failed, falling back to heuristic routing", error=str(exc))
        lowered = raw_input.lower()
        if any(k in lowered for k in ["tìm", "khách sạn", "quán", "ở đâu", "ăn gì", "chỗ nào"]):
            selected_intent = IntentEnum.UC01_FIND_PLACE.value
        elif any(k in lowered for k in ["tư vấn", "lịch trình", "gợi ý", "người già", "triệu"]):
            selected_intent = IntentEnum.UC02_RECOMMEND.value
        else:
            selected_intent = IntentEnum.UC01_FIND_PLACE.value

    return {"current_intent": selected_intent}
```

---

### File 2: `src/travelmate/graph/nodes/resolver.py`

> **Vị trí tạo file**: `src/travelmate/graph/nodes/resolver.py`  
> **Giải thích**: Node trích xuất tham số có cấu trúc (Parameter Resolver - CMP-05) qua `LLMClientProtocol`. Chuyển đổi ngôn ngữ tự nhiên thành các trường chuẩn và áp dụng quy tắc nghiệp vụ BR-UC01-01 (ghi đè location mới).

```python
"""Parameter Resolver Node implementation (CMP-05).

Extracts structured travel parameters (location, category, budget, preferences)
from user input using LLMClientProtocol and merges them with previous context state.
"""

from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, Field
import structlog

from src.travelmate.clients.llm_client import LLMClientProtocol
from src.travelmate.graph.state import TravelMateState
from src.travelmate.schemas.context import ContextState, LocationState

logger = structlog.get_logger(__name__)


class ExtractedParameters(BaseModel):
    """Pydantic model for parameter extraction from user query."""
    location: str | None = Field(
        default=None,
        description="Province or city in Vietnam (e.g., 'Đà Nẵng', 'Hội An', 'Phú Quốc', 'Huế')",
    )
    category: str | None = Field(
        default="ACCOM",
        description="Category: 'ACCOM' (khách sạn/lưu trú), 'FOOD' (ăn uống/quán cafe), 'ATTRACTION' (tham quan)",
    )
    budget_max: int | None = Field(
        default=None,
        description="Maximum budget in VND (e.g., '2 triệu' -> 2000000, '500k' -> 500000)",
    )
    budget_min: int | None = Field(
        default=None,
        description="Minimum budget in VND if specified",
    )
    preferences: list[str] = Field(
        default_factory=list,
        description="Preference tags (e.g., ['near_beach', 'quiet', 'pool', 'street_food'])",
    )
    traveler_types: list[str] = Field(
        default_factory=list,
        description="Traveler companions (e.g., ['elderly', 'children', 'couple', 'solo'])",
    )
    duration_days: int | None = Field(
        default=None,
        description="Duration in days if mentioned (e.g., '3N2Đ' -> 3)",
    )


RESOLVER_SYSTEM_PROMPT = """Bạn là chuyên gia bóc tách tham số du lịch cho TravelMate AI.
Hãy trích xuất các thông tin có cấu trúc từ câu nói của người dùng:
1. location: Tên Tỉnh/Thành phố hoặc địa danh tại Việt Nam (ví dụ: 'Đà Nẵng', 'Hội An', 'Huế', 'Phú Quốc'). Nếu người dùng không nhắc đến, để null.
2. category: Một trong 3 loại: 'ACCOM' (lưu trú/khách sạn/resort), 'FOOD' (quán ăn/ẩm thực/cafe), 'ATTRACTION' (điểm tham quan/vui chơi).
3. budget_max: Số tiền tối đa tính bằng VND (nguyên số). Ví dụ: '2 triệu' -> 2000000, '1tr5' -> 1500000, '500k' -> 500000.
4. preferences: Mảng từ khóa chuẩn hóa tiếng Anh ngắn gọn, ví dụ: ['near_beach', 'quiet', 'pool', 'luxury', 'budget', 'street_food', 'traditional'].
5. traveler_types: Mảng đối tượng, ví dụ: ['elderly', 'children', 'couple', 'solo', 'group'].
6. duration_days: Số ngày đi (ví dụ: '3 ngày 2 đêm' -> 3).

Chỉ trả về định dạng JSON hợp lệ tuân thủ schema."""


async def resolver_node(state: TravelMateState, llm_client: LLMClientProtocol | None = None) -> dict[str, Any]:
    """Execute Parameter Resolver node.

    Args:
        state: Current TravelMateState snapshot.
        llm_client: Optional injected LLM client. If None, resolves from dependencies.

    Returns:
        State update dictionary containing 'extracted_params' and updated 'context'.
    """
    raw_input = state.get("raw_user_input", "")
    context_data = state.get("context") or {}
    ctx_obj = ContextState.model_validate(context_data)

    if llm_client is None:
        from src.travelmate.api.deps import get_llm_client
        llm_client = get_llm_client()

    messages = [
        {"role": "system", "content": RESOLVER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Câu người dùng: {raw_input}"},
    ]

    try:
        content = await llm_client.complete(messages=messages, temperature=0.0, json_mode=True)
        parsed = json.loads(content)
        extracted = ExtractedParameters.model_validate(parsed)
    except Exception as exc:
        logger.warning("LLM resolver extraction failed, using defaults", error=str(exc))
        extracted = ExtractedParameters()

    # Rule BR-UC01-01: Explicit location in current query overrides context
    final_location = extracted.location
    location_source = "explicit"
    if not final_location:
        if ctx_obj.location and ctx_obj.location.value:
            final_location = ctx_obj.location.value
            location_source = "context"

    combined_prefs = list(set(ctx_obj.preferences + extracted.preferences))

    # Update context state
    ctx_obj.location = LocationState(value=final_location, source=location_source)
    if extracted.budget_max is not None:
        ctx_obj.budget.amount = extracted.budget_max
    if extracted.traveler_types:
        ctx_obj.traveler.types = extracted.traveler_types
    ctx_obj.preferences = combined_prefs

    resolved_params = {
        "location": final_location,
        "category": extracted.category or "ACCOM",
        "budget_max": extracted.budget_max or ctx_obj.budget.amount,
        "budget_min": extracted.budget_min,
        "preferences": combined_prefs,
        "traveler_types": ctx_obj.traveler.types,
        "duration_days": extracted.duration_days,
        "needs_clarification": final_location is None,
    }

    logger.info(
        "Resolved query parameters",
        location=final_location,
        category=resolved_params["category"],
        budget_max=resolved_params["budget_max"],
    )

    return {
        "extracted_params": resolved_params,
        "context": ctx_obj.model_dump(),
    }
```

---

## 4. Tóm Tắt & Giải Thích Chi Tiết

1. **Tuân thủ Rule 4 (External SDKs stay behind clients)**:
   - Cả `router_node` và `resolver_node` đều sử dụng `LLMClientProtocol` với hàm `complete(..., json_mode=True)`.
   - Điều này giúp code gọn gàng, không phụ thuộc vào `openai.AsyncOpenAI` hay `anthropic.AsyncAnthropic`.
   - Khi viết unit tests, bạn có thể truyền `MockLLMClient` vào để test trong tích tắc mà không tốn token hay phụ thuộc kết nối internet.

2. **Quy tắc ghi đè location (BR-UC01-01)**:
   - Nếu câu nói hiện tại có location mới (ví dụ "Đổi sang Hội An"), giá trị mới sẽ ghi đè và đánh dấu `source="explicit"`.
   - Nếu câu nói hiện tại không nhắc đến location (ví dụ "Khách sạn nào có bể bơi?"), hệ thống sẽ tái sử dụng location từ context cũ và đánh dấu `source="context"`.
