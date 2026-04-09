from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IterationOperation(BaseModel):
    operation: str
    file_path: str
    detail: dict[str, Any] = Field(default_factory=dict)
    status: str = "planned"


class IterationExecutionResult(BaseModel):
    sample_id: str
    target_skill_path: str
    primary_module: str
    applied: bool
    operations: list[IterationOperation] = Field(default_factory=list)
    touched_files: list[str] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
