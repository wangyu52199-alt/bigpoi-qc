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
    QCAgentImprovementRecord,
    SecondRoutingResult,
)
from shared.taxonomy import PriorityLevel

QC_MODULES = {
    "intercept_rule",
    "false_positive_control",
    "false_negative_control",
    "evidence_check",
    "risk_threshold",
    "qc_explanation_generation",
}


def _intercept_issue_type(manual: ManualResultInput) -> str:
    comment = manual.manual_comment
    tags = {tag.value for tag in manual.judgment_dimension_tags}
    issue_tags = {tag.value for tag in manual.issue_observation_tags}

    if manual.qc_intercept_is_correct == 0 and ("误拦截" in comment or manual.qc_status == "unqualified"):
        return "false_positive"
    if manual.qc_intercept_is_correct == 0 and ("漏拦截" in comment or manual.qc_status == "qualified"):
        return "false_negative"
    if "qc_intercept_rule_problem" in tags:
        return "rule_instability"
    if issue_tags & {"evidence_missing", "evidence_invalid", "evidence_conflicting", "invalid_evidence_cited"}:
        return "evidence_insufficient"
    return "qc_explanation_insufficient"


def _priority(manual: ManualResultInput) -> PriorityLevel:
    if (manual.qc_intercept_is_correct == 0 and manual.evidence_status == 2) or (
        manual.qc_intercept_is_correct == 0 and manual.qc_status == "risky"
    ):
        return PriorityLevel.high
    if manual.qc_intercept_is_correct == 0 or manual.evidence_status == 0:
        return PriorityLevel.medium
    return PriorityLevel.low


def _evidence_risk(manual: ManualResultInput) -> str:
    if manual.evidence_status == 2:
        return "contradictory"
    if manual.evidence_status == 0:
        return "not_supported"
    return "supported"


def build_qc_improvement_record(
    manual_payload: dict[str, Any],
    first_routing_payload: dict[str, Any],
    second_routing_payload: dict[str, Any],
) -> QCAgentImprovementRecord:
    manual = ManualResultInput.model_validate(manual_payload)
    first = FirstRoutingResult.model_validate(first_routing_payload)
    second = SecondRoutingResult.model_validate(second_routing_payload)

    if first.first_routing_target.value not in {"qc_agent", "both"}:
        raise ValueError("qc-agent-self-improve only accepts qc_agent or both samples")

    suspected_modules = [m for m in second.module_candidates if m in QC_MODULES]
    if not suspected_modules and second.primary_module in QC_MODULES:
        suspected_modules = [second.primary_module]

    issue_type = _intercept_issue_type(manual)
    issue_summary = f"质检问题类型: {issue_type}；人工说明: {manual.manual_comment[:60]}"

    record = QCAgentImprovementRecord(
        sample_id=first.sample_id,
        intercept_issue_type=issue_type,
        issue_summary=issue_summary,
        evidence_risk=_evidence_risk(manual),
        suspected_modules=suspected_modules,
        regression_case_candidate={
            "sample_id": first.sample_id,
            "qc_status": manual.qc_status,
            "qc_intercept_is_correct": manual.qc_intercept_is_correct,
            "manual_comment": manual.manual_comment,
        },
        training_priority=_priority(manual),
        structured_notes={
            "first_routing_reason": first.first_routing_reason,
            "second_routing_reason": second.second_routing_reason,
            "issue_observation_tags": [tag.value for tag in manual.issue_observation_tags],
            "judgment_dimension_tags": [tag.value for tag in manual.judgment_dimension_tags],
        },
    )
    return record
