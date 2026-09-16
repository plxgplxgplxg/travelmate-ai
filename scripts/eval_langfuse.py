"""Langfuse Dataset Evaluation and Golden Set regression runner (CMP-12).

Uploads or synchronizes data/evaluation/golden_set.json (26 regression cases) to a
Langfuse Dataset and executes benchmark evaluations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from src.travelmate.clients.langfuse_client import get_tracer_client
from src.travelmate.config import settings

logger = structlog.get_logger(__name__)


def sync_golden_dataset(json_file: Path | str | None = None) -> int:
    """Sync golden dataset test cases into Langfuse dataset.

    Args:
        json_file: Optional explicit path to golden set JSON file.

    Returns:
        Number of synced test items.
    """
    candidate_paths = (
        [Path(json_file)]
        if json_file
        else [
            Path("data/evaluation/golden_set_v1_2_220cases.json"),
            Path("data/evaluation/golden_set.json"),
            Path("golden_set_v1_2_220cases.json"),
            Path("golden_set.json"),
        ]
    )

    resolved_path: Path | None = None
    for p in candidate_paths:
        if p.exists():
            resolved_path = p
            break

    if not resolved_path:
        raise FileNotFoundError(
            f"Golden dataset file not found among candidates: {candidate_paths}"
        )

    path = resolved_path

    with open(path, encoding="utf-8") as f:
        cases: list[dict[str, Any]] = json.load(f)

    logger.info("Loaded golden set cases", file=str(path), total_cases=len(cases))

    tracer_client = get_tracer_client()
    sdk = getattr(tracer_client, "_langfuse", None)

    if sdk is None:
        logger.warning("Langfuse credentials not set. Running in local simulation mode.")
        return len(cases)

    dataset_name = f"travelmate-golden-set-{settings.bot_version.lower()}"

    try:
        dataset = sdk.get_dataset(dataset_name)
    except Exception:
        logger.info("Creating new Langfuse dataset", dataset_name=dataset_name)
        dataset = sdk.create_dataset(
            name=dataset_name,
            description="Golden regression test cases for TravelMate AI",
            metadata={"bot_version": settings.bot_version},
        )

    for item in cases:
        try:
            dataset.create_item(
                input={"query": item["query"]},
                expected_output={
                    "route": item.get("expected_route"),
                    "tool": item.get("expected_tool"),
                    "params": item.get("expected_params"),
                },
                metadata={
                    "case_id": item["case_id"],
                    "requirement_id": item.get("requirement_id"),
                    "priority": item.get("priority"),
                },
            )
        except Exception as exc:
            logger.debug(
                "Item may already exist in dataset", case_id=item["case_id"], error=str(exc)
            )

    tracer_client.flush()
    logger.info(
        "Successfully synced dataset to Langfuse", dataset_name=dataset_name, count=len(cases)
    )
    return len(cases)


if __name__ == "__main__":
    sync_golden_dataset()
