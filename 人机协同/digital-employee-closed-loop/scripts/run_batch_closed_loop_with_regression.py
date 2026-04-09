#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    input_path = Path(path)
    for idx, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"jsonl line {idx} must be object")
        rows.append(payload)
    return rows


def _load_bucket_samples(path: str | Path | None, bucket_name: str) -> list[dict[str, Any]]:
    if path is None:
        return []
    data = _load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        value = data.get(bucket_name)
        if isinstance(value, list):
            return value
    raise ValueError(f"invalid bucket input format: {path}")


def _priority_score(level: str) -> int:
    if level == "high":
        return 3
    if level == "medium":
        return 2
    return 1


def _priority_text(score: int) -> str:
    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"


def _build_current_fix_sample(sample_result: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    sample_id = str(sample_result.get("sample_id", "sample-unknown"))
    per_target = sample_result.get("per_target", {})

    issue_summaries: list[str] = []
    max_priority = 1
    all_targets_ok = True

    for target_data in per_target.values():
        if not isinstance(target_data, dict):
            all_targets_ok = False
            continue

        improvement = target_data.get("improvement_record", {})
        issue_summary = str(improvement.get("issue_summary", ""))
        if issue_summary:
            issue_summaries.append(issue_summary)

        priority = str(improvement.get("training_priority", "low"))
        max_priority = max(max_priority, _priority_score(priority))

        iter_result = target_data.get("iteration_result", {})
        operations = iter_result.get("operations", [])
        if not isinstance(operations, list) or len(operations) == 0:
            all_targets_ok = False
            continue

        if dry_run:
            statuses = [str(op.get("status", "")) for op in operations if isinstance(op, dict)]
            if not statuses or any(s != "planned" for s in statuses):
                all_targets_ok = False
        else:
            applied = bool(iter_result.get("applied", False))
            if not applied:
                all_targets_ok = False

    scenario = " | ".join(issue_summaries) if issue_summaries else "闭环批处理样本"
    return {
        "sample_id": sample_id,
        "scenario": scenario,
        "expected_pass": True,
        "actual_pass": all_targets_ok,
        "risk_level": _priority_text(max_priority),
        "detail": {
            "resolved_targets": sample_result.get("resolved_targets", []),
            "first_routing_target": sample_result.get("first_routing_result", {}).get("first_routing_target"),
            "dry_run": dry_run,
        },
    }


def run_batch_pipeline(
    manual_samples: list[dict[str, Any]],
    targets_cfg: dict[str, Any],
    repo_root: Path,
    output_dir: Path,
    thresholds_path: Path,
    historical_samples: list[dict[str, Any]] | None = None,
    boundary_samples: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    pipeline_module = _load_module(
        "closed_loop_pipeline",
        repo_root / "scripts" / "run_closed_loop_pipeline.py",
    )
    validator_module = _load_module(
        "regression_validator",
        repo_root / "pre-release-regression-validation" / "src" / "validator.py",
    )

    sample_output_dir = output_dir / "samples"
    sample_output_dir.mkdir(parents=True, exist_ok=True)

    sample_results: list[dict[str, Any]] = []
    failed_runs: list[dict[str, Any]] = []

    for payload in manual_samples:
        sample_id = str(payload.get("sample_id") or payload.get("case_id") or "sample-unknown")
        try:
            result = pipeline_module.run_pipeline(
                manual_payload=payload,
                targets_cfg=targets_cfg,
                repo_root=repo_root,
                dry_run=dry_run,
            )
            sample_results.append(result)
            (sample_output_dir / f"{sample_id}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            failed_runs.append(
                {
                    "sample_id": sample_id,
                    "error": str(exc),
                }
            )

    current_fix_target = [_build_current_fix_sample(item, dry_run=dry_run) for item in sample_results]
    for failed in failed_runs:
        current_fix_target.append(
            {
                "sample_id": failed["sample_id"],
                "scenario": "闭环流水线执行失败",
                "expected_pass": True,
                "actual_pass": False,
                "risk_level": "high",
                "detail": {"error": failed["error"]},
            }
        )

    regression_input = {
        "historical_high_frequency": historical_samples or [],
        "current_fix_target": current_fix_target,
        "boundary_cases": boundary_samples or [],
    }

    thresholds = validator_module.load_thresholds(thresholds_path)
    report, markdown = validator_module.validate_regression(regression_input, thresholds)

    regression_input_path = output_dir / "regression_input.json"
    report_json_path = output_dir / "regression_report.json"
    report_md_path = output_dir / "regression_report.md"
    failed_runs_path = output_dir / "failed_runs.json"

    regression_input_path.write_text(json.dumps(regression_input, ensure_ascii=False, indent=2), encoding="utf-8")
    report_json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    report_md_path.write_text(markdown, encoding="utf-8")
    failed_runs_path.write_text(json.dumps(failed_runs, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "run_time": datetime.now().astimezone().isoformat(),
        "dry_run": dry_run,
        "total_samples": len(manual_samples),
        "succeeded_samples": len(sample_results),
        "failed_samples": len(failed_runs),
        "failed_runs": failed_runs,
        "regression_report": report.model_dump(mode="json"),
        "output_files": {
            "regression_input": str(regression_input_path),
            "regression_report_json": str(report_json_path),
            "regression_report_md": str(report_md_path),
            "failed_runs": str(failed_runs_path),
            "sample_output_dir": str(sample_output_dir),
        },
    }

    summary_path = output_dir / "batch_run_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run batch closed-loop + regression report")
    parser.add_argument("--manual-jsonl", required=True, help="Path to manual samples JSONL")
    parser.add_argument(
        "--targets-config",
        default=str(repo_root / "integrations" / "targets.yaml"),
        help="Path to integration target YAML",
    )
    parser.add_argument(
        "--thresholds",
        default=str(repo_root / "pre-release-regression-validation" / "config" / "regression_thresholds.yaml"),
        help="Path to regression threshold YAML",
    )
    parser.add_argument("--historical-input", default=None, help="Path to historical bucket JSON")
    parser.add_argument("--boundary-input", default=None, help="Path to boundary bucket JSON")
    parser.add_argument(
        "--output-dir",
        default=str(repo_root / "integration-output" / "batch"),
        help="Batch output root directory",
    )
    parser.add_argument("--run-id", default="", help="Run id suffix; default uses timestamp")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not apply writes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    manual_samples = _load_jsonl(args.manual_jsonl)
    targets_cfg = _load_json(args.targets_config) if str(args.targets_config).endswith(".json") else None
    if targets_cfg is None:
        import yaml

        loaded = yaml.safe_load(Path(args.targets_config).read_text(encoding="utf-8"))
        targets_cfg = loaded if isinstance(loaded, dict) else {}

    historical = _load_bucket_samples(args.historical_input, "historical_high_frequency")
    boundary = _load_bucket_samples(args.boundary_input, "boundary_cases")

    run_id = args.run_id.strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_batch_pipeline(
        manual_samples=manual_samples,
        targets_cfg=targets_cfg,
        repo_root=repo_root,
        output_dir=output_dir,
        thresholds_path=Path(args.thresholds),
        historical_samples=historical,
        boundary_samples=boundary,
        dry_run=args.dry_run,
    )

    print(f"[OK] batch run finished: {output_dir}")
    print(f"[OK] overall_pass: {summary['regression_report']['overall_pass']}")
    print(f"[OK] release_recommendation: {summary['regression_report']['release_recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
