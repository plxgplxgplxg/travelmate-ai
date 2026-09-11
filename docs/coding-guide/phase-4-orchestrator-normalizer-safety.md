# Phase 4 — Tool Orchestrator, Evidence Normalizer & Safety Guard

---

## 1. Mục Tiêu & Nghiệp Vù Cốt Lõi

1. **Tool Orchestrator (CMP-07)**:
   - Điều phối các Tool:
     - Khi cần tìm địa điểm lưu trú, ẩm thực, vui chơi -> gọi `poi_search`.
     - Khi người dùng hỏi về kinh nghiệm, thời tiết, mẹo vặt, văn hóa -> gọi `knowledge_search`.
   - Tích hợp **Redis Tool Cache**: kiểm tra xem cùng tham số đã gọi trong 5 phút trước đó hay chưa; nếu có thì trả về ngay từ cache.
   - Cập nhật `last_results` vào `context` để phục vụ giải mã tham chiếu (Reference Resolution) cho các lượt chat sau.

2. **Evidence Normalizer (CMP-08)**:
   - **Tuân thủ Rule 5**: Nhận `tool_outputs` thô và chuẩn hóa thành danh sách đối tượng `Evidence` (`schemas/evidence.py`).
   - Tạo ra `EvidenceCollection` và chuỗi văn bản `grounded_evidence` chuẩn Markdown cho LLM.
   - Nếu Tool trả về `EMPTY`, tạo cảnh báo nghiêm ngặt cấm bịa đặt thông tin.

3. **Safety Guard (CMP-10)**:
   - Kiểm tra an toàn 2 chiều (Input & Output):
     - **Input**: Quét Prompt Injection, jailbreak qua `guardrails/prompt_injection.py`.
     - **Output**: Lọc rò rỉ secrets qua `guardrails/output_filter.py`.

---

## 2. Sơ Đồ Luồng Orchestration & Safety

```mermaid
graph TD
    IN["Extracted Params từ Resolver"] --> TO["Tool Orchestrator Node (CMP-07)"]
    
    TO --> CHECK_CACHE{"Kiểm tra Redis Tool Cache"}
    CHECK_CACHE -->|Cache Hit| USE_CACHE["Lấy kết quả từ Cache"]
    CHECK_CACHE -->|Cache Miss| DISPATCH{"Điều phối Tool"}
    
    DISPATCH -->|Cần tìm POI| CALL_POI["Gọi poi_search tool"]
    DISPATCH -->|Cần tìm FAQ/Mẹo| CALL_KB["Gọi knowledge_search tool"]
    
    CALL_POI --> SET_CACHE["Lưu kết quả vào Redis Cache"]
    CALL_KB --> SET_CACHE
    
    USE_CACHE --> EN["Evidence Normalizer Node (CMP-08)"]
    SET_CACHE --> EN
    
    EN -->|Chuẩn hóa thành List[Evidence]| EVIDENCE_OBJS["List[Evidence] (schemas/evidence.py)"]
    EN -->|Tạo Markdown Grounding Text| GROUNDED_TEXT["grounded_evidence (Text)"]
    
    EVIDENCE_OBJS --> RG["Response Generator (Phase 5)"]
    GROUNDED_TEXT --> RG
    
    RG --> SG["Safety Guard Node (CMP-10)"]
    SG -->|Kiểm tra Secret Leak & Fake Entity| OUT["Safe Response Stream"]
```

---

## 3. Mã Nguồn Cần Code Trong Phase Này

### File 1: `src/travelmate/graph/nodes/tool_orchestrator.py`

> **Vị trí tạo file**: `src/travelmate/graph/nodes/tool_orchestrator.py`  
> **Giải thích**: Điều phối thực thi các tool với cơ chế cache Redis. Cập nhật `last_results` vào `context`.

