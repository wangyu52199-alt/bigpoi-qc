from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[0]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location("second_routing_router", MODULE_ROOT / "src" / "router.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SecondRoutingEngine = module.SecondRoutingEngine


def _load_shared_sample(file_name: str) -> dict:
    root = Path(__file__).resolve().parents[2]
    sample_path = root / "shared" / "examples" / file_name
    return json.loads(sample_path.read_text(encoding="utf-8"))


def _engine() -> SecondRoutingEngine:
    rule_path = Path(__file__).resolve().parents[1] / "config" / "second_routing_rules.yaml"
    return SecondRoutingEngine(rule_path)


def test_second_routing_qc_intercept_rule() -> None:
    manual = _load_shared_sample("sample_02_qc_issue.json")
    first = {
        "sample_id": manual["sample_id"],
        "first_routing_target": "qc_agent",
        "first_routing_reason": "qc",
        "matched_rules": [],
        "confidence": 0.9,
        "structured_signals": {},
    }
    result = _engine().route(manual, first)
    assert result.primary_module == "intercept_rule"
    assert "qc_intercept_rule" in result.matched_rules


def test_second_routing_verify_module() -> None:
    manual = _load_shared_sample("sample_01_verify_issue.json")
    first = {
        "sample_id": manual["sample_id"],
        "first_routing_target": "verify_agent",
        "first_routing_reason": "verify",
        "matched_rules": [],
        "confidence": 0.9,
        "structured_signals": {},
    }
    result = _engine().route(manual, first)
    assert result.primary_module in {"entity_extraction", "evidence_selection", "evidence_collection"}
