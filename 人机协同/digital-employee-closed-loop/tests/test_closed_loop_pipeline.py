from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "closed_loop_pipeline",
    REPO_ROOT / "scripts" / "run_closed_loop_pipeline.py",
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
run_pipeline = module.run_pipeline

VERIFY_MODULES = {
    "task_understanding",
    "entity_extraction",
    "evidence_collection",
    "evidence_selection",
    "reasoning",
    "decision",
    "escalation_strategy",
    "response_generation",
}

QC_MODULES = {
    "intercept_rule",
    "false_positive_control",
    "false_negative_control",
    "evidence_check",
    "risk_threshold",
    "qc_explanation_generation",
}


def _load_manual_sample() -> dict:
    path = REPO_ROOT / "shared" / "examples" / "sample_03_both_issue.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_closed_loop_pipeline_both_targets_apply(tmp_path: Path) -> None:
    manual_payload = _load_manual_sample()

    targets_cfg = {
        "verify_target": {
            "skill_path": str(tmp_path / "verify_skill"),
            "config_path": str(REPO_ROOT / "verify-agent-self-improve" / "config" / "auto_iteration_config.yaml"),
        },
        "qc_target": {
            "skill_path": str(tmp_path / "qc_skill"),
            "config_path": str(REPO_ROOT / "qc-agent-self-improve" / "config" / "auto_iteration_config.yaml"),
        },
    }

    summary = run_pipeline(
        manual_payload=manual_payload,
        targets_cfg=targets_cfg,
        repo_root=REPO_ROOT,
        dry_run=False,
    )

    assert summary["first_routing_result"]["first_routing_target"] == "both"
    assert summary["resolved_targets"] == ["verify_agent", "qc_agent"]

    verify_result = summary["per_target"]["verify_agent"]["iteration_result"]
    qc_result = summary["per_target"]["qc_agent"]["iteration_result"]

    assert verify_result["primary_module"] in VERIFY_MODULES
    assert qc_result["primary_module"] in QC_MODULES

    assert (tmp_path / "verify_skill" / "config" / "verify_rules.yaml").exists()
    assert (tmp_path / "qc_skill" / "config" / "qc_rules.yaml").exists()
