"""Hugging Face embedding service adapter.

Re-exports embedding client implementations and protocols from clients.embedding_client
to maintain clean separation and backwards compatibility.
"""

from src.travelmate.clients.embedding_client import (
    EmbeddingClientProtocol,
    EmbeddingRateLimitError,
    EmbeddingServiceError,
    HFKeyRotator,
    HuggingFaceEmbeddingClient,
)

__all__ = [
    "EmbeddingClientProtocol",
    "EmbeddingRateLimitError",
    "EmbeddingServiceError",
    "HFKeyRotator",
    "HuggingFaceEmbeddingClient",
]
