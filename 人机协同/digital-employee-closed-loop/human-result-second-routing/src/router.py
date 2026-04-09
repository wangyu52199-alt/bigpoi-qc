from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.schemas import FirstRoutingResult, ManualResultInput, SecondRoutingResult
from shared.utils import load_rule_config


def _evaluate_condition(condition: dict[str, Any], payload: dict[str, Any]) -> bool:
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


class SecondRoutingEngine:
    def __init__(self, rules_path: str | Path) -> None:
        self.rules = load_rule_config(rules_path)

    def _scope_allowed(self, scope: str, first_target: str) -> bool:
        if first_target == "verify_agent":
            return scope in {"verify", "both"}
        if first_target == "qc_agent":
            return scope in {"qc", "both"}
        if first_target == "both":
            return scope in {"verify", "qc", "both"}
        return False

    def route(self, manual_payload: dict[str, Any], first_routing_payload: dict[str, Any]) -> SecondRoutingResult:
        manual = ManualResultInput.model_validate(manual_payload)
        first = FirstRoutingResult.model_validate(first_routing_payload)

        manual_data = manual.model_dump(mode="json")
        first_target = first.first_routing_target.value
        sample_id = first.sample_id

        module_scores: dict[str, int] = {}
        matched_rules: list[str] = []
        reason_map: dict[str, list[str]] = {}

        for rule in self.rules:
            scope = str(rule.get("scope", "both"))
            if not self._scope_allowed(scope, first_target):
                continue
            if _evaluate_condition(rule.get("conditions", {}), manual_data):
                module = str(rule["target"])
                priority = int(rule.get("priority", 0))
                module_scores[module] = module_scores.get(module, 0) + priority
                matched_rules.append(str(rule["id"]))
                reason_map.setdefault(module, []).append(str(rule.get("reason", "")))

        if not module_scores:
            default_module = "decision" if first_target in {"verify_agent", "both"} else "intercept_rule"
            return SecondRoutingResult(
                sample_id=sample_id,
                primary_module=default_module,
                module_candidates=[default_module],
                second_routing_reason="未命中模块规则，使用默认模块。",
                matched_rules=matched_rules,
                structured_signals={"module_scores": module_scores, "first_routing_target": first_target},
            )

        ordered = sorted(module_scores.items(), key=lambda item: item[1], reverse=True)
        primary_module = ordered[0][0]
        module_candidates = [name for name, _ in ordered]

        reason_text = "；".join(reason_map.get(primary_module, [])) or "命中模块规则。"

        return SecondRoutingResult(
            sample_id=sample_id,
            primary_module=primary_module,
            module_candidates=module_candidates,
            second_routing_reason=reason_text,
            matched_rules=matched_rules,
            structured_signals={
                "module_scores": module_scores,
                "first_routing_target": first_target,
                "reason_map": reason_map,
            },
        )
