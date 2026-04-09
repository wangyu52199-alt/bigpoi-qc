from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "batch_closed_loop",
    REPO_ROOT / "scripts" / "run_batch_closed_loop_with_regression.py",
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
run_batch_pipeline = module.run_batch_pipeline
load_jsonl = module._load_jsonl


def test_batch_closed_loop_with_regression_dry_run(tmp_path: Path) -> None:
    manual_samples = load_jsonl(REPO_ROOT / "integrations" / "examples" / "manual_batch_samples.jsonl")

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

    historical = [
        {
            "sample_id": "H-TEST-001",
            "scenario": "历史测试",
            "expected_pass": True,
            "actual_pass": True,
            "risk_level": "low",
            "detail": {"note": "ok"},
        }
    ]
    boundary = [
        {
            "sample_id": "B-TEST-001",
            "scenario": "边界测试",
            "expected_pass": True,
            "actual_pass": True,
            "risk_level": "medium",
            "detail": {"note": "ok"},
        }
    ]

    output_dir = tmp_path / "batch_output"
    summary = run_batch_pipeline(
        manual_samples=manual_samples,
        targets_cfg=targets_cfg,
        repo_root=REPO_ROOT,
        output_dir=output_dir,
        thresholds_path=REPO_ROOT / "pre-release-regression-validation" / "config" / "regression_thresholds.yaml",
        historical_samples=historical,
        boundary_samples=boundary,
        dry_run=True,
    )

    assert summary["dry_run"] is True
    assert summary["total_samples"] == 3
    assert summary["failed_samples"] == 0
    assert summary["regression_report"]["overall_pass"] is True

    report_path = output_dir / "regression_report.json"
    md_path = output_dir / "regression_report.md"
    assert report_path.exists()
    assert md_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["release_recommendation"] in {"allow_release", "hold_release"}
    assert len(list((output_dir / "samples").glob("*.json"))) == 3
