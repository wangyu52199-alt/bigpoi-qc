from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.taxonomy import IssueObservationTag, JudgmentDimensionTag


class ManualResultInput(BaseModel):
    """人工结果统一输入 schema（严格沿用字段名定义）。"""

    model_config = ConfigDict(extra="allow")

    verify_content_is_correct: int = Field(..., description="核实内容是否正确: 1=是,0=否")
    verify_action_is_correct: int = Field(..., description="核实动作是否正确: 1=是,0=否")
    qc_intercept_is_correct: int = Field(..., description="质检拦截是否正确: 1=是,0=否")
    evidence_status: int = Field(..., description="证据状态: 1=是,0=否,2=矛盾")

    issue_observation_tags: list[IssueObservationTag] = Field(default_factory=list)
    judgment_dimension_tags: list[JudgmentDimensionTag] = Field(default_factory=list)

    manual_comment: str = Field(..., min_length=1)
    conflicting_evidence: Optional[str] = None
    manual_added_evidence_url: Optional[str] = None
    manual_added_evidence_type: Optional[str] = None
    manual_added_evidence_abstract: Optional[str] = None

    verify_result: str = Field(..., description="核实结果: 核实通过/需人工核实")
    evidence_record: Any = Field(..., description="证据列表(jsonb)")
    qc_status: str = Field(..., description="质检结论: qualified/risky/unqualified")
    qc_result: Any = Field(..., description="质检结果详情(jsonb)")

    @field_validator("verify_content_is_correct", "verify_action_is_correct", "qc_intercept_is_correct")
    @classmethod
    def validate_binary(cls, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("value must be 0 or 1")
        return value

    @field_validator("evidence_status")
    @classmethod
    def validate_evidence_status(cls, value: int) -> int:
        if value not in (0, 1, 2):
            raise ValueError("evidence_status must be one of 0, 1, 2")
        return value

    @field_validator("verify_result")
    @classmethod
    def validate_verify_result(cls, value: str) -> str:
        if value not in ("核实通过", "需人工核实"):
            raise ValueError("verify_result must be '核实通过' or '需人工核实'")
        return value

    @field_validator("qc_status")
    @classmethod
    def validate_qc_status(cls, value: str) -> str:
        if value not in ("qualified", "risky", "unqualified"):
            raise ValueError("qc_status must be one of qualified/risky/unqualified")
        return value

    @field_validator("evidence_record", "qc_result")
    @classmethod
    def validate_jsonb(cls, value: Any) -> Any:
        if not isinstance(value, (list, dict)):
            raise ValueError("jsonb field must be list or dict")
        return value
