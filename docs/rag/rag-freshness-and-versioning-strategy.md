# Chiến Lược Quản Lý Phiên Bản & Độ Mới Dữ Liệu (Freshness & Versioning Strategy) Trong RAG

---

## 1. Bối Cảnh & Đặt Vấn Đề

Trong bộ dataset `knowledge_base_v1_3.json` và `mock_poi_data_v1_3.json`, mỗi bản ghi đã được bổ sung các trường siêu dữ liệu (metadata) nguồn chính thống:
- `source_url`: URL trang web chính thức (`official`) hoặc nguồn công khai uy tín (`public_web`).
- `source_type`: Phân loại độ tin cậy của nguồn.
- `last_updated` / `verified_at`: Ngày rà soát kiểm chứng dữ liệu gần nhất (ví dụ: `2026-09-11`).
- `data_version`: Phiên bản của tài liệu (ví dụ: `kb_v1.3_2026-09-11`).
- `scope_and_limitations`: Khuyến cáo về độ biến động (giá phòng, thời tiết, lịch cáp treo) và thời hạn nên re-verify (3–6 tháng).

### Vấn đề cốt lõi của RAG truyền thống:
1. **Tìm kiếm Vector ngữ nghĩa (Cosine Similarity) không có khái niệm về thời gian**:
   - Nếu trong cơ sở dữ liệu có 2 bài viết về *"Giá vé Bà Nà Hills"* (bài năm 2024 giá 750.000đ và bài năm 2026 giá 900.000đ), thuật toán HNSW vector search có thể trả về bài 2024 với điểm tương đồng ngữ nghĩa cao hơn nếu từ khóa trùng khớp sát hơn.
2. **Dữ liệu ngành du lịch có tính biến động cao**:
   - Giá phòng thay đổi theo mùa cao/thấp điểm.
   - Lịch hoạt động của ca-nô, cáp treo phụ thuộc theo bão/mùa mưa.
   - Quán ăn, khách sạn có thể đổi địa chỉ hoặc tạm dừng kinh doanh.

---

## 2. Có Nên Check Live URL Khi User Đang Chat Không?

> [!WARNING]
> **TUYỆT ĐỐI KHÔNG NÊN** gửi request HTTP cào web (live scrape) hoặc check URL thời gian thực trong lúc user đang chờ phản hồi trên luồng SSE `/chat/stream`.

### Lý do kỹ thuật:
| Rủi ro | Tác động tiêu cực |
| :--- | :--- |
| **Độ trễ (Latency)** | Một request HTTP ra ngoài (đặc biệt cào trang du lịch nặng JS/HTML) tốn **500ms – 3000ms**, phá vỡ SLA phản hồi nhanh của hệ thống chat streaming. |
| **SPOF (Điểm lỗi đơn độc)** | Nếu website nguồn (Vinpearl, Vietnam.travel, Muong Thanh) bị nghẽn, sập mạng, hoặc chặn IP bot (Cloudflare 403/429), luồng chat của người dùng sẽ bị timeout hoặc crash. |
| **Chi phí & Rate limit** | Gửi hàng ngàn request đồng thời tới các trang web bên thứ ba sẽ bị liệt vào blacklist bot cào dữ liệu. |

---

## 3. Kiến Trúc Đề Xuất: 3 Trụ Cột Xử Lý Freshness & Versioning

Thay vì live-check khi chat, giải pháp chuẩn công nghiệp là chia làm **3 trụ cột phân tách rõ ràng**:

```
[External Sources (Web URLs)]
            │
            ▼ (Trụ cột 3: Offline / Background Job)
┌──────────────────────────────────────────────┐
│  Automated Freshness Auditor & Ingestion     │
│  - Chạy định kỳ (Cron / Async Worker)        │
│  - Kiểm tra ETag / Last-Modified / Diff      │
│  - Cập nhật data_version, last_updated       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  PostgreSQL 16 + pgvector                    │
│  - Cột: source_url, source_type, last_updated│
│  - Cờ is_active / versioning                 │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Trụ cột 1: Query Time)
┌──────────────────────────────────────────────┐
│  Hybrid Retriever + Recency Re-ranking       │
│  - RRF Score + Time Decay Boost              │
│  - Lọc bỏ bản ghi lỗi thời / inactive        │
└──────────────────────┬───────────────────────┘
                       │
                       ▼ (Trụ cột 2: Grounding & UI)
┌──────────────────────────────────────────────┐
│  Evidence Normalizer & Response Generator    │
│  - Evidence chứa source_url, verified_at     │
│  - LLM trích dẫn link nguồn minh bạch        │
│  - Cảnh báo dữ liệu biến động / hết hạn      │
└──────────────────────────────────────────────┘
```

---

### Trụ Cột 1: Metadata-aware Retrieval & Recency Scoring (Tại Query Time)

Khi thực hiện Hybrid Search (Vector + Full-Text Search), kết hợp điểm số tương đồng ngữ nghĩa với hệ số suy giảm theo thời gian (**Time Decay Function**):

1. **Lọc phiên bản (Version Deduplication / Active Filter)**:
   - Thêm cờ `is_active: bool = True` hoặc gom nhóm theo `source_id` để luôn chọn chunk có `data_version` mới nhất. Không bao giờ để chunk cũ cùng tồn tại song song trong kết quả tìm kiếm.

