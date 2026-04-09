from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.schemas import IterationExecutionResult, IterationOperation, SecondRoutingResult, VerifyAgentImprovementRecord
from shared.utils import append_jsonl, append_markdown, append_yaml_rule

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


def _load_config(path: str | Path) -> dict[str, Any]:
    cfg_path = Path(path)
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def run_verify_auto_iteration(
    improvement_payload: dict[str, Any],
    second_routing_payload: dict[str, Any],
    target_skill_path: str | Path,
    config_path: str | Path,
    dry_run: bool = False,
) -> IterationExecutionResult:
    improvement = VerifyAgentImprovementRecord.model_validate(improvement_payload)
    second = SecondRoutingResult.model_validate(second_routing_payload)
    cfg = _load_config(config_path)

    target_root = Path(target_skill_path).resolve()
    paths = cfg.get("paths", {})
    bucket_key = str(cfg.get("rules_bucket_key", "auto_verify_rules"))

    rule_file = target_root / str(paths.get("rule_file", "config/verify_rules.yaml"))
    regression_file = target_root / str(paths.get("regression_file", "regression/current_fix_target.jsonl"))
    log_file = target_root / str(paths.get("log_file", "changelog/auto_iteration.md"))

    if second.primary_module in VERIFY_MODULES:
        primary_module = second.primary_module
    elif improvement.suspected_modules:
        primary_module = improvement.suspected_modules[0]
    else:
        primary_module = "decision"

    auto_rule = {
        "id": f"verify-auto-{improvement.sample_id}",
        "module": primary_module,
        "issue_summary": improvement.issue_summary,
        "related_dimensions": improvement.related_dimensions,
        "evidence_gap": improvement.evidence_gap,
        "training_priority": improvement.training_priority.value,
        "created_at": datetime.now().astimezone().isoformat(),
    }

    regression_case = {
        "sample_id": improvement.sample_id,
        "scenario": improvement.issue_summary,
        "expected_pass": True,
        "actual_pass": False,
        "risk_level": improvement.training_priority.value,
        "detail": improvement.regression_case_candidate,
    }

    log_entry = (
        f"## {improvement.sample_id}\\n"
        f"- module: {primary_module}\\n"
        f"- issue_summary: {improvement.issue_summary}\\n"
        f"- priority: {improvement.training_priority.value}\\n"
    )

    operations = [
        IterationOperation(
            operation="append_yaml_rule",
            file_path=str(rule_file),
            detail={"bucket_key": bucket_key, "rule_id": auto_rule["id"]},
            status="planned" if dry_run else "applied",
        ),
        IterationOperation(
            operation="append_jsonl",
            file_path=str(regression_file),
            detail={"sample_id": improvement.sample_id},
            status="planned" if dry_run else "applied",
        ),
        IterationOperation(
            operation="append_markdown",
            file_path=str(log_file),
            detail={"sample_id": improvement.sample_id},
            status="planned" if dry_run else "applied",
        ),
    ]

    touched_files = [str(rule_file), str(regression_file), str(log_file)]

    if not dry_run:
        append_yaml_rule(rule_file, bucket_key, auto_rule)
        append_jsonl(regression_file, regression_case)
        append_markdown(log_file, log_entry)

    return IterationExecutionResult(
        sample_id=improvement.sample_id,
        target_skill_path=str(target_root),
        primary_module=primary_module,
        applied=not dry_run,
        operations=operations,
        touched_files=touched_files,
        trace={
            "source": "verify-agent-self-improve",
            "second_routing_reason": second.second_routing_reason,
            "suspected_modules": improvement.suspected_modules,
        },
    )
