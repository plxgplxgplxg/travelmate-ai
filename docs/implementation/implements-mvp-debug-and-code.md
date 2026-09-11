# TravelMate AI — Nên nhờ Agent dựng khung ở đâu, tự code ở đâu?

> Mục tiêu: bạn hiểu được **luồng dữ liệu** và **kiến trúc quyết định** của hệ thống, thay vì chỉ có một repo chạy được mà không biết vì sao nó chạy.
> Cập nhật theo kiến trúc chuẩn: [`docs/implementation/travelmate_ai_architecture.md`](./travelmate_ai_architecture.md)

## Nguyên tắc phân loại

Câu hỏi để tự kiểm tra cho từng file: **"Nếu file này sai logic, tôi có tự sửa được không, hay phải hỏi lại agent từ đầu?"**

- Nếu câu trả lời là *"đây là hạ tầng lặp lại, ai viết cũng giống nhau"* → để **Agent** dựng khung, bạn đọc hiểu API/contract là đủ.
- Nếu câu trả lời là *"đây chính là bộ não nghiệp vụ, quyết định app trả lời đúng hay sai"* → bạn **tự code**, agent chỉ đóng vai trò review/gợi ý.

---

## 1. Nên để Agent dựng khung (bạn đọc hiểu, không cần tự gõ)

Đây là phần hạ tầng (infrastructure) và client adapters — có pattern chuẩn, ít quyết định nghiệp vụ, sai thì dễ nhận ra qua test/log.

| Thành phần | File | Vì sao giao cho Agent |
|---|---|---|
| Project skeleton | `pyproject.toml`, `.env.example`, `Makefile`, `Dockerfile`, `docker-compose.yml` | Boilerplate chuẩn, không có logic nghiệp vụ |
| Data layout | `data/seed/mock_poi_data.json`, `data/seed/knowledge_base.json`, `data/evaluation/golden_set.json` | Phân tách dữ liệu khởi tạo và dữ liệu benchmark |
| DB/Redis connection lifecycle | `infrastructure/database/session.py`, `infrastructure/redis/client.py`, `main.py` (lifespan) | Pattern async pool + lifespan là kỹ thuật thuần, lặp lại giữa các dự án FastAPI |
| ORM models | `infrastructure/database/models.py` | Là bản dịch 1-1 từ ERD sang SQLAlchemy — đọc ERD hiểu bảng là đủ |
| Alembic migration | `alembic/env.py`, `alembic/versions/` | Auto-generate từ models, không cần tự viết |
| Pydantic Settings | `config.py` | Chỉ là mapping từ `.env` → object, không có logic |
| External Clients (SDK Abstractions) | `clients/llm_client.py`, `clients/embedding_client.py`, `clients/langfuse_client.py` | Đóng gói toàn bộ SDK bên ngoài (DeepSeek, HuggingFace, Langfuse) sau interface chuẩn |
| Schemas (contracts) | `schemas/context.py`, `schemas/tools.py`, `schemas/evidence.py`, `schemas/trace.py` | Định nghĩa dữ liệu (data shape) và chuẩn hóa Evidence — bạn nên **đọc kỹ** vì đây là "ngôn ngữ chung" |
| Seed & Eval scripts | `scripts/seed_poi.py`, `scripts/seed_kb.py`, `scripts/eval_langfuse.py`, `scripts/audit_freshness.py` | Đọc JSON trong `data/` → insert DB/pgvector, đồng bộ dataset Langfuse, audit link và độ mới |
| Observability | `observability/tracer.py`, `observability/logger.py` | Wrapper SDK Langfuse/structlog, dùng đúng hướng dẫn của thư viện |
| Test scaffold | `tests/conftest.py`, fixtures | Setup lặp lại, agent dựng nhanh và đúng convention |

**Cách làm việc:** nhờ agent dựng từng nhóm nhỏ (ví dụ chỉ Phase 1), sau đó bạn `git diff` đọc qua 5–10 phút để nắm được **API bề mặt** (class nào có method gì) — vì các phần ở Mục 2 sẽ *gọi* vào các API này.

---

## 2. Nên tự code (đây là nơi bạn thực sự học kiến trúc & luồng)

Đây là **AI Agent Layer** — phần quyết định hệ thống "nghĩ" và "quyết định" như thế nào. Nếu để agent viết hết phần này, bạn sẽ có một hệ thống chạy được nhưng bạn không giải thích được tại sao nó trả lời sai khi có bug.

