"""External service client adapters package."""

from src.travelmate.clients.base import (
    EmbeddingClientError,
    EmbeddingClientProtocol,
    EmbeddingRateLimitError,
    EmbeddingServiceError,
    LLMClientError,
    LLMClientProtocol,
)
from src.travelmate.clients.hf_embedding_client import HuggingFaceEmbeddingClient
from src.travelmate.clients.hf_rotator import HFKeyRotator
from src.travelmate.clients.llm_client import OpenAILLMClient

__all__ = [
    "EmbeddingClientError",
    "EmbeddingClientProtocol",
    "EmbeddingRateLimitError",
    "EmbeddingServiceError",
    "HFKeyRotator",
    "HuggingFaceEmbeddingClient",
    "LLMClientError",
    "LLMClientProtocol",
    "OpenAILLMClient",
]
