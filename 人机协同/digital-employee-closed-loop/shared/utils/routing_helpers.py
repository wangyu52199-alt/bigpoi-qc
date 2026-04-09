from __future__ import annotations

from typing import Any


def extract_sample_id(payload: dict[str, Any], default_prefix: str = "sample") -> str:
    for key in ("sample_id", "id", "case_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"{default_prefix}-unknown"


def text_contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def list_contains_any(values: list[str], targets: list[str]) -> bool:
    value_set = set(values)
    return any(target in value_set for target in targets)


def summarize_manual_signals(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "verify_wrong": payload.get("verify_content_is_correct") == 0
        or payload.get("verify_action_is_correct") == 0,
        "qc_wrong": payload.get("qc_intercept_is_correct") == 0,
        "evidence_status": payload.get("evidence_status"),
        "issue_observation_tags": payload.get("issue_observation_tags", []),
        "judgment_dimension_tags": payload.get("judgment_dimension_tags", []),
    }
