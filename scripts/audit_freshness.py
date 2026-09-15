"""Offline Freshness and Source URL Auditor for TravelMate AI.

Audits source_url availability, detects broken links (HTTP 404/500), reads Last-Modified
headers, and flags stale records (>180 days since verification) across POI and Knowledge Base.
Runs as an offline administrative CLI or scheduled cron job.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


async def check_url(
    client: httpx.AsyncClient,
    item_id: str,
    title: str,
    url: str,
    verified_at_str: str | None,
) -> dict[str, Any]:
    """Audit single URL using HTTP HEAD request.

    Args:
        client: Shared httpx.AsyncClient.
        item_id: POI or KB chunk identifier.
        title: Title or entity name.
        url: Target HTTP/HTTPS URL.
        verified_at_str: Verification date string (YYYY-MM-DD).

    Returns:
        Audit result dictionary.
    """
    days_old = None
    if verified_at_str:
        try:
            v_date = datetime.strptime(verified_at_str, "%Y-%m-%d").date()
            days_old = (datetime.now(UTC).date() - v_date).days
        except ValueError:
            days_old = None

    result: dict[str, Any] = {
        "id": item_id,
        "title": title,
        "url": url,
        "days_since_verified": days_old,
        "is_stale": days_old is not None and days_old > 180,
        "status_code": None,
        "is_alive": False,
        "last_modified_header": None,
        "error": None,
    }

    if not url or not url.startswith("http"):
        result["error"] = "Invalid or empty URL"
        return result

    try:
        resp = await client.head(url, follow_redirects=True, timeout=5.0)
        result["status_code"] = resp.status_code
        result["is_alive"] = resp.status_code < 400
        result["last_modified_header"] = resp.headers.get("last-modified")
    except Exception as exc:
        result["error"] = type(exc).__name__
        result["is_alive"] = False

    return result


async def run_freshness_audit() -> dict[str, Any]:
    """Execute batch audit across POI and Knowledge Base datasets.

    Returns:
        Comprehensive summary report dictionary.
    """
    # 1. Resolve dataset files
    poi_candidates = [
        Path("data/seed/mock_poi_data_v1_3.json"),
        Path("data/seed/mock_poi_data.json"),
    ]
    kb_candidates = [
        Path("data/seed/knowledge_base_v1_3.json"),
        Path("data/seed/knowledge_base.json"),
    ]

    poi_items: list[dict[str, Any]] = []
    for p in poi_candidates:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                poi_items = json.load(f).get("items", [])
            break

    kb_items: list[dict[str, Any]] = []
    for p in kb_candidates:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                kb_items = json.load(f)
            break

    total_targets = len(poi_items) + len(kb_items)
    logger.info("Starting Freshness Audit", poi_count=len(poi_items), kb_count=len(kb_items), total=total_targets)

    headers = {"User-Agent": "TravelMate-AI-FreshnessAuditor/1.0"}
    async with httpx.AsyncClient(headers=headers, verify=False) as client:
        tasks = []
        for p in poi_items:
            tasks.append(
                check_url(
                    client=client,
                    item_id=p.get("id", "UNKNOWN"),
                    title=p.get("name", ""),
                    url=p.get("source_url", ""),
                    verified_at_str=p.get("verified_at"),
                )
            )
        for k in kb_items:
            tasks.append(
                check_url(
                    client=client,
                    item_id=k.get("kb_id", "UNKNOWN"),
                    title=k.get("title", ""),
                    url=k.get("source_url", ""),
                    verified_at_str=k.get("last_updated"),
                )
            )

        results = await asyncio.gather(*tasks)

    # 2. Compile metrics
    alive_count = sum(1 for r in results if r["is_alive"])
    broken_items = [r for r in results if not r["is_alive"]]
    stale_items = [r for r in results if r["is_stale"]]

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_scanned": len(results),
        "active_urls": alive_count,
        "broken_urls_count": len(broken_items),
        "stale_records_count": len(stale_items),
        "broken_items": broken_items[:10],  # Top 10 sample
        "stale_items": stale_items[:10],
    }

    print("\n" + "=" * 60)
    print("           TRAVELMATE AI FRESHNESS AUDIT REPORT")
    print("=" * 60)
    print(f"Total Sources Scanned: {len(results)}")
    print(f"Healthy/Reachable URLs: {alive_count} / {len(results)}")
    print(f"Broken Links Detected: {len(broken_items)}")
    print(f"Stale Records (>180 days): {len(stale_items)}")
    print("=" * 60 + "\n")

    return report


if __name__ == "__main__":
    asyncio.run(run_freshness_audit())
