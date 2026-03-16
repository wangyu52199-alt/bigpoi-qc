#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent
PARENT_SCRIPT_DIR = REPO_ROOT / "skills-bigpoi-verification" / "scripts"

for candidate in (SCRIPT_DIR, PARENT_SCRIPT_DIR, REPO_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from qc_common import (
    TRACKED_FIELDS,
    build_issue,
    ensure_stdout_utf8,
    floats_close,
    format_change_value,
    get_final_field_value,
    get_input_field_value,
    haversine_distance_meters,
    normalize_coordinate_value,
    normalize_input,
    normalize_scalar_value,
    normalize_text,
    read_json_file,
    source_distribution,
    utc_iso_now,
    utc_timestamp,
    values_equal,
    write_json_file,
)
from runtime_paths import detect_workspace_root


AUTO_ACCEPT_MIN_CONFIDENCE = 0.85
MIN_EVIDENCE_COUNT = 2
COORDINATE_SUPPORT_DISTANCE_METERS = 500.0
REQUIRED_DIMENSIONS = ("existence", "name", "address", "coordinates", "category")
DECISION_TO_RECORD_STATUS = {
    "accepted": "verified",
    "downgraded": "modified",
    "manual_review": "manual_review_pending",
    "rejected": "rejected",
}


def normalize_bundle_path(raw_value: Any, task_dir: Path) -> tuple[Path | None, str]:
    text = str(raw_value or "").strip()
    if not text:
        return None, ""
    raw_path = Path(text)
    resolved = raw_path if raw_path.is_absolute() else (task_dir / raw_path)
    return resolved.resolve(), str(resolved.resolve())


def load_optional_json(path: Path | None) -> tuple[Any | None, str | None]:
    if path is None:
        return None, "path is missing"
    if not path.is_file():
        return None, f"file does not exist: {path}"
    try:
        return read_json_file(path), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def run_bundle_validator(task_dir: Path, workspace_root: Path) -> dict[str, Any]:
    validator = PARENT_SCRIPT_DIR / "validate_result_bundle.py"
    if not validator.is_file():
        return {
            "status": "failed",
            "failed_stage": "parent_integration",
            "reasons": [f"bundle validator is missing: {validator}"],
            "warnings": [],
            "retry_action": "restore validate_result_bundle.py before rerunning quality-check",
        }

    completed = subprocess.run(
        [
            sys.executable,
            str(validator),
            "-TaskDir",
            str(task_dir),
            "-WorkspaceRoot",
            str(workspace_root),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "bundle validator exited with non-zero status"
        return {
            "status": "failed",
            "failed_stage": "parent_integration",
            "reasons": [message],
            "warnings": [],
            "retry_action": "repair bundle validator execution, then rerun quality-check",
        }
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "failed_stage": "parent_integration",
            "reasons": ["bundle validator returned invalid JSON"],
            "warnings": [completed.stdout.strip()] if completed.stdout.strip() else [],
            "retry_action": "repair bundle validator output, then rerun quality-check",
        }


def build_check_result(pass_summary: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    severity_counts = Counter(str(item.get("severity") or "") for item in issues)
    penalties = {"critical": 0.5, "major": 0.25, "minor": 0.1}
    score = 1.0
    for severity, count in severity_counts.items():
        score -= penalties.get(severity, 0.0) * count
    score = round(max(0.0, score), 4)

    critical_count = severity_counts.get("critical", 0)
    major_count = severity_counts.get("major", 0)
    minor_count = severity_counts.get("minor", 0)

    if critical_count or major_count:
        status = "fail"
        summary = f"发现严重{critical_count}项、主要{major_count}项、提示{minor_count}项，建议退回核实。"
    elif minor_count:
        status = "warning"
        summary = f"发现提示{minor_count}项，建议人工复核后再放行。"
    else:
        status = "pass"
        summary = pass_summary

    return {
        "status": status,
        "score": score,
        "summary": summary,
        "issue_count": len(issues),
        "issues": issues,
    }


def compute_valid_evidence_count(evidence: list[dict[str, Any]]) -> int:
    count = 0
    for item in evidence:
        verification = item.get("verification") if isinstance(item.get("verification"), dict) else {}
        if verification.get("is_valid") is True:
            count += 1
    return count


def compute_high_weight_count(evidence: list[dict[str, Any]]) -> int:
    count = 0
    for item in evidence:
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        if source.get("weight") is None:
            continue
        try:
            if float(source["weight"]) >= 0.8:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


def compute_evidence_quality(evidence: list[dict[str, Any]]) -> float:
    confidences: list[float] = []
    for item in evidence:
        verification = item.get("verification") if isinstance(item.get("verification"), dict) else {}
        if verification.get("confidence") is None:
            continue
        try:
            confidences.append(float(verification["confidence"]))
        except (TypeError, ValueError):
            continue
    if not confidences:
        return 0.0
    return round(sum(confidences) / len(confidences), 4)


def compute_source_diversity(evidence: list[dict[str, Any]]) -> float:
    source_types = {
        str(item["source"]["source_type"])
        for item in evidence
        if isinstance(item.get("source"), dict) and str(item["source"].get("source_type") or "").strip()
    }
    return round(len(source_types) / 5.0, 4)


def compute_field_support(final_values: dict[str, Any], evidence: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    support = {
        "name_support_count": 0,
        "address_support_count": 0,
        "coordinate_support_count": 0,
    }
    available = {
        "name": 0,
        "address": 0,
        "coordinates": 0,
    }

    final_name = normalize_text(final_values.get("name"))
    final_address = normalize_text(final_values.get("address"))
    final_coordinates = normalize_coordinate_value(final_values.get("coordinates"))

    for item in evidence:
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        evidence_name = normalize_text(data.get("name"))
        if evidence_name:
            available["name"] += 1
            if final_name and evidence_name == final_name:
                support["name_support_count"] += 1

        evidence_address = normalize_text(data.get("address"))
        if evidence_address:
            available["address"] += 1
            if final_address and evidence_address == final_address:
                support["address_support_count"] += 1

        evidence_coordinates = normalize_coordinate_value(data.get("coordinates"))
        if evidence_coordinates is not None:
            available["coordinates"] += 1
            if final_coordinates is not None:
                distance = haversine_distance_meters(final_coordinates, evidence_coordinates)
                if distance is not None and distance <= COORDINATE_SUPPORT_DISTANCE_METERS:
                    support["coordinate_support_count"] += 1

    return support, available


def collect_bundle_integrity_issues(validation: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    retry_action = str(validation.get("retry_action") or "").strip() or None
    status = str(validation.get("status") or "")
    failed_stage = str(validation.get("failed_stage") or "")

    if status == "failed":
        for reason in validation.get("reasons", []):
            issues.append(
                build_issue(
                    "major",
                    f"bundle_validation_failed_{failed_stage or 'unknown'}",
                    str(reason),
                    "bundle",
                    suggestion=retry_action,
                )
            )

    for warning in validation.get("warnings", []):
        issues.append(
            build_issue(
                "minor",
                "bundle_validation_warning",
                str(warning),
                "bundle",
                suggestion=retry_action,
            )
        )

    return issues


def collect_cross_file_consistency_issues(
    index: dict[str, Any],
    decision: Any,
    evidence: Any,
    record: Any,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(decision, dict):
        issues.append(build_issue("critical", "missing_decision_payload", "decision 文件缺失或不是 JSON 对象。", "decision"))
        return issues
    if not isinstance(record, dict):
        issues.append(build_issue("critical", "missing_record_payload", "record 文件缺失或不是 JSON 对象。", "record"))
        return issues
    if not isinstance(evidence, list):
        issues.append(build_issue("critical", "missing_evidence_payload", "evidence 文件缺失或不是 JSON 数组。", "evidence"))
        return issues

    decision_id = str(decision.get("decision_id") or "").strip()
    record_decision_ref = str(record.get("decision_ref") or "").strip()
    if decision_id and record_decision_ref and record_decision_ref != decision_id:
        issues.append(
            build_issue(
                "major",
                "decision_ref_mismatch",
                "record.decision_ref 与 decision.decision_id 不一致。",
                "record",
                field_path="decision_ref",
            )
        )

    actual_evidence_ids = [str(item.get("evidence_id") or "").strip() for item in evidence if isinstance(item, dict)]
    actual_evidence_ids = [item for item in actual_evidence_ids if item]
    record_evidence_refs = []
    if isinstance(record.get("evidence_refs"), list):
        record_evidence_refs = [str(item).strip() for item in record["evidence_refs"] if str(item).strip()]

    if len(set(actual_evidence_ids)) != len(actual_evidence_ids):
        issues.append(build_issue("major", "duplicate_evidence_ids", "evidence 中存在重复的 evidence_id。", "evidence", field_path="[].evidence_id"))

    if len(set(record_evidence_refs)) != len(record_evidence_refs):
        issues.append(build_issue("major", "duplicate_record_evidence_refs", "record.evidence_refs 中存在重复值。", "record", field_path="evidence_refs"))

    if set(record_evidence_refs) != set(actual_evidence_ids):
        issues.append(
            build_issue(
                "major",
                "record_evidence_refs_mismatch",
                "record.evidence_refs 与 evidence 文件中的 evidence_id 集合不一致。",
                "record",
                field_path="evidence_refs",
            )
        )

    decision_summary = decision.get("evidence_summary") if isinstance(decision.get("evidence_summary"), dict) else {}
    distribution = source_distribution(evidence)
    valid_count = compute_valid_evidence_count(evidence)
    high_weight_count = compute_high_weight_count(evidence)

    if decision_summary:
        if decision_summary.get("total_count") is not None and int(decision_summary["total_count"]) != len(evidence):
            issues.append(build_issue("major", "decision_total_count_mismatch", "decision.evidence_summary.total_count 与 evidence 数量不一致。", "decision", field_path="evidence_summary.total_count"))
        if decision_summary.get("valid_count") is not None and int(decision_summary["valid_count"]) != valid_count:
            issues.append(build_issue("major", "decision_valid_count_mismatch", "decision.evidence_summary.valid_count 与有效证据数量不一致。", "decision", field_path="evidence_summary.valid_count"))
        if decision_summary.get("high_weight_count") is not None and int(decision_summary["high_weight_count"]) != high_weight_count:
            issues.append(build_issue("major", "decision_high_weight_count_mismatch", "decision.evidence_summary.high_weight_count 与高权重证据数量不一致。", "decision", field_path="evidence_summary.high_weight_count"))
        summary_distribution = decision_summary.get("source_distribution") if isinstance(decision_summary.get("source_distribution"), dict) else {}
        for key in ("official", "map_vendor", "internet"):
            if summary_distribution.get(key) is not None and int(summary_distribution[key]) != distribution[key]:
                issues.append(build_issue("major", f"decision_source_distribution_{key}_mismatch", f"decision.evidence_summary.source_distribution.{key} 与实际证据来源分布不一致。", "decision", field_path=f"evidence_summary.source_distribution.{key}"))

    verification_result = record.get("verification_result") if isinstance(record.get("verification_result"), dict) else {}
    expected_record_status = DECISION_TO_RECORD_STATUS.get(str(decision.get("overall", {}).get("status") or ""), "")
    record_status = str(verification_result.get("status") or "").strip()
    if expected_record_status and record_status and expected_record_status != record_status:
        issues.append(build_issue("major", "record_status_mismatch", "record.verification_result.status 与 decision.overall.status 的映射结果不一致。", "record", field_path="verification_result.status"))

    decision_confidence = decision.get("overall", {}).get("confidence") if isinstance(decision.get("overall"), dict) else None
    record_confidence = verification_result.get("confidence")
    if decision_confidence is not None and record_confidence is not None and not floats_close(decision_confidence, record_confidence):
        issues.append(build_issue("major", "record_confidence_mismatch", "record.verification_result.confidence 与 decision.overall.confidence 不一致。", "record", field_path="verification_result.confidence"))

    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    data_sources = metadata.get("data_sources") if isinstance(metadata.get("data_sources"), list) else None
    actual_source_ids = sorted(
        {
            str(item["source"]["source_id"])
            for item in evidence
            if isinstance(item.get("source"), dict) and str(item["source"].get("source_id") or "").strip()
        }
    )
    if data_sources is None:
        issues.append(build_issue("minor", "missing_record_data_sources", "record.metadata.data_sources 缺失，无法追溯实际来源集合。", "record", field_path="metadata.data_sources"))
    else:
        normalized_sources = sorted({str(item).strip() for item in data_sources if str(item).strip()})
        if normalized_sources != actual_source_ids:
            issues.append(build_issue("major", "record_data_sources_mismatch", "record.metadata.data_sources 与 evidence 实际 source_id 集合不一致。", "record", field_path="metadata.data_sources"))

    custom_fields = metadata.get("custom_fields") if isinstance(metadata.get("custom_fields"), dict) else {}
    if custom_fields:
        index_task_id = str(index.get("task_id") or "").strip()
        custom_task_id = str(custom_fields.get("task_id") or "").strip()
        if index_task_id and custom_task_id and custom_task_id != index_task_id:
            issues.append(build_issue("major", "record_task_id_mismatch", "record.metadata.custom_fields.task_id 与 index.task_id 不一致。", "record", field_path="metadata.custom_fields.task_id"))
        bundle_run_id = str(index.get("run_id") or record.get("run_id") or "").strip()
        custom_run_id = str(custom_fields.get("run_id") or "").strip()
        if bundle_run_id and custom_run_id and custom_run_id != bundle_run_id:
            issues.append(build_issue("major", "record_custom_run_id_mismatch", "record.metadata.custom_fields.run_id 与结果包 run_id 不一致。", "record", field_path="metadata.custom_fields.run_id"))
    else:
        issues.append(build_issue("minor", "missing_record_custom_fields", "record.metadata.custom_fields 缺失，任务与运行追踪信息不完整。", "record", field_path="metadata.custom_fields"))

    quality_metrics = record.get("quality_metrics") if isinstance(record.get("quality_metrics"), dict) else {}
    if not quality_metrics:
        issues.append(build_issue("minor", "missing_quality_metrics", "record.quality_metrics 缺失，无法复核派生质量指标。", "record", field_path="quality_metrics"))
        return issues

    evidence_quality = quality_metrics.get("evidence_quality")
    expected_evidence_quality = compute_evidence_quality(evidence)
    if evidence_quality is not None and not floats_close(evidence_quality, expected_evidence_quality):
        issues.append(build_issue("minor", "evidence_quality_mismatch", "record.quality_metrics.evidence_quality 与 evidence 置信度均值不一致。", "record", field_path="quality_metrics.evidence_quality"))

    source_diversity_value = quality_metrics.get("source_diversity")
    expected_source_diversity = compute_source_diversity(evidence)
    if source_diversity_value is not None and not floats_close(source_diversity_value, expected_source_diversity):
        issues.append(build_issue("minor", "source_diversity_mismatch", "record.quality_metrics.source_diversity 与 evidence 来源多样性不一致。", "record", field_path="quality_metrics.source_diversity"))

    dimension_scores = quality_metrics.get("dimension_scores") if isinstance(quality_metrics.get("dimension_scores"), dict) else {}
    decision_dimensions = decision.get("dimensions") if isinstance(decision.get("dimensions"), dict) else {}
    for dimension_name, dimension in decision_dimensions.items():
        if not isinstance(dimension, dict):
            continue
        expected_score = dimension.get("score", dimension.get("confidence"))
        actual_score = dimension_scores.get(dimension_name)
        if actual_score is None:
            issues.append(build_issue("minor", "missing_dimension_score", f"record.quality_metrics.dimension_scores 缺少 {dimension_name}。", "record", field_path=f"quality_metrics.dimension_scores.{dimension_name}"))
            continue
        if expected_score is not None and not floats_close(actual_score, expected_score):
            issues.append(build_issue("minor", "dimension_score_mismatch", f"record.quality_metrics.dimension_scores.{dimension_name} 与 decision.dimensions.{dimension_name} 不一致。", "record", field_path=f"quality_metrics.dimension_scores.{dimension_name}"))

    return issues


def collect_evidence_support_issues(
    decision: Any,
    evidence: Any,
    record: Any,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    issues: list[dict[str, Any]] = []
    support_metrics = {
        "name_support_count": 0,
        "address_support_count": 0,
        "coordinate_support_count": 0,
    }

    if not isinstance(decision, dict):
        issues.append(build_issue("critical", "missing_decision_payload", "decision 文件缺失或不是 JSON 对象。", "decision"))
        return issues, support_metrics
    if not isinstance(record, dict):
        issues.append(build_issue("critical", "missing_record_payload", "record 文件缺失或不是 JSON 对象。", "record"))
        return issues, support_metrics
    if not isinstance(evidence, list):
        issues.append(build_issue("critical", "missing_evidence_payload", "evidence 文件缺失或不是 JSON 数组。", "evidence"))
        return issues, support_metrics

    evidence_count = len(evidence)
    if evidence_count < MIN_EVIDENCE_COUNT:
        issues.append(build_issue("minor", "insufficient_evidence_count", f"正式 evidence 数量仅 {evidence_count} 条，低于推荐最小值 {MIN_EVIDENCE_COUNT}。", "evidence"))

    distribution = source_distribution(evidence)
    populated_source_types = sum(1 for value in distribution.values() if value > 0)
    overall = decision.get("overall") if isinstance(decision.get("overall"), dict) else {}
    overall_status = str(overall.get("status") or "").strip()
    overall_confidence = overall.get("confidence")

    if populated_source_types < 2:
        issues.append(build_issue("minor", "low_source_diversity", "证据来源类型少于 2 类，抗偏差能力偏弱。", "evidence"))

    if overall_status == "accepted" and overall_confidence is not None and float(overall_confidence) < AUTO_ACCEPT_MIN_CONFIDENCE:
        issues.append(build_issue("major", "accepted_below_threshold", f"decision.overall.status 为 accepted，但 overall.confidence={float(overall_confidence):.4f} 低于 0.85。", "decision", field_path="overall.confidence"))

    dimensions = decision.get("dimensions") if isinstance(decision.get("dimensions"), dict) else {}
    if overall_status == "accepted":
        non_pass_dimensions = [name for name in REQUIRED_DIMENSIONS if str((dimensions.get(name) or {}).get("result") or "") != "pass"]
        if non_pass_dimensions:
            issues.append(build_issue("critical", "accepted_with_non_pass_dimension", f"decision.overall.status 为 accepted，但以下关键维度不是 pass：{', '.join(non_pass_dimensions)}。", "decision", field_path="dimensions"))

    if distribution["official"] + distribution["map_vendor"] == 0:
        severity = "major" if overall_status == "accepted" else "minor"
        issues.append(build_issue(severity, "missing_authoritative_source", "正式 evidence 中没有 official 或 map_vendor 来源，权威支撑不足。", "evidence"))

    verification_result = record.get("verification_result") if isinstance(record.get("verification_result"), dict) else {}
    final_values = verification_result.get("final_values") if isinstance(verification_result.get("final_values"), dict) else {}
    support_metrics, available_metrics = compute_field_support(final_values, evidence)

    final_name = normalize_text(final_values.get("name"))
    if final_name and available_metrics["name"] and support_metrics["name_support_count"] == 0 and overall_status != "rejected":
        severity = "major" if overall_status == "accepted" else "minor"
        issues.append(build_issue(severity, "unsupported_final_name", "record.verification_result.final_values.name 在 evidence 中找不到直接支撑。", "record", field_path="verification_result.final_values.name"))

    final_address = normalize_text(final_values.get("address"))
    address_result = str((dimensions.get("address") or {}).get("result") or "")
    if final_address and available_metrics["address"] and support_metrics["address_support_count"] == 0 and address_result == "pass":
        severity = "major" if overall_status == "accepted" else "minor"
        issues.append(build_issue(severity, "unsupported_final_address", "地址维度判定为 pass，但 final_values.address 在 evidence 中没有直接支撑。", "record", field_path="verification_result.final_values.address"))

    final_coordinates = normalize_coordinate_value(final_values.get("coordinates"))
    coordinates_result = str((dimensions.get("coordinates") or {}).get("result") or "")
    if final_coordinates is not None:
        if available_metrics["coordinates"] == 0 and coordinates_result == "pass":
            issues.append(build_issue("minor", "missing_coordinate_evidence", "坐标维度判定为 pass，但 evidence 中没有坐标信息可供追溯。", "decision", field_path="dimensions.coordinates"))
        elif available_metrics["coordinates"] > 0 and support_metrics["coordinate_support_count"] == 0 and coordinates_result == "pass":
            severity = "major" if overall_status == "accepted" else "minor"
            issues.append(build_issue(severity, "unsupported_final_coordinates", f"坐标维度判定为 pass，但 final_values.coordinates 在 {COORDINATE_SUPPORT_DISTANCE_METERS:.0f} 米范围内找不到支撑证据。", "record", field_path="verification_result.final_values.coordinates"))

    dimension_ref_total = 0
    for dimension_name in REQUIRED_DIMENSIONS:
        dimension = dimensions.get(dimension_name)
        if not isinstance(dimension, dict):
            continue
        refs = dimension.get("evidence_refs")
        if isinstance(refs, list):
            dimension_ref_total += len([str(item).strip() for item in refs if str(item).strip()])
    if overall_status in {"accepted", "downgraded"} and dimension_ref_total == 0:
        issues.append(build_issue("minor", "missing_dimension_refs", "关键维度均未提供 evidence_refs，证据追溯链路偏弱。", "decision", field_path="dimensions"))

    return issues, support_metrics


def collect_correction_consistency_issues(decision: Any, record: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(decision, dict):
        issues.append(build_issue("critical", "missing_decision_payload", "decision 文件缺失或不是 JSON 对象。", "decision"))
        return issues
    if not isinstance(record, dict):
        issues.append(build_issue("critical", "missing_record_payload", "record 文件缺失或不是 JSON 对象。", "record"))
        return issues

    corrections = decision.get("corrections") if isinstance(decision.get("corrections"), dict) else {}
    verification_result = record.get("verification_result") if isinstance(record.get("verification_result"), dict) else {}
    input_data = record.get("input_data") if isinstance(record.get("input_data"), dict) else {}
    final_values = verification_result.get("final_values") if isinstance(verification_result.get("final_values"), dict) else {}
    changes = verification_result.get("changes") if isinstance(verification_result.get("changes"), list) else []

    change_map: dict[str, dict[str, Any]] = {}
    for item in changes:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        if not field:
            continue
        change_map[field] = item
        if field not in TRACKED_FIELDS:
            issues.append(build_issue("minor", "unsupported_change_field", f"record.verification_result.changes 包含未纳入正式修正闭环的字段 {field}。", "record", field_path="verification_result.changes"))

    for field in TRACKED_FIELDS:
        original_value = get_input_field_value(input_data, field)
        final_value = get_final_field_value(final_values, field)
        correction = corrections.get(field) if isinstance(corrections.get(field), dict) else None
        change = change_map.get(field)

        changed = False
        if original_value is not None and final_value is not None:
            changed = not values_equal(original_value, final_value)

        if changed and correction is None:
            issues.append(build_issue("major", "missing_decision_correction", f"final_values.{field} 相比 input_data 已发生变化，但 decision.corrections.{field} 缺失。", "decision", field_path=f"corrections.{field}"))

        if correction is not None and original_value is not None and final_value is not None and values_equal(original_value, final_value):
            issues.append(build_issue("major", "redundant_decision_correction", f"decision.corrections.{field} 已声明修正，但 final_values.{field} 与 input_data 未发生变化。", "record", field_path=f"verification_result.final_values.{field}"))

        if change is not None and not changed and original_value is not None and final_value is not None:
            issues.append(build_issue("major", "stale_record_change", f"record.verification_result.changes 中记录了 {field} 变更，但 final_values.{field} 与 input_data 一致。", "record", field_path="verification_result.changes"))

        if change is not None and final_value is not None:
            expected_new_value = format_change_value(final_value)
            actual_new_value = str(change.get("new_value") or "")
            if expected_new_value != actual_new_value:
                issues.append(build_issue("major", "record_change_new_value_mismatch", f"record.verification_result.changes 中 {field} 的 new_value 与 final_values.{field} 不一致。", "record", field_path="verification_result.changes"))

        if change is not None and original_value is not None:
            expected_old_value = format_change_value(original_value)
            actual_old_value = str(change.get("old_value") or "")
            if actual_old_value and expected_old_value != actual_old_value:
                issues.append(build_issue("minor", "record_change_old_value_mismatch", f"record.verification_result.changes 中 {field} 的 old_value 与 input_data 不一致。", "record", field_path="verification_result.changes"))

    return issues


def collect_input_traceability_issues(original_input: Any, index: dict[str, Any], record: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(original_input, dict):
        issues.append(build_issue("critical", "invalid_original_input", "原始输入文件不是 JSON 对象。", "input"))
        return issues
    if not isinstance(record, dict):
        issues.append(build_issue("critical", "missing_record_payload", "record 文件缺失或不是 JSON 对象。", "record"))
        return issues

    normalized_input = normalize_input(original_input)
    record_input = record.get("input_data") if isinstance(record.get("input_data"), dict) else {}
    input_id = str(normalized_input.get("id") or "").strip()
    bundle_poi_id = str(record.get("poi_id") or index.get("poi_id") or "").strip()
    if input_id and bundle_poi_id and input_id != bundle_poi_id:
        issues.append(build_issue("critical", "input_poi_id_mismatch", "原始输入 id 与结果包 poi_id 不一致。", "input", field_path="id"))

    input_task_id = str(normalized_input.get("task_id") or "").strip()
    index_task_id = str(index.get("task_id") or "").strip()
    if input_task_id and index_task_id and input_task_id != index_task_id:
        issues.append(build_issue("major", "input_task_id_mismatch", "原始输入 task_id 与 index.task_id 不一致。", "input", field_path="task_id"))

    field_mapping = (
        ("name", "name"),
        ("poi_type", "poi_type"),
        ("city", "city"),
        ("address", "address"),
        ("source", "source"),
        ("city_adcode", "city_adcode"),
    )
    for input_field, record_field in field_mapping:
        if normalized_input.get(input_field) is None:
            continue
        expected = normalize_scalar_value(normalized_input.get(input_field))
        actual = normalize_scalar_value(record_input.get(record_field))
        if not values_equal(expected, actual):
            issues.append(build_issue("major", "input_snapshot_mismatch", f"record.input_data.{record_field} 与原始输入 {input_field} 不一致。", "record", field_path=f"input_data.{record_field}"))

    original_coordinates = normalize_coordinate_value(normalized_input.get("coordinates"))
    if original_coordinates is not None:
        record_coordinates = normalize_coordinate_value(record_input.get("coordinates"))
        if not values_equal(original_coordinates, record_coordinates):
            issues.append(build_issue("major", "input_coordinate_snapshot_mismatch", "record.input_data.coordinates 与原始输入 coordinates 不一致。", "record", field_path="input_data.coordinates"))

    return issues


def build_overall(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    check_values = list(checks.values())
    score = round(sum(float(item["score"]) for item in check_values) / len(check_values), 4)

    issue_counter = Counter()
    for check in check_values:
        for issue in check["issues"]:
            issue_counter[str(issue.get("severity") or "")] += 1

    if any(item["status"] == "fail" for item in check_values):
        status = "fail"
        recommended_action = "return_to_verification"
        summary = f"质检未通过，发现严重{issue_counter['critical']}项、主要{issue_counter['major']}项、提示{issue_counter['minor']}项，建议退回核实链路处理。"
    elif any(item["status"] == "warning" for item in check_values):
        status = "manual_review"
        recommended_action = "manual_review"
        summary = f"质检完成，未发现阻断问题，但存在提示{issue_counter['minor']}项，建议人工复核后再放行。"
    else:
        status = "pass"
        recommended_action = "release"
        summary = "质检通过，结果包结构完整，跨文件一致性与证据支撑未发现异常。"

    return {
        "status": status,
        "score": score,
        "summary": summary,
        "recommended_action": recommended_action,
    }


def main() -> int:
    ensure_stdout_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("-IndexPath", required=True)
    parser.add_argument("-PoiPath")
    parser.add_argument("-WorkspaceRoot")
    args = parser.parse_args()

    index_path = Path(args.IndexPath).resolve()
    if not index_path.is_file():
        raise FileNotFoundError(f"index file not found: {index_path}")

    index = read_json_file(index_path)
    if not isinstance(index, dict):
        raise ValueError("index file must contain an object")

    task_dir = index_path.parent.resolve()
    task_id = str(index.get("task_id") or task_dir.name)
    workspace_detection = detect_workspace_root(
        workspace_hint=args.WorkspaceRoot,
        related_paths=(index_path, args.PoiPath, task_dir),
        cwd=Path.cwd(),
    )
    workspace_root = workspace_detection.workspace_root.resolve()

    files = index.get("files") if isinstance(index.get("files"), dict) else {}
    decision_path, decision_path_text = normalize_bundle_path(files.get("decision"), task_dir)
    evidence_path, evidence_path_text = normalize_bundle_path(files.get("evidence"), task_dir)
    record_path, record_path_text = normalize_bundle_path(files.get("record"), task_dir)

    decision, _ = load_optional_json(decision_path)
    evidence, _ = load_optional_json(evidence_path)
    record, _ = load_optional_json(record_path)
    original_input = None
    input_path_text = ""
    if args.PoiPath:
        original_input = read_json_file(args.PoiPath)
        input_path_text = str(Path(args.PoiPath).resolve())

    bundle_validation = run_bundle_validator(task_dir, workspace_root)
    checks: dict[str, dict[str, Any]] = {}
    checks["bundle_integrity"] = build_check_result("结果包结构与父技能正式合同一致。", collect_bundle_integrity_issues(bundle_validation))
    checks["cross_file_consistency"] = build_check_result("跨文件 ID、统计项与派生字段保持一致。", collect_cross_file_consistency_issues(index, decision, evidence, record))
    evidence_support_issues, support_metrics = collect_evidence_support_issues(decision, evidence, record)
    checks["evidence_support"] = build_check_result("证据数量、来源和关键字段支撑度满足质检要求。", evidence_support_issues)
    checks["correction_consistency"] = build_check_result("修正、最终值与变更记录保持闭环一致。", collect_correction_consistency_issues(decision, record))
    if original_input is not None:
        checks["input_traceability"] = build_check_result("原始输入与 record.input_data 保持一致。", collect_input_traceability_issues(original_input, index, record))

    overall = build_overall(checks)
    poi_id = str(index.get("poi_id") or (record.get("poi_id") if isinstance(record, dict) else "") or "")
    verification_run_id = str(index.get("run_id") or (record.get("run_id") if isinstance(record, dict) else "") or (decision.get("run_id") if isinstance(decision, dict) else "") or "")

    evidence_list = evidence if isinstance(evidence, list) else []
    record_verification_result = record.get("verification_result") if isinstance(record, dict) and isinstance(record.get("verification_result"), dict) else {}
    decision_corrections = decision.get("corrections") if isinstance(decision, dict) and isinstance(decision.get("corrections"), dict) else {}

    severity_counter = Counter()
    for check in checks.values():
        for issue in check["issues"]:
            severity_counter[str(issue.get("severity") or "")] += 1

    timestamp = utc_timestamp()
    checked_at = utc_iso_now()
    hash_source = f"{task_id}|{poi_id}|{timestamp}|qc".encode("utf-8")
    short_hash = hashlib.sha256(hash_source).hexdigest()[:8].upper()

    report = {
        "qc_report_id": f"QC_{timestamp}_{short_hash}",
        "task_id": task_id,
        "poi_id": poi_id,
        "verification_run_id": verification_run_id,
        "checked_at": checked_at,
        "workspace_root": str(workspace_root),
        "source_bundle": {
            "index_path": str(index_path),
            "task_dir": str(task_dir),
            "decision_path": decision_path_text,
            "evidence_path": evidence_path_text,
            "record_path": record_path_text,
        },
        "overall": overall,
        "checks": checks,
        "metrics": {
            "check_count": len(checks),
            "evidence_count": len(evidence_list),
            "valid_evidence_count": compute_valid_evidence_count(evidence_list),
            "change_count": len(record_verification_result.get("changes") if isinstance(record_verification_result.get("changes"), list) else []),
            "correction_count": len(decision_corrections),
            "critical_issue_count": severity_counter["critical"],
            "major_issue_count": severity_counter["major"],
            "minor_issue_count": severity_counter["minor"],
            "source_distribution": source_distribution(evidence_list),
            "name_support_count": support_metrics["name_support_count"],
            "address_support_count": support_metrics["address_support_count"],
            "coordinate_support_count": support_metrics["coordinate_support_count"],
        },
    }
    if input_path_text:
        report["source_bundle"]["input_path"] = input_path_text

    output_dir = workspace_root / "output" / "qc_results" / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"qc_report_{timestamp}.json"
    write_json_file(report, report_path)

    validator = SCRIPT_DIR / "validate_qc_report.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(validator),
            "-ReportPath",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"qc validator execution failed: {completed.stderr.strip() or completed.stdout.strip()}")
    validation = json.loads(completed.stdout)
    if validation.get("status") != "passed":
        reason_text = "; ".join(validation.get("reasons", []))
        raise ValueError(f"qc report validation failed: {reason_text}")

    result = {
        "status": "ok",
        "task_id": task_id,
        "poi_id": poi_id,
        "verification_run_id": verification_run_id,
        "workspace_root": str(workspace_root),
        "qc_report_path": str(report_path.resolve()),
        "overall_status": overall["status"],
        "recommended_action": overall["recommended_action"],
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