2. **Công thức tính điểm ưu tiên độ mới (Recency-Weighted Score)**:
   $$\text{Final\_Score} = \text{Score}_{\text{RRF}} \times e^{-\lambda \cdot \Delta t}$$
   Trong đó:
   - $\text{Score}_{\text{RRF}}$: Điểm số dung hợp giữa Dense Vector và Lexical Search.
   - $\Delta t$: Khoảng cách thời gian tính từ `last_updated` đến hiện tại (theo tháng hoặc ngày).
   - $\lambda$: Hệ số suy giảm (ví dụ: thông tin thời tiết/giá cả giảm nhanh hơn thông tin lịch sử văn hóa).

---

### Trụ Cột 2: Grounding Transparency & Staleness Warning (Tại UI / LLM Generation)

Dữ liệu dù được kiểm chứng vẫn có hạn sử dụng. Do đó, hệ thống cần minh bạch hóa nguồn tin thay vì biến LLM thành một hộp đen:

1. **Bổ sung vào Schema `Evidence` (`schemas/evidence.py`)**:
   ```python
   class Evidence(BaseModel):
       source_id: str
       title: str
       content: str
       source_url: str | None = None
       source_type: str = "official" # official | public_web | user_curated
       verified_at: date | None = None
       scope_and_limitations: str | None = None
       score: float = 1.0
   ```

2. **Quy chuẩn văn bản Grounded Evidence đưa vào System Prompt**:
   Khi `Evidence Normalizer` sinh `grounded_evidence`, nó gắn kèm URL và ngày xác thực:
   ```text
   [BẰNG CHỨNG 1] (Loại: official, Ngày kiểm chứng: 2026-09-11)
   - Tiêu đề: Thời tiết Đà Nẵng theo mùa
   - Nguồn: https://www.climatestotravel.com/climate/vietnam/da-nang
   - Nội dung: Mùa mưa từ tháng 9-12... Cáp treo Bà Nà có thể tạm dừng khi gió lớn...
   - Lưu ý: Giá vé/lịch trình có thể biến động; khuyến nghị re-verify trước quyết định.
   ```

3. **Luật Response Generator (Anti-Hallucination & Citation Rule)**:
   - Trong system prompt, chỉ thị cho Claude/LLM:
     - Luôn đính kèm trích dẫn: *"Theo thông tin xác thực từ [Vietnam.travel](url) (cập nhật ngày 11/09/2026)..."*
     - Nếu thông tin có `verified_at` quá 6 tháng hoặc rơi vào hạng mục giá phòng/vé tham quan, tự động thêm câu khuyến cáo: *"Lưu ý: Giá dịch vụ có thể biến động tùy mùa lễ hội, bạn nên tham khảo link chính thức trước khi đặt."*

---

### Trụ Cột 3: Offline Freshness Auditor (Background Job / Cron)

Một script hoặc cron job độc lập (`scripts/audit_freshness.py`) chạy hàng tuần/tháng để bảo trì dữ liệu:

1. **Gửi HTTP `HEAD` Request**:
   - Không tải toàn bộ nội dung HTML nặng.
   - Chỉ đọc header `Last-Modified` hoặc `ETag` của `source_url`.
2. **Phát hiện URL chết (Broken Link Check)**:
   - Đánh dấu các POI hoặc KB có URL trả về `404 Not Found` hoặc `500 Server Error` để nhân sự rà soát lại.
3. **Cảnh báo độ trễ (Staleness Threshold Alert)**:
   - Xuất báo cáo danh sách các địa điểm có `verified_at` đã quá 180 ngày (6 tháng) để cập nhật dữ liệu phiên bản mới.

---

## 4. Bảng So Sánh Các Hướng Tiếp Cận

| Tiêu Chí | Check Live URL Khi Chat | Không Làm Gì (Bỏ Mặc Dữ Liệu Cũ) | Chiến Lược Đề Xuất (Hybrid + Metadata + Offline Audit) |
| :--- | :--- | :--- | :--- |
| **Độ trễ phản hồi (Latency)** | Rất chậm (+1s - 3s) | Rất nhanh (<100ms) | Rất nhanh (<100ms) |
| **Độ tin cậy hệ thống** | Thấp (phụ thuộc web ngoài) | Cao (nội bộ DB) | Cao (nội bộ DB, có link đối chiếu) |
| **Nguy cơ Hallucination** | Trung bình | Rất cao (lỗi thời) | Thấp nhất (Grounding + Citation) |
| **Trải nghiệm người dùng** | Gián đoạn, dễ lỗi | Không biết tin đúng hay sai | Minh bạch, có link nguồn để kiểm chứng |
| **Độ phức tạp triển khai** | Trung bình | Không có | Vừa phải, module hóa rõ ràng |

---

## 5. Lộ Trình Triển Khai Thực Tế Cho TravelMate AI

- **Giai đoạn 1 (Ngay hiện tại - Khuyên dùng)**:
  - Cập nhật Model `KbChunkModel` và `PoiModel` thêm 3 cột: `source_url`, `source_type`, `verified_at` (hoặc `last_updated`).
  - Cập nhật script seed để nạp trực tiếp các trường này từ `data/seed/knowledge_base_v1_3.json` và `data/seed/mock_poi_data_v1_3.json`.
  - Cập nhật `Evidence` schema và Prompt để LLM trích dẫn URL và ngày xác nhận trong câu trả lời.
- **Giai đoạn 2 (Nâng cấp thuật toán RAG)**:
  - Thêm hệ số suy giảm thời gian (Time-decay) vào hàm tính điểm trong `KbRepository.hybrid_search`.
- **Giai đoạn 3 (Mở rộng quy mô)**:
  - Viết background script `scripts/audit_freshness.py` để tự động rà soát link hỏng và báo cáo bài viết hết hạn.
