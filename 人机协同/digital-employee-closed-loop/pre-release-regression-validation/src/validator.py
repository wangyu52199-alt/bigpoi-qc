from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.schemas import BucketResult, RegressionReportOutput, RegressionValidationInput
from shared.utils import render_regression_markdown


BUCKET_NAMES = ["historical_high_frequency", "current_fix_target", "boundary_cases"]


def load_thresholds(path: str | Path) -> dict[str, Any]:
    threshold_path = Path(path)
    data = yaml.safe_load(threshold_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def validate_regression(
    payload: dict[str, Any],
    thresholds: dict[str, Any],
) -> tuple[RegressionReportOutput, str]:
    model = RegressionValidationInput.model_validate(payload)

    bucket_cfg = thresholds.get("bucket_thresholds", {})
    global_cfg = thresholds.get("global", {})
    block_on_high_risk_fail = bool(global_cfg.get("block_on_high_risk_fail", True))

    bucket_results: list[BucketResult] = []
    failed_samples: list[dict[str, Any]] = []
    total_samples = 0
    high_risk_failed = 0

    for bucket_name in BUCKET_NAMES:
        samples = getattr(model, bucket_name)
        total = len(samples)
        failed = [s for s in samples if not s.actual_pass]
        passed = total - len(failed)
        pass_rate = passed / total if total else 1.0

        cfg = bucket_cfg.get(bucket_name, {})
        max_fail = int(cfg.get("max_fail", 0))
        min_pass_rate = float(cfg.get("min_pass_rate", 1.0))
        bucket_pass = len(failed) <= max_fail and pass_rate >= min_pass_rate

        bucket_results.append(
            BucketResult(
                bucket_name=bucket_name,
                total=total,
                passed=passed,
                failed=len(failed),
                pass_rate=pass_rate,
                bucket_pass=bucket_pass,
            )
        )

        for sample in failed:
            failed_samples.append(
                {
                    "sample_id": sample.sample_id,
                    "bucket": bucket_name,
                    "scenario": sample.scenario,
                    "risk_level": sample.risk_level.value,
                }
            )
            if sample.risk_level.value == "high":
                high_risk_failed += 1

        total_samples += total

    overall_pass = all(bucket.bucket_pass for bucket in bucket_results)
    if block_on_high_risk_fail and high_risk_failed > 0:
        overall_pass = False

    risk_summary = (
        f"高风险失败样本数: {high_risk_failed}; 总失败样本数: {len(failed_samples)}"
    )
    release_recommendation = "allow_release" if overall_pass else "hold_release"

    report = RegressionReportOutput(
        overall_pass=overall_pass,
        bucket_results=bucket_results,
        failed_samples=failed_samples,
        risk_summary=risk_summary,
        release_recommendation=release_recommendation,
        metrics_summary={
            "total_samples": total_samples,
            "failed_samples": len(failed_samples),
            "high_risk_failed": high_risk_failed,
        },
    )

    markdown = render_regression_markdown(report.model_dump(mode="json"))
    return report, markdown
