from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.taxonomy import PriorityLevel


class VerifyAgentImprovementRecord(BaseModel):
    sample_id: str
    issue_summary: str
    observed_symptoms: list[str] = Field(default_factory=list)
    related_dimensions: list[str] = Field(default_factory=list)
    suspected_modules: list[str] = Field(default_factory=list)
    evidence_gap: str
    escalation_signal: bool
    regression_case_candidate: dict[str, Any]
    training_priority: PriorityLevel
    structured_notes: dict[str, Any] = Field(default_factory=dict)


class QCAgentImprovementRecord(BaseModel):
    sample_id: str
    intercept_issue_type: str
    issue_summary: str
    evidence_risk: str
    suspected_modules: list[str] = Field(default_factory=list)
    regression_case_candidate: dict[str, Any]
    training_priority: PriorityLevel
    structured_notes: dict[str, Any] = Field(default_factory=dict)
