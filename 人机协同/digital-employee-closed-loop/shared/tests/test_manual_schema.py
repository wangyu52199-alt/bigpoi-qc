from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.schemas import ManualResultInput


def load_example(name: str) -> dict:
    base = Path(__file__).resolve().parents[1] / "examples"
    return json.loads((base / name).read_text(encoding="utf-8"))


def test_manual_schema_validation_success() -> None:
    payload = load_example("sample_01_verify_issue.json")
    model = ManualResultInput.model_validate(payload)
    assert model.verify_action_is_correct == 0
    assert model.verify_result == "需人工核实"


def test_manual_schema_validation_failure() -> None:
    payload = load_example("sample_02_qc_issue.json")
    payload["qc_status"] = "bad_status"
    with pytest.raises(ValidationError):
        ManualResultInput.model_validate(payload)
