from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[0]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location("verify_improver", MODULE_ROOT / "src" / "improver.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
build_verify_improvement_record = module.build_verify_improvement_record


def _load_shared_sample(file_name: str) -> dict:
    root = Path(__file__).resolve().parents[2]
    sample_path = root / "shared" / "examples" / file_name
    return json.loads(sample_path.read_text(encoding="utf-8"))


def test_verify_self_improve_only_consumes_verify_related() -> None:
    manual = _load_shared_sample("sample_01_verify_issue.json")
    first = {
        "sample_id": manual["sample_id"],
        "first_routing_target": "verify_agent",
        "first_routing_reason": "verify",
        "matched_rules": [],
        "confidence": 0.9,
        "structured_signals": {},
    }
    second = {
        "sample_id": manual["sample_id"],
        "primary_module": "entity_extraction",
        "module_candidates": ["entity_extraction", "evidence_selection"],
        "second_routing_reason": "verify",
        "matched_rules": [],
        "structured_signals": {},
    }

    result = build_verify_improvement_record(manual, first, second)
    assert result.training_priority in {"high", "medium", "low"}
    assert result.sample_id == manual["sample_id"]


def test_verify_self_improve_rejects_qc_only() -> None:
    manual = _load_shared_sample("sample_02_qc_issue.json")
    first = {
        "sample_id": manual["sample_id"],
        "first_routing_target": "qc_agent",
        "first_routing_reason": "qc",
        "matched_rules": [],
        "confidence": 0.9,
        "structured_signals": {},
    }
    second = {
        "sample_id": manual["sample_id"],
        "primary_module": "intercept_rule",
        "module_candidates": ["intercept_rule"],
        "second_routing_reason": "qc",
        "matched_rules": [],
        "structured_signals": {},
    }

    with pytest.raises(ValueError):
        build_verify_improvement_record(manual, first, second)
