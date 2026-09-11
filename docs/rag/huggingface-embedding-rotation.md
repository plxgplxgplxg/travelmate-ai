# Hugging Face Serverless Inference API — Vietnamese Embedding Service

## 1. Giới thiệu & Lựa chọn Model

Trong kiến trúc RAG của TravelMate AI, việc truy xuất thông tin từ cơ sở tri thức (`kb_chunks`) đòi hỏi model vector embedding phải hiểu sâu ngữ nghĩa tiếng Việt, các thực thể du lịch, văn hóa bản địa và phân biệt được ngữ cảnh hỏi đáp.

### 1.1. So sánh các lựa chọn Free Tier trên Hugging Face

| Model | Dimensions | Hỗ trợ tiếng Việt | Sẵn sàng trên Serverless Inference API | Đánh giá |
|---|---|---|---|---|
| `all-MiniLM-L6-v2` | 384 | Kém | Rất cao | Model tiếng Anh, dịch/hiểu tiếng Việt dễ bị lệch ngữ nghĩa |
| `bkai-foundation-models/vietnamese-bi-encoder` | 768 | Tốt (chuyên Việt) | Thấp / Thường xuyên Cold Start | Ít lượt tải trên HF Hub, serverless container không được giữ warm liên tục |
| **`intfloat/multilingual-e5-base`** | **768** | **Xuất sắc (Top MTEB)** | **Rất cao (Featured model)** | **Lựa chọn tối ưu nhất**: Top 1 benchmark đa ngôn ngữ, container luôn warm, miễn phí 100% |

### 1.2. Quy chuẩn Prefix của E5 Model
Dòng model E5 được huấn luyện với cấu trúc tiền tố bất đối xứng (asymmetric retrieval):
- Khi index dữ liệu KB: thêm prefix `passage: ` vào trước nội dung (ví dụ: `passage: Chùa Cầu Hội An nằm ở trung tâm phố cổ...`).
- Khi tìm kiếm: thêm prefix `query: ` vào câu hỏi (ví dụ: `query: Những điểm tham quan lịch sử ở Hội An`).

---

## 2. Thiết kế Cơ Chế Xoay Vòng Dual-Key (Rate Limit Rotation)

### 2.1. Vấn đề
Hugging Face Serverless Inference API (Free Tier) có giới hạn tần suất gọi:
- Giới hạn requests per minute (RPM) trên mỗi IP / User Access Token.
- Khi vượt ngưỡng, API trả về `HTTP 429 Too Many Requests` kèm header `Retry-After`.

### 2.2. Giải pháp: `HFKeyRotator`
- Sử dụng 2 tokens: `HF_API_KEY_1` và `HF_API_KEY_2`.
- Quản lý trạng thái key bằng `asyncio.Lock` và tracking cooldown timestamp (`monotonic`).
- Khi Key 1 gặp lỗi `HTTP 429`:
  1. Đánh dấu Key 1 vào trạng thái cooldown (mặc định 60 giây hoặc theo header `Retry-After`).
  2. Ngay lập tức chuyển sang Key 2 để retry request.
  3. Ghi log cảnh báo mức WARNING (che mờ token để bảo mật).

---

## 3. Mã Nguồn Chi Tiết (`src/travelmate/rag/embeddings.py`)

