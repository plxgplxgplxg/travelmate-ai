"""Router Node implementation (CMP-04).

Classifies incoming user intent into UC01_FIND_PLACE, UC02_RECOMMEND, UC03_CONTEXT_FLOW, OR OUT_OF_SCOPE using LLMClientProtocol.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import structlog
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.travelmate.clients.base import LLMClientProtocol
from src.travelmate.graph.state import TravelMateState
from src.travelmate.schemas.context import IntentEnum

logger = structlog.get_logger(__name__)


class RouteClassification(BaseModel):
    """Structured LLM output for intent routing."""

    intent: Literal["UC01_FIND_PLACE", "UC02_RECOMMEND", "UC03_CONTEXT_FLOW", "OUT_OF_SCOPE"] = (
        Field(
            description="Classified user intent label",
        )
    )
    confidence: float = Field(
        default=1.0, description="Confidence score of the classification (0.0 to 1.0)"
    )
    reasoning: str = Field(description="Short rationable for this classification")


ROUTER_SYSTEM_PROMPT = """
Bạn là Router phân loại ý định người dùng cho Trợ lý Du lịch TravelMate AI.
Phân loại câu nói mới nhất của người dùng vào đúng 1 trong 4 nhãn, dựa trên NGỮ CẢNH hội thoại trước đó (nếu có).

1. UC01_FIND_PLACE — Tìm địa điểm cụ thể, không có ràng buộc tổng thể phức tạp
   (khách sạn, resort, homestay, quán ăn, cafe, điểm tham quan).
   Đặc điểm: có tối đa 1-2 tiêu chí lọc đơn giản (giá, vị trí, loại hình).
   VD: "Tìm khách sạn ở Đà Nẵng", "Quán cafe đẹp ở Hội An",
       "Homestay dưới 1 triệu gần biển"

2. UC02_RECOMMEND — Tư vấn/lập lịch trình, có ≥2 ràng buộc tổng thể
   (ngân sách toàn chuyến, số ngày, đối tượng đặc biệt: người già/trẻ nhỏ,
   mục đích chuyến đi, so sánh nhiều lựa chọn).
   VD: "Gia đình có người già đi Đà Nẵng 3N2Đ nên đi đâu",
       "5 triệu đi Huế cuối tuần chơi gì"

   !Tie-breaker: nếu câu vừa "tìm chỗ" vừa có ≥2 ràng buộc tổng thể
   (ngân sách + đối tượng, hoặc ngân sách + số ngày) → chọn UC02.

3. UC03_CONTEXT_FLOW — Câu phụ thuộc vào kết quả/ngữ cảnh ngay trước đó.
   VD: "Thế chỗ thứ 2 có bể bơi không?", "Còn chỗ nào khác không?",
       "Đổi sang tìm quán ăn gần đấy"
   !Nếu không có lịch sử hội thoại trước đó mà câu vẫn mang tính "tiếp nối"
   (vd dùng "thế", "còn", "chỗ đó") → hạ confidence, không tự suy diễn ngữ cảnh.

4. OUT_OF_SCOPE — Không liên quan du lịch.
   VD: "Viết hàm Python quicksort", "Thủ đô Pháp là gì?",
       "Kinh tế toàn cầu đang thế nào?"

QUY TẮC CONFIDENCE:
- 0.85–1.0: khớp rõ ràng với 1 mẫu ví dụ hoặc quy tắc trên
- 0.6–0.84: cần suy luận, có thể lẫn giữa 2 nhãn
- <0.6: mơ hồ, cân nhắc yêu cầu người dùng làm rõ thay vì đoán

Chỉ trả về JSON đúng schema, không thêm văn bản khác:
{
  "intent": "UC01_FIND_PLACE | UC02_RECOMMEND | UC03_CONTEXT_FLOW | OUT_OF_SCOPE",
  "confidence": 0.0,
  "reasoning": "..."
}
"""


async def router_node(state: TravelMateState, config: RunnableConfig) -> dict[str, Any]:
    """Execute Router node classifying intent.

    Dependencies are injected via LangGraph's RunnableConfig mechanism, elimitnating Service Locator anti-pattern and enabling clean testability.

    Args:
        state: Current TravelMateState snapshot.
        config: LangGraph runtime configuration containing injected deppendencies.

    Returns:
        State update dictionary containing 'current_intent'.
    """
    raw_input = state.get("raw_user_input", "")
    session_id = state.get("session_id", "default_session")

    if not raw_input.strip():
        return {"current_intent": IntentEnum.OUT_OF_SCOPE.value}

    configurable = config.get("configurable") or {}
    llm_client: LLMClientProtocol | None = configurable.get("llm_client")
    if llm_client is None:
        raise ValueError("llm_client must be provided in RunnableConfig['configurable']")

    message = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Câu hỏi người dùng: {raw_input}"},
    ]

    try:
        content = await llm_client.complete(messages=message, temperature=0.0, json_mode=True)
        parsed = json.loads(content)
        route_obj = RouteClassification.model_validate(parsed)
        selected_intent = route_obj.intent
        confidence = float(route_obj.confidence)

        logger.info(
            "Router classified intent",
            session_id=session_id,
            intent=selected_intent,
            confidence=confidence,
        )
    except Exception as e:
        logger.warning("LLM router failed, falling back to heuristic routing", error=str(e))
        confidence = 0.7
        lowered = raw_input.lower()
        if any(k in lowered for k in ["tìm", "khách sạn", "quán", "ở đâu", "ăn gì", "chỗ nào"]):
            selected_intent = IntentEnum.UC01_FIND_PLACE.value
        elif any(k in lowered for k in ["tư vấn", "lịch trình", "gợi ý", "người già", "triệu"]):
            selected_intent = IntentEnum.UC02_RECOMMEND.value
        else:
            selected_intent = IntentEnum.UC01_FIND_PLACE.value

    return {
        "current_intent": selected_intent,
        "confidence": confidence,
    }
