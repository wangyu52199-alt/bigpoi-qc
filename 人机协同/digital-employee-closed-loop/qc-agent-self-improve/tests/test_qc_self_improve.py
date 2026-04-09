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

spec = importlib.util.spec_from_file_location("qc_improver", MODULE_ROOT / "src" / "improver.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
build_qc_improvement_record = module.build_qc_improvement_record


def _load_shared_sample(file_name: str) -> dict:
    root = Path(__file__).resolve().parents[2]
    sample_path = root / "shared" / "examples" / file_name
    return json.loads(sample_path.read_text(encoding="utf-8"))


def test_qc_self_improve_only_consumes_qc_related() -> None:
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
        "module_candidates": ["intercept_rule", "false_positive_control"],
        "second_routing_reason": "qc",
        "matched_rules": [],
        "structured_signals": {},
    }

    result = build_qc_improvement_record(manual, first, second)
    assert result.sample_id == manual["sample_id"]
    assert result.intercept_issue_type in {
        "false_positive",
        "false_negative",
        "rule_instability",
        "evidence_insufficient",
        "qc_explanation_insufficient",
    }


def test_qc_self_improve_rejects_verify_only() -> None:
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
        "module_candidates": ["entity_extraction"],
        "second_routing_reason": "verify",
        "matched_rules": [],
        "structured_signals": {},
    }

    with pytest.raises(ValueError):
        build_qc_improvement_record(manual, first, second)