```python
"""Hugging Face Serverless Inference API embedding client with key rotation.

Provides async text embedding using Hugging Face's free Serverless Inference
API, featuring automatic dual-key rotation on HTTP 429 (rate limit) errors,
E5 prefix formatting, and retry handling.
Serves CMP-07 (Tool Orchestrator) and RAG hybrid retrieval for UC01/UC02.
"""

from __future__ import annotations

import asyncio
import time
from typing import Sequence
import httpx
import structlog

logger = structlog.get_logger(__name__)


class EmbeddingRateLimitError(Exception):
    """Raised when all configured Hugging Face API keys exceed rate limits."""


class EmbeddingServiceError(Exception):
    """Raised when the Hugging Face inference API returns an unrecoverable error."""


class HFKeyRotator:
    """Thread-safe and async-safe API key rotator with cooldown tracking.

    Manages multiple Hugging Face API tokens, tracking rate-limiting state
    and automatically rotating to the next valid key when HTTP 429 occurs.
    """

    def __init__(self, keys: Sequence[str], default_cooldown_seconds: float = 60.0) -> None:
        """Initialize the key rotator.

        Args:
            keys: List of Hugging Face API tokens (e.g., [HF_API_KEY_1, HF_API_KEY_2]).
            default_cooldown_seconds: Default penalty cooldown time in seconds on 429.

        Raises:
            ValueError: If the keys list is empty.
        """
        if not keys:
            raise ValueError("At least one Hugging Face API key must be provided.")
        self._keys = [k.strip() for k in keys if k.strip()]
        if not self._keys:
            raise ValueError("No valid non-empty Hugging Face API keys found.")
        self._cooldown_seconds = default_cooldown_seconds
        self._cooldown_until: dict[str, float] = {k: 0.0 for k in self._keys}
        self._current_index: int = 0
        self._lock = asyncio.Lock()

    async def get_active_key(self) -> str:
        """Get the currently active API key that is not in cooldown.

        Returns:
            The active Hugging Face API token string.

        Raises:
            EmbeddingRateLimitError: If all keys are currently in cooldown.
        """
        async with self._lock:
            now = time.monotonic()
            key = self._keys[self._current_index]
            if self._cooldown_until[key] <= now:
                return key

            for idx, candidate in enumerate(self._keys):
                if self._cooldown_until[candidate] <= now:
                    self._current_index = idx
                    logger.info("Switched to active HF API key", key_index=idx)
                    return candidate

            min_remaining = min(self._cooldown_until[k] - now for k in self._keys)
            raise EmbeddingRateLimitError(
                f"All {len(self._keys)} HF API keys are rate-limited. "
                f"Earliest cooldown reset in {min_remaining:.1f}s."
            )

    async def mark_rate_limited(self, key: str, custom_cooldown: float | None = None) -> str:
        """Mark a key as rate-limited (HTTP 429) and advance to the next key.

        Args:
            key: The key that hit HTTP 429.
            custom_cooldown: Optional cooldown in seconds (e.g., from Retry-After header).

        Returns:
            The next key to try.

        Raises:
            EmbeddingRateLimitError: If all keys have been exhausted.
        """
        async with self._lock:
            cooldown = custom_cooldown or self._cooldown_seconds
            self._cooldown_until[key] = time.monotonic() + cooldown
            logger.warning(
                "HF API key rate-limited, cooling down",
                masked_key=f"{key[:6]}...{key[-4:]}",
                cooldown_seconds=cooldown,
            )

            self._current_index = (self._current_index + 1) % len(self._keys)
            next_key = self._keys[self._current_index]

            now = time.monotonic()
            if self._cooldown_until[next_key] > now:
                for idx, candidate in enumerate(self._keys):
                    if self._cooldown_until[candidate] <= now:
                        self._current_index = idx
                        return candidate

                min_remaining = min(self._cooldown_until[k] - now for k in self._keys)
                raise EmbeddingRateLimitError(
                    f"All {len(self._keys)} HF API keys exhausted after rotation. "
                    f"Cooldown reset in {min_remaining:.1f}s."
                )

            return next_key


class HuggingFaceEmbeddingClient:
    """Async client for Hugging Face Serverless Inference API with key rotation.

    Embeds text chunks and search queries using intfloat/multilingual-e5-base
    (768 dimensions), strictly prefixing queries with 'query: ' and passages
    with 'passage: ' as required by the E5 model family.
    """

    def __init__(
        self,
        api_keys: Sequence[str],
        model_name: str = "intfloat/multilingual-e5-base",
        timeout: float = 30.0,
        cooldown_seconds: float = 60.0,
    ) -> None:
        """Initialize the embedding client.

        Args:
            api_keys: List of 2 or more Hugging Face access tokens.
            model_name: Model identifier on Hugging Face Hub (default: intfloat/multilingual-e5-base).
            timeout: HTTP request timeout in seconds.
            cooldown_seconds: Rate limit cooldown period in seconds.
        """
        self.model_name = model_name
        self.endpoint_url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model_name}"
        self.rotator = HFKeyRotator(api_keys, default_cooldown_seconds=cooldown_seconds)
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self.client.aclose()

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Send embedding request with automatic key rotation on 429 and retry on 503.

        Args:
            texts: List of prepared strings (with prefix).

        Returns:
            List of 768-dimensional float embedding vectors.

        Raises:
            EmbeddingRateLimitError: If all keys are rate-limited.
            EmbeddingServiceError: If API call fails after retries.
        """
        max_attempts = len(self.rotator._keys) * 2
        for attempt in range(max_attempts):
            key = await self.rotator.get_active_key()
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "inputs": texts,
                "options": {"wait_for_model": True},
            }

            try:
                response = await self.client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data and isinstance(data[0], list):
                        return data
                    elif isinstance(data, list) and data and isinstance(data[0], (int, float)):
                        return [data]
                    raise EmbeddingServiceError(f"Unexpected response format from HF API: {type(data)}")

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    cooldown = float(retry_after) if retry_after and retry_after.isdigit() else 60.0
                    await self.rotator.mark_rate_limited(key, custom_cooldown=cooldown)
                    continue

                if response.status_code == 503:
                    logger.info("HF model is loading (cold start), waiting 5 seconds...")
                    await asyncio.sleep(5.0)
                    continue

                raise EmbeddingServiceError(
                    f"HF Inference API returned HTTP {response.status_code}: {response.text}"
                )

            except httpx.RequestError as exc:
                logger.error("HTTP request error to HF API", error=str(exc))
                if attempt == max_attempts - 1:
                    raise EmbeddingServiceError(f"HF API request failed: {exc}") from exc
                await asyncio.sleep(1.0)

        raise EmbeddingRateLimitError("Exceeded maximum retry attempts across all API keys.")

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Embed a list of knowledge base document chunks for vector indexing.

        Automatically prepends the 'passage: ' prefix required by multilingual-e5 models.

        Args:
            documents: List of text content from knowledge base articles.

        Returns:
            List of 768-dimensional embedding vectors.
        """
        if not documents:
            return []
        prefixed = [f"passage: {doc}" for doc in documents]
        return await self._embed_with_retry(prefixed)

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single search query for hybrid vector retrieval.

        Automatically prepends the 'query: ' prefix required by multilingual-e5 models.

        Args:
            query: User search query or synthesized query string.

        Returns:
            768-dimensional embedding vector for cosine similarity search.
        """
        prefixed = [f"query: {query}"]
        vectors = await self._embed_with_retry(prefixed)
        return vectors[0]
```

---

## 4. Hướng dẫn Lấy 2 Token Hugging Face Free

1. Đăng ký/đăng nhập tài khoản tại [huggingface.co](https://huggingface.co).
2. Truy cập **Settings -> Access Tokens** (`https://huggingface.co/settings/tokens`).
3. Nhấn **Create new token**:
   - Token 1: Name: `travelmate_embed_key_1`, Type: `Read`.
   - Token 2: Name: `travelmate_embed_key_2`, Type: `Read`.
4. Copy 2 token này dán vào `.env`:
   ```env
   HF_API_KEY_1=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   HF_API_KEY_2=hf_yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
   ```