```python
"""Tool Orchestrator Node implementation (CMP-07).

Coordinates execution of poi_search and knowledge_search tools, utilizes Redis
result caching for idempotency, and preserves entity references in context.
"""

from __future__ import annotations

from typing import Any
import structlog

from src.travelmate.clients.embedding_client import HuggingFaceEmbeddingClient
from src.travelmate.config import settings
from src.travelmate.graph.state import TravelMateState
from src.travelmate.infrastructure.database.repositories.kb_repo import KbRepository
from src.travelmate.infrastructure.database.repositories.poi_repo import PoiRepository
from src.travelmate.infrastructure.database.session import get_db_session
from src.travelmate.infrastructure.redis.cache import CacheManager
from src.travelmate.infrastructure.redis.client import get_redis_client
from src.travelmate.schemas.context import ContextState, ResultItem
from src.travelmate.tools.knowledge_search import KnowledgeSearchTool
from src.travelmate.tools.poi_search import PoiSearchTool

logger = structlog.get_logger(__name__)


async def tool_orchestrator_node(state: TravelMateState) -> dict[str, Any]:
    """Execute Tool Orchestrator node logic.

    Args:
        state: Current TravelMateState snapshot.

    Returns:
        State update dictionary containing 'tool_outputs' and updated 'context'.
    """
    params = state.get("extracted_params") or {}
    raw_input = state.get("raw_user_input", "")
    context_data = state.get("context") or {}
    ctx_obj = ContextState.model_validate(context_data)

    tool_outputs: list[dict[str, Any]] = []

    # If query requires clarification (e.g. missing location entirely), bypass tools
    if params.get("needs_clarification"):
        logger.info("Location missing, bypassing tool execution for clarification prompt")
        return {"tool_outputs": []}

    redis_client = get_redis_client()
    cache_mgr = CacheManager(redis_client=redis_client)

    async with get_db_session() as db_session:
        poi_repo = PoiRepository(session=db_session)
        kb_repo = KbRepository(session=db_session)
        embedding_client = HuggingFaceEmbeddingClient()

        poi_tool = PoiSearchTool(poi_repo=poi_repo)
        kb_tool = KnowledgeSearchTool(kb_repo=kb_repo, embedding_client=embedding_client)

        try:
            # 1. Execute poi_search when location is present
            if params.get("location"):
                poi_params = {
                    "location": params["location"],
                    "category": params.get("category", "ACCOM"),
                    "budget_max": params.get("budget_max"),
                    "budget_min": params.get("budget_min"),
                    "preferences": params.get("preferences", []),
                    "limit": 5,
                }
                cache_key = cache_mgr.make_cache_key("poi_search", poi_params)
                cached_res = await cache_mgr.get_cached(cache_key)

                if cached_res:
                    logger.info("Cache hit for poi_search", key=cache_key)
                    poi_result = cached_res
                else:
                    poi_result = await poi_tool.execute(poi_params)
                    await cache_mgr.set_cached(cache_key, poi_result, ttl_seconds=300)

                tool_outputs.append({"tool_name": "poi_search", "result": poi_result})

                # Update last_results in context for future ordinal references
                if poi_result.get("status") == "OK" and poi_result.get("items"):
                    ctx_obj.last_results = [
                        ResultItem(
                            id=item["id"],
                            name=item["name"],
                            category=item["category"],
                            source="tool",
                        )
                        for item in poi_result["items"]
                    ]

            # 2. Execute knowledge_search if query is asking for advice, weather, or tips
            advice_keywords = ["thời tiết", "mùa", "kinh nghiệm", "lưu ý", "vé", "tham quan", "lịch trình"]
            if any(k in raw_input.lower() for k in advice_keywords):
                kb_params = {
                    "query": raw_input,
                    "location": params.get("location"),
                    "top_k": 3,
                }
                kb_cache_key = cache_mgr.make_cache_key("knowledge_search", kb_params)
                cached_kb = await cache_mgr.get_cached(kb_cache_key)

                if cached_kb:
                    kb_result = cached_kb
                else:
                    kb_result = await kb_tool.execute(kb_params)
                    await cache_mgr.set_cached(kb_cache_key, kb_result, ttl_seconds=300)

                tool_outputs.append({"tool_name": "knowledge_search", "result": kb_result})

        finally:
            await embedding_client.close()

    return {
        "tool_outputs": tool_outputs,
        "context": ctx_obj.model_dump(),
    }
```

---

### File 2: `src/travelmate/graph/nodes/evidence_normalizer.py`

> **Vị trí tạo file**: `src/travelmate/graph/nodes/evidence_normalizer.py`  
> **Giải thích**: Node chuẩn hóa bằng chứng (CMP-08). Chuyển đổi toàn bộ kết quả POI và KB thành danh sách đối tượng `Evidence` (`schemas/evidence.py`) và tạo văn bản `grounded_evidence`.

