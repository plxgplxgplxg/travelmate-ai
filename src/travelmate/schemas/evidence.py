"""Common Evidence Schema (CMP-08).

Defines the unified contract for grounded factual evidence normalized from
heterogeneous sources (POI database and Knowledge Base RAG).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Normalized evidence item used for grounding LLM generation.

    Attributes:
        source_type: Origin data provider ('poi' or 'knowledge_base').
        source_id: Identifier of the source record or chunk (e.g. 'POI_101', 'KB_DN_001').
        title: Entity name or article title.
        content: Grounding text representation (facts, address, price, tips).
        source_url: Official or public authoritative website URL.
        verified_at: Verification date string (YYYY-MM-DD).
        authority_level: Source trust rating ('official' | 'public_web').
        scope_and_limitations: Seasonal volatility note or re-verification recommendation.
        score: Optional relevance or similarity score.
        metadata: Additional attributes preserved from source.
    """

    source_type: Literal["poi", "knowledge_base"] = Field(
        description="Source provider identifier",
    )
    source_id: str = Field(description="Unique source entity or chunk ID")
    title: str = Field(description="Entity name or article headline")
    content: str = Field(description="Normalized factual content")
    source_url: str | None = Field(default=None, description="Official source URL")
    verified_at: str | None = Field(default=None, description="Date of verification (YYYY-MM-DD)")
    authority_level: str = Field(
        default="official", description="Origin classification ('official' | 'public_web')"
    )
    scope_and_limitations: str | None = Field(
        default=None, description="Seasonal volatility or re-verification note"
    )
    score: float | None = Field(default=None, description="Retrieval or relevance score")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary source metadata (rating, price, location, etc.)",
    )


class EvidenceCollection(BaseModel):
    """Container collection of normalized evidence items."""

    items: list[Evidence] = Field(
        default_factory=list,
        description="List of normalized evidence records",
    )

    @property
    def is_empty(self) -> bool:
        """Check if collection contains no evidence items."""
        return len(self.items) == 0

    def to_grounded_text(self) -> str:
        """Format collection into structured markdown with explicit citations for LLM.

        Returns:
            Structured markdown string presenting all evidence facts with URLs and dates.
        """
        if not self.items:
            return (
                "### KẾT QUẢ: RỖNG (EMPTY)\n"
                "Không tìm thấy dữ liệu phù hợp trong cơ sở dữ liệu. Bắt buộc thông báo "
                "trung thực và đề xuất nới lỏng tiêu chí hoặc ngân sách. "
                "TUYỆT ĐỐI KHÔNG BỊA ĐẶT."
            )

        poi_lines: list[str] = []
        kb_lines: list[str] = []

        for idx, ev in enumerate(self.items, start=1):
            cite_parts = []
            if ev.source_url:
                cite_parts.append(f"Link nguồn: {ev.source_url}")
            if ev.verified_at:
                cite_parts.append(f"Xác minh: {ev.verified_at}")
            if ev.authority_level:
                cite_parts.append(f"Cấp độ: {ev.authority_level}")

            cite_str = f" ({', '.join(cite_parts)})" if cite_parts else ""
            notes = (
                f"\n   Lưu ý/Hạn chế: {ev.scope_and_limitations}"
                if ev.scope_and_limitations
                else ""
            )

            if ev.source_type == "poi":
                poi_lines.append(
                    f"{idx}. [{ev.source_id}] {ev.title}{cite_str}:\n   {ev.content}{notes}"
                )
            else:
                kb_lines.append(f"- [{ev.source_id}] {ev.title}{cite_str}:\n  {ev.content}{notes}")

        sections: list[str] = []
        if poi_lines:
            sections.append("### BẰNG CHỨNG ĐỊA ĐIỂM (POI DATABASE):\n" + "\n".join(poi_lines))
        if kb_lines:
            sections.append("### BẰNG CHỨNG CẨM NANG (KNOWLEDGE BASE):\n" + "\n".join(kb_lines))

        return "\n\n".join(sections)
