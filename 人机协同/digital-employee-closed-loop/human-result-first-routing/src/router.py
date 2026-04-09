from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.schemas import FirstRoutingResult, ManualResultInput
from shared.taxonomy import FirstRoutingTarget
from shared.utils import load_rule_config, summarize_manual_signals


def _evaluate_condition(condition: dict[str, Any], payload: dict[str, Any]) -> bool:
    if "always_true" in condition:
        return bool(condition["always_true"])

    if "field_equals" in condition:
        cfg = condition["field_equals"]
        return payload.get(cfg["field"]) == cfg["value"]

    if "tags_include_any" in condition:
        cfg = condition["tags_include_any"]
        values = payload.get(cfg["field"], []) or []
        return any(tag in values for tag in cfg["values"])

    if "text_contains_any" in condition:
        cfg = condition["text_contains_any"]
        text = str(payload.get(cfg["field"], "")).lower()
        return any(keyword.lower() in text for keyword in cfg["keywords"])

    if "all" in condition:
        return all(_evaluate_condition(sub, payload) for sub in condition["all"])

    if "any" in condition:
        return any(_evaluate_condition(sub, payload) for sub in condition["any"])

    if "not" in condition:
        return not _evaluate_condition(condition["not"], payload)

    return False


class FirstRoutingEngine:
    def __init__(self, rules_path: str | Path) -> None:
        self.rules = load_rule_config(rules_path)

    def route(self, payload: dict[str, Any]) -> FirstRoutingResult:
        model = ManualResultInput.model_validate(payload)
        data = model.model_dump(mode="json")
        sample_id = payload.get("sample_id") or payload.get("case_id") or "sample-unknown"

        matched: list[dict[str, Any]] = []
        for rule in self.rules:
            if _evaluate_condition(rule.get("conditions", {}), data):
                matched.append(rule)

        matched_rule_ids = [rule["id"] for rule in matched]
        matched_targets = [rule["target"] for rule in matched]

        has_verify = "verify_agent" in matched_targets
        has_qc = "qc_agent" in matched_targets
        if has_verify and has_qc:
            selected_target = "both"
            selected_reason = "同时命中核实与质检分流规则。"
            confidence = 0.92
        elif has_verify:
            selected_target = "verify_agent"
            selected_reason = next(
                rule["reason"] for rule in matched if rule["target"] == "verify_agent"
            )
            confidence = float(
                next(rule.get("confidence", 0.8) for rule in matched if rule["target"] == "verify_agent")
            )
        elif has_qc:
            selected_target = "qc_agent"
            selected_reason = next(
                rule["reason"] for rule in matched if rule["target"] == "qc_agent"
            )
            confidence = float(
                next(rule.get("confidence", 0.8) for rule in matched if rule["target"] == "qc_agent")
            )
        else:
            selected_target = "both"
            selected_reason = "未命中单边规则，按默认双路由处理。"
            confidence = 0.6

        return FirstRoutingResult(
            sample_id=str(sample_id),
            first_routing_target=FirstRoutingTarget(selected_target),
            first_routing_reason=selected_reason,
            matched_rules=matched_rule_ids,
            confidence=max(0.0, min(confidence, 1.0)),
            structured_signals={
                "targets_hit": matched_targets,
                "manual_signals": summarize_manual_signals(data),
            },
        )
