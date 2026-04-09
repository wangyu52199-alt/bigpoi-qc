from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from shared.taxonomy import FirstRoutingTarget


class FirstRoutingResult(BaseModel):
    sample_id: str
    first_routing_target: FirstRoutingTarget
    first_routing_reason: str
    matched_rules: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    structured_signals: dict[str, Any] = Field(default_factory=dict)


class SecondRoutingResult(BaseModel):
    sample_id: str
    primary_module: str
    module_candidates: list[str] = Field(default_factory=list)
    second_routing_reason: str
    matched_rules: list[str] = Field(default_factory=list)
    structured_signals: dict[str, Any] = Field(default_factory=dict)
