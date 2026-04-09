from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[0]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location("first_routing_router", MODULE_ROOT / "src" / "router.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FirstRoutingEngine = module.FirstRoutingEngine


def _load_shared_sample(file_name: str) -> dict:
    root = Path(__file__).resolve().parents[2]
    sample_path = root / "shared" / "examples" / file_name
    return json.loads(sample_path.read_text(encoding="utf-8"))


def _engine() -> FirstRoutingEngine:
    rule_path = Path(__file__).resolve().parents[1] / "config" / "first_routing_rules.yaml"
    return FirstRoutingEngine(rule_path)


def test_first_routing_qc_rule_hit() -> None:
    payload = _load_shared_sample("sample_02_qc_issue.json")
    result = _engine().route(payload)
    assert result.first_routing_target == "qc_agent"
    assert "qc_issue_by_intercept_and_tag" in result.matched_rules


def test_first_routing_verify_rule_hit() -> None:
    payload = _load_shared_sample("sample_01_verify_issue.json")
    result = _engine().route(payload)
    assert result.first_routing_target == "verify_agent"


def test_first_routing_both_hit() -> None:
    payload = _load_shared_sample("sample_03_both_issue.json")
    result = _engine().route(payload)
    assert result.first_routing_target == "both"


def test_first_routing_upstream_sample_falls_back_to_both() -> None:
    payload = _load_shared_sample("sample_06_upstream_data_issue.json")
    result = _engine().route(payload)
    assert result.first_routing_target == "both"


def test_first_routing_policy_sample_falls_back_to_both() -> None:
    payload = _load_shared_sample("sample_07_policy_taxonomy_issue.json")
    result = _engine().route(payload)
    assert result.first_routing_target == "both"
