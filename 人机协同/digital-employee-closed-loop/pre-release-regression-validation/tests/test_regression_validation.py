from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[0]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

spec = importlib.util.spec_from_file_location("regression_validator", MODULE_ROOT / "src" / "validator.py")
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
load_thresholds = module.load_thresholds
validate_regression = module.validate_regression


def test_regression_report_json_generation() -> None:
    base = Path(__file__).resolve().parents[1]
    payload = json.loads((base / "examples" / "regression_input.json").read_text(encoding="utf-8"))
    thresholds = load_thresholds(base / "config" / "regression_thresholds.yaml")

    report, _ = validate_regression(payload, thresholds)
    data = report.model_dump(mode="json")

    assert "overall_pass" in data
    assert "bucket_results" in data
    assert isinstance(data["failed_samples"], list)


def test_regression_report_markdown_generation() -> None:
    base = Path(__file__).resolve().parents[1]
    payload = json.loads((base / "examples" / "regression_input.json").read_text(encoding="utf-8"))
    thresholds = load_thresholds(base / "config" / "regression_thresholds.yaml")

    _, markdown = validate_regression(payload, thresholds)
    assert "# Regression Validation Report" in markdown
    assert "## Bucket Results" in markdown
