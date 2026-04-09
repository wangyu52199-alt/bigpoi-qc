from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.taxonomy import PriorityLevel


class RegressionSample(BaseModel):
    sample_id: str
    scenario: str
    expected_pass: bool
    actual_pass: bool
    risk_level: PriorityLevel = PriorityLevel.medium
    detail: dict[str, Any] = Field(default_factory=dict)


class RegressionValidationInput(BaseModel):
    historical_high_frequency: list[RegressionSample] = Field(default_factory=list)
    current_fix_target: list[RegressionSample] = Field(default_factory=list)
    boundary_cases: list[RegressionSample] = Field(default_factory=list)


class BucketResult(BaseModel):
    bucket_name: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    bucket_pass: bool


class RegressionReportOutput(BaseModel):
    overall_pass: bool
    bucket_results: list[BucketResult]
    failed_samples: list[dict[str, Any]]
    risk_summary: str
    release_recommendation: str
    metrics_summary: dict[str, Any]