| Thành phần | File | Vì sao PHẢI tự code |
|---|---|---|
| **State schema** | `graph/state.py` | Đây là "bộ nhớ" chảy qua toàn bộ graph — tự định nghĩa để hiểu dữ liệu nào tồn tại ở bước nào |
| **Graph wiring** | `graph/builder.py` | Đây là sơ đồ kiến trúc viết thành code — tự nối các node + conditional edges để hiểu luồng rẽ nhánh UC01/UC02/UC03/OOS |
| **Context Manager (CMP-03)** | `graph/nodes/context_manager.py` | Logic Retain/Overwrite/Reset/RefResolve là **nghiệp vụ cốt lõi** — quyết định hệ thống có "nhớ" đúng ngữ cảnh multi-turn hay không |
| **Router (CMP-04)** | `graph/nodes/router.py` | Bạn tự gọi `LLMClientProtocol` và thiết kế prompt phân loại intent — đây là nơi hay lỗi nhất khi user hỏi mơ hồ |
| **Parameter Resolver (CMP-05)** | `graph/nodes/resolver.py` | Structured extraction (Pydantic) qua `LLMClientProtocol` — tự viết để hiểu vì sao có param bị extract sai/thiếu |
| **Tool Orchestrator (CMP-07)** | `graph/nodes/tool_orchestrator.py` | Quyết định gọi tool nào, khi nào dùng cache — là nơi nối Agent Layer với Tool Abstractions |
| **Evidence Normalizer (CMP-08)** | `graph/nodes/evidence_normalizer.py` | Chuẩn hoá dữ liệu POI/KB thành danh sách `Evidence` (`schemas/evidence.py`) trước khi đưa vào prompt |
| **Response Generator (CMP-09)** | `graph/nodes/response_generator.py` | Ghép danh sách `Evidence` vào prompt + gọi streaming qua `LLMClientProtocol` |
| **Safety Guard (CMP-10)** | `graph/nodes/safety_guard.py` | Input injection defense & output filtering — cần hiểu rõ để biết giới hạn bảo vệ ở đâu |
| **Hybrid Retriever (RAG)** | `rag/retriever.py` | Thuật toán RRF (Reciprocal Rank Fusion) kết hợp vector + FTS qua `EmbeddingClientProtocol` |
| **Tool Protocols & Impls** | `tools/base.py`, `tools/poi_search.py`, `tools/knowledge_search.py` | Lớp mỏng nhưng là điểm nối giữa Agent Layer và Repository — tự viết để hiểu ranh giới DIP |
| **SSE endpoint** | `api/routes_chat.py` | Tự viết để hiểu vòng đời 1 request: load context → chạy graph → stream response → lưu context |
| **System Prompt** | `prompts/system_prompt_v1.md` | Prompt engineering là công việc *bắt buộc tự làm* — không ai hiểu domain travel của bạn tốt hơn chính bạn |

**Gợi ý thứ tự tự code (map với Request Processing Workflow):**
1. `graph/state.py` → hiểu shape dữ liệu trước
2. `graph/nodes/context_manager.py` → nắm state machine đa lượt
3. `graph/nodes/router.py` → `resolver.py` → luồng hiểu intent + tham số qua `LLMClientProtocol`
4. `tools/*.py` → `rag/retriever.py` → cách lấy bằng chứng qua abstractions
5. `graph/nodes/evidence_normalizer.py` → `response_generator.py` → `safety_guard.py`
6. `graph/builder.py` cuối cùng — lúc này bạn đã hiểu từng node, ghép lại sẽ rất tự nhiên
7. `api/routes_chat.py` — nối toàn bộ vào HTTP SSE layer

---

## 3. Vùng xám: Agent dựng khung, nhưng bạn phải review kỹ (không đọc lướt)

| File | Vì sao là "vùng xám" |
|---|---|
| `infrastructure/database/repositories/poi_repo.py`, `kb_repo.py` | Code lặp lại (CRUD/query) nên để agent viết nhanh, nhưng **câu SQL/vector search bên trong quyết định độ chính xác retrieval** → bạn nên đọc từng query |
| `clients/embedding_client.py` (HF key rotation) | Pattern rotation khá chuẩn để agent viết, nhưng bạn nên hiểu cơ chế cooldown 60s vì nó ảnh hưởng latency thực tế |
| `guardrails/prompt_injection.py`, `output_filter.py` | Agent dựng rule/regex ban đầu, nhưng bạn cần tự bổ sung case cụ thể theo domain travel của mình |

---

## 4. Cách làm việc với Agent để không bị "vibe code"

- **Không** đưa cả plan này cho agent và nói "code hết đi" — bạn sẽ nhận một repo bạn không hiểu.
- Chia theo **Phase** đã có sẵn trong tài liệu: mỗi lần chỉ nhờ agent 1 phase hạ tầng/client (Mục 1 ở trên), rồi bạn tự tay viết phần Mục 2 tương ứng.
- Với mỗi node ở Mục 2, có thể nhờ agent **giải thích/review** sau khi bạn viết xong, thay vì nhờ viết hộ — cách này giữ bạn ở vai trò ra quyết định kiến trúc.
- Khi bí, nhờ agent viết **1 node mẫu đơn giản hơn** (ví dụ `safety_guard.py` — ít quyết định nghiệp vụ nhất) để tham khảo pattern, rồi tự áp dụng sang các node phức tạp hơn như `router.py`, `context_manager.py`.
