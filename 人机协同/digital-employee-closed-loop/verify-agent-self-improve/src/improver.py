from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.schemas import (
    FirstRoutingResult,
    ManualResultInput,
    SecondRoutingResult,
    VerifyAgentImprovementRecord,
)
from shared.taxonomy import PriorityLevel

VERIFY_MODULES = {
    "task_understanding",
    "entity_extraction",
    "evidence_collection",
    "evidence_selection",
    "reasoning",
    "decision",
    "escalation_strategy",
    "response_generation",
}


def _build_issue_summary(manual: ManualResultInput) -> str:
    dims = [tag.value for tag in manual.judgment_dimension_tags]
    if dims:
        return f"核实问题集中在维度: {', '.join(dims)}"
    return f"核实问题样本：{manual.manual_comment[:50]}"


def _build_evidence_gap(manual: ManualResultInput) -> str:
    if manual.evidence_status == 2:
        return "evidence_conflict"
    if manual.evidence_status == 0:
        return "evidence_missing_or_not_support"
    if any(tag.value == "evidence_missing" for tag in manual.issue_observation_tags):
        return "evidence_missing"
    return "evidence_sufficient"


def _priority(manual: ManualResultInput) -> PriorityLevel:
    if (manual.verify_content_is_correct == 0 and manual.verify_action_is_correct == 0) or manual.evidence_status == 2:
        return PriorityLevel.high
    if manual.verify_content_is_correct == 0 or manual.verify_action_is_correct == 0 or manual.evidence_status == 0:
        return PriorityLevel.medium
    return PriorityLevel.low


def build_verify_improvement_record(
    manual_payload: dict[str, Any],
    first_routing_payload: dict[str, Any],
    second_routing_payload: dict[str, Any],
) -> VerifyAgentImprovementRecord:
    manual = ManualResultInput.model_validate(manual_payload)
    first = FirstRoutingResult.model_validate(first_routing_payload)
    second = SecondRoutingResult.model_validate(second_routing_payload)

    if first.first_routing_target.value not in {"verify_agent", "both"}:
        raise ValueError("verify-agent-self-improve only accepts verify_agent or both samples")

    suspected_modules = [m for m in second.module_candidates if m in VERIFY_MODULES]
    if not suspected_modules and second.primary_module in VERIFY_MODULES:
        suspected_modules = [second.primary_module]

    related_dimensions = [tag.value for tag in manual.judgment_dimension_tags]
    observed_symptoms = [tag.value for tag in manual.issue_observation_tags]
    if manual.evidence_status == 2 and "evidence_conflicting" not in observed_symptoms:
        observed_symptoms.append("evidence_conflicting")

    escalation_signal = (
        "manual_escalation_strategy_problem" in related_dimensions
        or manual.verify_result == "需人工核实"
    )

    record = VerifyAgentImprovementRecord(
        sample_id=first.sample_id,
        issue_summary=_build_issue_summary(manual),
        observed_symptoms=observed_symptoms,
        related_dimensions=related_dimensions,
        suspected_modules=suspected_modules,
        evidence_gap=_build_evidence_gap(manual),
        escalation_signal=escalation_signal,
        regression_case_candidate={
            "sample_id": first.sample_id,
            "verify_result": manual.verify_result,
            "evidence_status": manual.evidence_status,
            "manual_comment": manual.manual_comment,
        },
        training_priority=_priority(manual),
        structured_notes={
            "manual_comment": manual.manual_comment,
            "has_manual_added_evidence": bool(manual.manual_added_evidence_url),
            "first_routing_reason": first.first_routing_reason,
            "second_routing_reason": second.second_routing_reason,
        },
    )
    return record
