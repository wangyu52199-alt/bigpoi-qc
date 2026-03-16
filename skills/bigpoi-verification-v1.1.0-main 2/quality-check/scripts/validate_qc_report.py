#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from qc_common import ISSUE_SEVERITIES, ensure_stdout_utf8, is_iso_time, read_json_file


CHECK_STATUSES = {"pass", "warning", "fail"}
OVERALL_STATUSES = {"pass", "manual_review", "fail"}
RECOMMENDED_ACTIONS = {"release", "manual_review", "return_to_verification"}


def add_error(errors: list[str], message: str) -> None:
    errors.append(message)


def validate_issue(issue: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(issue, dict):
        add_error(errors, f"{prefix} must be an object")
        return
    for field in ("severity", "code", "message", "file_role"):
        if not str(issue.get(field) or "").strip():
            add_error(errors, f"{prefix}.{field} is required")
    if issue.get("severity") not in ISSUE_SEVERITIES:
        add_error(errors, f"{prefix}.severity is invalid")


def validate_check(check: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(check, dict):
        add_error(errors, f"{prefix} must be an object")
        return
    for field in ("status", "score", "summary", "issue_count", "issues"):
        if field not in check:
            add_error(errors, f"{prefix}.{field} is required")
    status = check.get("status")
    if status not in CHECK_STATUSES:
        add_error(errors, f"{prefix}.status is invalid")
    score = check.get("score")
    if not isinstance(score, (int, float)) or float(score) < 0 or float(score) > 1:
        add_error(errors, f"{prefix}.score must be between 0 and 1")
    if not str(check.get("summary") or "").strip():
        add_error(errors, f"{prefix}.summary is required")
    issue_count = check.get("issue_count")
    if not isinstance(issue_count, int) or issue_count < 0:
        add_error(errors, f"{prefix}.issue_count must be a non-negative integer")
    issues = check.get("issues")
    if not isinstance(issues, list):
        add_error(errors, f"{prefix}.issues must be an array")
        return
    for index, issue in enumerate(issues):
        validate_issue(issue, f"{prefix}.issues[{index}]", errors)
    if isinstance(issue_count, int) and issue_count != len(issues):
        add_error(errors, f"{prefix}.issue_count must match issues length")


def validate_source_bundle(bundle: Any, errors: list[str]) -> None:
    if not isinstance(bundle, dict):
        add_error(errors, "source_bundle must be an object")
        return
    for field in ("index_path", "task_dir", "decision_path", "evidence_path", "record_path"):
        if field not in bundle:
            add_error(errors, f"source_bundle.{field} is required")
            continue
        if not isinstance(bundle.get(field), str):
            add_error(errors, f"source_bundle.{field} must be a string")
    if isinstance(bundle.get("index_path"), str) and not str(bundle["index_path"]).strip():
        add_error(errors, "source_bundle.index_path cannot be empty")
    if isinstance(bundle.get("task_dir"), str) and not str(bundle["task_dir"]).strip():
        add_error(errors, "source_bundle.task_dir cannot be empty")
    if bundle.get("input_path") is not None and not isinstance(bundle.get("input_path"), str):
        add_error(errors, "source_bundle.input_path must be a string")


def validate_source_distribution(distribution: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(distribution, dict):
        add_error(errors, f"{prefix} must be an object")
        return
    for field in ("official", "map_vendor", "internet", "user_contributed", "other"):
        value = distribution.get(field)
        if not isinstance(value, int) or value < 0:
            add_error(errors, f"{prefix}.{field} must be a non-negative integer")


def validate_metrics(metrics: Any, errors: list[str]) -> None:
    if not isinstance(metrics, dict):
        add_error(errors, "metrics must be an object")
        return
    for field in (
        "check_count",
        "evidence_count",
        "valid_evidence_count",
        "change_count",
        "correction_count",
        "critical_issue_count",
        "major_issue_count",
        "minor_issue_count",
        "name_support_count",
        "address_support_count",
        "coordinate_support_count",
    ):
        value = metrics.get(field)
        if not isinstance(value, int) or value < 0:
            add_error(errors, f"metrics.{field} must be a non-negative integer")
    validate_source_distribution(metrics.get("source_distribution"), "metrics.source_distribution", errors)


def main() -> int:
    ensure_stdout_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("-ReportPath", required=True)
    args = parser.parse_args()

    errors: list[str] = []
    report_path = Path(args.ReportPath)

    if not report_path.is_file():
        add_error(errors, f"report file does not exist: {report_path}")
        json.dump({"status": "failed", "reasons": errors, "report_path": str(report_path)}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    payload = read_json_file(report_path)
    if not isinstance(payload, dict):
        add_error(errors, "report file must contain an object")
        json.dump({"status": "failed", "reasons": errors, "report_path": str(report_path)}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    for field in ("qc_report_id", "task_id", "poi_id", "verification_run_id", "checked_at", "workspace_root", "source_bundle", "overall", "checks", "metrics"):
        if field not in payload:
            add_error(errors, f"{field} is required")

    for field in ("qc_report_id", "task_id", "poi_id", "verification_run_id", "workspace_root"):
        if field in payload and not isinstance(payload.get(field), str):
            add_error(errors, f"{field} must be a string")

    checked_at = payload.get("checked_at")
    if checked_at is not None and not is_iso_time(str(checked_at)):
        add_error(errors, "checked_at must be ISO datetime")

    validate_source_bundle(payload.get("source_bundle"), errors)

    overall = payload.get("overall")
    if not isinstance(overall, dict):
        add_error(errors, "overall must be an object")
    else:
        for field in ("status", "score", "summary", "recommended_action"):
            if field not in overall:
                add_error(errors, f"overall.{field} is required")
        if overall.get("status") not in OVERALL_STATUSES:
            add_error(errors, "overall.status is invalid")
        score = overall.get("score")
        if not isinstance(score, (int, float)) or float(score) < 0 or float(score) > 1:
            add_error(errors, "overall.score must be between 0 and 1")
        if not str(overall.get("summary") or "").strip():
            add_error(errors, "overall.summary is required")
        if overall.get("recommended_action") not in RECOMMENDED_ACTIONS:
            add_error(errors, "overall.recommended_action is invalid")

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        add_error(errors, "checks must be an object")
    else:
        for field in ("bundle_integrity", "cross_file_consistency", "evidence_support", "correction_consistency"):
            validate_check(checks.get(field), f"checks.{field}", errors)
        if "input_traceability" in checks:
            validate_check(checks.get("input_traceability"), "checks.input_traceability", errors)

    validate_metrics(payload.get("metrics"), errors)

    result = {
        "status": "passed" if not errors else "failed",
        "reasons": errors,
        "report_path": str(report_path.resolve()),
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
