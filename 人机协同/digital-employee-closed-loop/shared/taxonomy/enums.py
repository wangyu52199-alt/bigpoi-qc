from __future__ import annotations

from enum import Enum


class IssueObservationTag(str, Enum):
    evidence_missing = "evidence_missing"
    evidence_invalid = "evidence_invalid"
    evidence_conflicting = "evidence_conflicting"
    invalid_evidence_cited = "invalid_evidence_cited"


class JudgmentDimensionTag(str, Enum):
    name_judgment_problem = "name_judgment_problem"
    address_judgment_problem = "address_judgment_problem"
    type_judgment_problem = "type_judgment_problem"
    location_judgment_problem = "location_judgment_problem"
    admin_judgement_problem = "admin_judgement_problem"
    evidence_usage_problem = "evidence_usage_problem"
    manual_escalation_strategy_problem = "manual_escalation_strategy_problem"
    qc_intercept_rule_problem = "qc_intercept_rule_problem"


class FirstRoutingTarget(str, Enum):
    verify_agent = "verify_agent"
    qc_agent = "qc_agent"
    both = "both"


class VerifyAgentModule(str, Enum):
    task_understanding = "task_understanding"
    entity_extraction = "entity_extraction"
    evidence_collection = "evidence_collection"
    evidence_selection = "evidence_selection"
    reasoning = "reasoning"
    decision = "decision"
    escalation_strategy = "escalation_strategy"
    response_generation = "response_generation"


class QCAgentModule(str, Enum):
    intercept_rule = "intercept_rule"
    false_positive_control = "false_positive_control"
    false_negative_control = "false_negative_control"
    evidence_check = "evidence_check"
    risk_threshold = "risk_threshold"
    qc_explanation_generation = "qc_explanation_generation"


class SecondRoutingModule(str, Enum):
    task_understanding = "task_understanding"
    entity_extraction = "entity_extraction"
    evidence_collection = "evidence_collection"
    evidence_selection = "evidence_selection"
    reasoning = "reasoning"
    decision = "decision"
    escalation_strategy = "escalation_strategy"
    response_generation = "response_generation"
    intercept_rule = "intercept_rule"
    false_positive_control = "false_positive_control"
    false_negative_control = "false_negative_control"
    evidence_check = "evidence_check"
    risk_threshold = "risk_threshold"
    qc_explanation_generation = "qc_explanation_generation"


class PriorityLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


VERIFY_DIMENSION_TAGS = {
    JudgmentDimensionTag.name_judgment_problem.value,
    JudgmentDimensionTag.address_judgment_problem.value,
    JudgmentDimensionTag.type_judgment_problem.value,
    JudgmentDimensionTag.location_judgment_problem.value,
    JudgmentDimensionTag.admin_judgement_problem.value,
    JudgmentDimensionTag.evidence_usage_problem.value,
    JudgmentDimensionTag.manual_escalation_strategy_problem.value,
}

QC_DIMENSION_TAGS = {
    JudgmentDimensionTag.qc_intercept_rule_problem.value,
}