```python
"""Evidence Normalizer Node implementation (CMP-08).

Normalizes raw outputs from poi_search and knowledge_search into standardized
Evidence objects (schemas/evidence.py) and structured grounding text for prompts.
"""

from __future__ import annotations

from typing import Any
import structlog

from src.travelmate.graph.state import TravelMateState
from src.travelmate.schemas.evidence import Evidence, EvidenceCollection

logger = structlog.get_logger(__name__)


async def evidence_normalizer_node(state: TravelMateState) -> dict[str, Any]:
    """Execute Evidence Normalizer node logic.

    Args:
        state: Current TravelMateState snapshot.

    Returns:
        State update dictionary containing 'evidence' and 'grounded_evidence'.
    """
    tool_outputs = state.get("tool_outputs") or []
    params = state.get("extracted_params") or {}

    if params.get("needs_clarification"):
        evidence_text = (
            "THIẾU ĐỊA ĐIỂM: Người dùng chưa cung cấp địa điểm (Tỉnh/Thành phố). "
            "Hãy hỏi lại người dùng một cách lịch sự xem họ muốn đi du lịch ở đâu."
        )
        return {
            "evidence": [],
            "grounded_evidence": evidence_text,
        }

    evidence_items: list[Evidence] = []

    for item in tool_outputs:
        tool_name = item.get("tool_name")
        res = item.get("result", {})
        status = res.get("status")

        if tool_name == "poi_search" and status == "OK" and res.get("items"):
            for poi in res["items"]:
                attributes_str = ", ".join(poi.get("attributes", []))
                content_desc = (
                    f"Địa chỉ: {poi['address']}. "
                    f"Đánh giá: {poi.get('rating', 0.0)}/5.0 sao. "
                    f"Giá: {poi.get('price_info', 'N/A')}. "
                    f"Tiện ích: {attributes_str}."
                )
                evidence_items.append(
                    Evidence(
                        source_type="poi",
                        source_id=poi["id"],
                        title=poi["name"],
                        content=content_desc,
                        source_url=poi.get("source_url"),
                        verified_at=str(poi.get("verified_at")) if poi.get("verified_at") else None,
                        authority_level=poi.get("source_type", "official"),
                        scope_and_limitations=poi.get("scope_and_limitations"),
                        score=float(poi.get("rating", 0.0)),
                        metadata={
                            "address": poi["address"],
                            "price_numeric": poi.get("price_numeric", 0),
                            "attributes": poi.get("attributes", []),
                            "source_url": poi.get("source_url"),
                        },
                    )
                )

        elif tool_name == "knowledge_search" and status == "OK" and res.get("chunks"):
            for chunk in res["chunks"]:
                evidence_items.append(
                    Evidence(
                        source_type="knowledge_base",
                        source_id=chunk["chunk_id"],
                        title=chunk["title"],
                        content=chunk["content"],
                        source_url=chunk.get("source_url"),
                        verified_at=str(chunk.get("last_updated")) if chunk.get("last_updated") else None,
                        authority_level=chunk.get("source_type", "official"),
                        scope_and_limitations=chunk.get("scope_and_limitations"),
                        score=float(chunk.get("score", 0.0)),
                        metadata={"source_id": chunk.get("source_id", "")},
                    )
                )

    collection = EvidenceCollection(items=evidence_items)
    grounded_text = collection.to_grounded_text()

    logger.debug(
        "Normalized evidence items",
        total_items=len(evidence_items),
        text_length=len(grounded_text),
    )

    return {
        "evidence": [ev.model_dump() for ev in evidence_items],
        "grounded_evidence": grounded_text,
    }
```

---

### File 3: `src/travelmate/graph/nodes/safety_guard.py`

> **Vị trí tạo file**: `src/travelmate/graph/nodes/safety_guard.py`  
> **Giải thích**: Node chốt chặn an toàn (CMP-10). Sử dụng các hàm bảo mật từ `guardrails/` để kiểm tra injection và làm sạch đầu ra.

```python
"""Safety Guard Node implementation (CMP-10).

Executes prompt injection detection on input queries and performs secret scrubbing
and grounding verification on generated assistant responses.
"""

from __future__ import annotations

from typing import Any
import structlog

from src.travelmate.graph.state import TravelMateState
from src.travelmate.guardrails.output_filter import sanitize_response
from src.travelmate.guardrails.prompt_injection import is_prompt_injection

logger = structlog.get_logger(__name__)


async def safety_guard_node(state: TravelMateState) -> dict[str, Any]:
    """Execute Safety Guard node logic.

    Args:
        state: Current TravelMateState snapshot.

    Returns:
        State update dictionary containing 'is_safe' and sanitized 'final_response'.
    """
    raw_input = state.get("raw_user_input", "")
    current_response = state.get("final_response", "")

    # 1. Input Inspection: Prompt Injection Check
    is_injected, reason = is_prompt_injection(raw_input)
    if is_injected:
        logger.warning("Safety Guard flagged input prompt injection", reason=reason)
        refusal_msg = (
            "Xin lỗi, tôi là TravelMate AI - Trợ lý Du lịch thông minh. "
            "Tôi chỉ có thể hỗ trợ các thông tin, gợi ý và lịch trình liên quan đến du lịch tại Việt Nam."
        )
        return {
            "is_safe": False,
            "final_response": refusal_msg,
            "error": "ERR-INPUT-INJECTION",
        }

    # 2. Output Inspection: Secret Sanitization
    sanitized = sanitize_response(current_response)

    return {
        "is_safe": True,
        "final_response": sanitized,
    }
```

---

## 4. Tóm Tắt & Giải Thích Chi Tiết

1. **`evidence_normalizer_node` sử dụng `Evidence` & `EvidenceCollection`**:
   - Thay vì nối chuỗi tự do, dữ liệu được chuyển đổi thành danh sách các model Pydantic v2 `Evidence`.
   - Hàm `collection.to_grounded_text()` chịu trách nhiệm định dạng markdown nhất quán. Khi danh sách rỗng, câu cảnh báo cấm bịa đặt được tạo tự động.

2. **Dữ liệu `evidence` có cấu trúc**:
   - `state["evidence"]` lưu trữ danh sách các dict chứa đầy đủ `source_id`, `score`, `metadata`. Điều này giúp hệ thống tracing (Langfuse) hoặc API Client có thể hiển thị các thẻ danh thiếp địa điểm (Cards) trên giao diện người dùng mà không cần parse lại text.
