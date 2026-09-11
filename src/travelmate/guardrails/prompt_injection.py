"""Prompt Injection Defense Module (CMP-10).

Detects adversarial prompts, jailbreak attempts, system instruction overrides,
and role-confusion attacks in English and Vietnamese.
"""

from __future__ import annotations

import re
import structlog

logger = structlog.get_logger(__name__)

# Heuristic patterns for instruction overrides and jailbreaks
INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "OVERRIDE_INSTRUCTIONS",
        re.compile(
            r"(ignore|disregard|forget|skip)\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules|commands)",
            re.IGNORECASE,
        ),
    ),
    (
        "VN_OVERRIDE_INSTRUCTIONS",
        re.compile(
            r"(bỏ\s+qua|quên|hủy)\s+(hết\s+)?(toàn\s+bộ\s+)?(quy\s+tắc|chỉ\s+dẫn|hướng\s+dẫn|lệnh|yêu\s+cầu)\s+(ở\s+trên|trước\s+đó|cũ)",
            re.IGNORECASE,
        ),
    ),
    (
        "SYSTEM_PROMPT_LEAK",
        re.compile(
            r"(print|show|display|reveal|output|repeat)\s+(the\s+)?(system\s+prompt|initial\s+prompt|developer\s+mode|instructions)",
            re.IGNORECASE,
        ),
    ),
    (
        "VN_SYSTEM_PROMPT_LEAK",
        re.compile(
            r"(in\s+ra|cho\s+tôi\s+xem|tiết\s+lộ|hiển\s+thị)\s+(system\s+prompt|hướng\s+dẫn\s+hệ\s+thống|quy\s+tắc\s+gốc|lời\s+nhắc\s+hệ\s+thống)",
            re.IGNORECASE,
        ),
    ),
    (
        "ROLEPLAY_JAILBREAK",
        re.compile(
            r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(DAN|unfiltered|jailbroken|god\s+mode|developer)",
            re.IGNORECASE,
        ),
    ),
    (
        "VN_ROLEPLAY_JAILBREAK",
        re.compile(
            r"(hãy\s+đóng\s+vai|từ\s+bây\s+giờ\s+bạn\s+là|giả\s+vờ\s+là)\s+(chế\s+độ\s+nhà\s+phát\s+triển|bất\s+chấp\s+luật|DAN)",
            re.IGNORECASE,
        ),
    ),
]


def is_prompt_injection(user_input: str) -> tuple[bool, str | None]:
    """Inspect user input against prompt injection and jailbreak patterns.

    Args:
        user_input: Raw query string from user.

    Returns:
        Tuple of (is_flagged: bool, reason_code: str | None).
    """
    if not user_input or not user_input.strip():
        return False, None

    normalized = " ".join(user_input.split())

    for label, pattern in INJECTION_PATTERNS:
        if pattern.search(normalized):
            logger.warning(
                "Detected potential prompt injection",
                rule=label,
                sample=user_input[:80],
            )
            return True, label

    return False, None
