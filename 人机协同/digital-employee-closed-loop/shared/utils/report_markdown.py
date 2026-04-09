from __future__ import annotations

from typing import Any


def render_regression_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Regression Validation Report")
    lines.append("")
    lines.append(f"- overall_pass: {report.get('overall_pass')}")
    lines.append(f"- release_recommendation: {report.get('release_recommendation')}")
    lines.append(f"- risk_summary: {report.get('risk_summary')}")
    lines.append("")
    lines.append("## Bucket Results")
    lines.append("")
    lines.append("| bucket | total | passed | failed | pass_rate | bucket_pass |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for item in report.get("bucket_results", []):
        lines.append(
            "| {bucket_name} | {total} | {passed} | {failed} | {pass_rate:.2%} | {bucket_pass} |".format(
                bucket_name=item.get("bucket_name", ""),
                total=item.get("total", 0),
                passed=item.get("passed", 0),
                failed=item.get("failed", 0),
                pass_rate=float(item.get("pass_rate", 0.0)),
                bucket_pass=item.get("bucket_pass", False),
            )
        )

    failed_samples = report.get("failed_samples", [])
    lines.append("")
    lines.append("## Failed Samples")
    lines.append("")
    if not failed_samples:
        lines.append("- 无")
    else:
        for sample in failed_samples:
            lines.append(
                f"- {sample.get('sample_id', '')} ({sample.get('bucket', '')}): {sample.get('scenario', '')}"
            )

    return "\n".join(lines) + "\n"
