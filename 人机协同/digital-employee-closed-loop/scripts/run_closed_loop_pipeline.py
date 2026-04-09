#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import yaml


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_yaml(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _build_target_first_payload(first_payload: dict[str, Any], target: str) -> dict[str, Any]:
    first_target = str(first_payload.get("first_routing_target", ""))
    if first_target != "both":
        return first_payload

    payload = dict(first_payload)
    payload["first_routing_target"] = target
    reason = str(first_payload.get("first_routing_reason", ""))
    payload["first_routing_reason"] = f"{reason}；both 场景按 {target} 子链路执行"
    return payload


def _resolve_targets(first_target: str) -> list[str]:
    if first_target == "verify_agent":
        return ["verify_agent"]
    if first_target == "qc_agent":
        return ["qc_agent"]
    return ["verify_agent", "qc_agent"]


def run_pipeline(
    manual_payload: dict[str, Any],
    targets_cfg: dict[str, Any],
    repo_root: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    first_router_module = _load_module(
        "first_router",
        repo_root / "human-result-first-routing" / "src" / "router.py",
    )
    second_router_module = _load_module(
        "second_router",
        repo_root / "human-result-second-routing" / "src" / "router.py",
    )
    verify_improver_module = _load_module(
        "verify_improver",
        repo_root / "verify-agent-self-improve" / "src" / "improver.py",
    )
    qc_improver_module = _load_module(
        "qc_improver",
        repo_root / "qc-agent-self-improve" / "src" / "improver.py",
    )
    verify_iter_module = _load_module(
        "verify_iter",
        repo_root / "verify-agent-self-improve" / "src" / "iter_engine.py",
    )
    qc_iter_module = _load_module(
        "qc_iter",
        repo_root / "qc-agent-self-improve" / "src" / "iter_engine.py",
    )

    first_engine = first_router_module.FirstRoutingEngine(
        repo_root / "human-result-first-routing" / "config" / "first_routing_rules.yaml"
    )
    second_engine = second_router_module.SecondRoutingEngine(
        repo_root / "human-result-second-routing" / "config" / "second_routing_rules.yaml"
    )

    first_result_obj = first_engine.route(manual_payload)
    first_result = first_result_obj.model_dump(mode="json")
    first_target = str(first_result["first_routing_target"])

    sample_id = str(first_result.get("sample_id") or manual_payload.get("sample_id") or "sample-unknown")
    resolved_targets = _resolve_targets(first_target)

    per_target_outputs: dict[str, Any] = {}

    for target in resolved_targets:
        if target == "verify_agent":
            cfg = targets_cfg["verify_target"]
            first_for_target = _build_target_first_payload(first_result, "verify_agent")
            second_obj = second_engine.route(manual_payload, first_for_target)
            second_payload = second_obj.model_dump(mode="json")
            improvement_obj = verify_improver_module.build_verify_improvement_record(
                manual_payload,
                first_for_target,
                second_payload,
            )
            improvement_payload = improvement_obj.model_dump(mode="json")
            iter_result = verify_iter_module.run_verify_auto_iteration(
                improvement_payload=improvement_payload,
                second_routing_payload=second_payload,
                target_skill_path=cfg["skill_path"],
                config_path=cfg["config_path"],
                dry_run=dry_run,
            )
            per_target_outputs[target] = {
                "second_routing_result": second_payload,
                "improvement_record": improvement_payload,
                "iteration_result": iter_result.model_dump(mode="json"),
            }
            continue

        cfg = targets_cfg["qc_target"]
        first_for_target = _build_target_first_payload(first_result, "qc_agent")
        second_obj = second_engine.route(manual_payload, first_for_target)
        second_payload = second_obj.model_dump(mode="json")
        improvement_obj = qc_improver_module.build_qc_improvement_record(
            manual_payload,
            first_for_target,
            second_payload,
        )
        improvement_payload = improvement_obj.model_dump(mode="json")
        iter_result = qc_iter_module.run_qc_auto_iteration(
            improvement_payload=improvement_payload,
            second_routing_payload=second_payload,
            target_skill_path=cfg["skill_path"],
            config_path=cfg["config_path"],
            dry_run=dry_run,
        )
        per_target_outputs[target] = {
            "second_routing_result": second_payload,
            "improvement_record": improvement_payload,
            "iteration_result": iter_result.model_dump(mode="json"),
        }

    return {
        "sample_id": sample_id,
        "dry_run": dry_run,
        "first_routing_result": first_result,
        "resolved_targets": resolved_targets,
        "per_target": per_target_outputs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run closed-loop pipeline once")
    parser.add_argument("--manual-input", required=True, help="Path to manual result JSON")
    parser.add_argument(
        "--targets-config",
        default=str(Path(__file__).resolve().parents[1] / "integrations" / "targets.yaml"),
        help="Path to integration target YAML",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "integration-output" / "closed_loop_last_run.json"),
        help="Path to output summary JSON",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not apply file writes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    manual_payload = _load_json(args.manual_input)
    targets_cfg = _load_yaml(args.targets_config)

    summary = run_pipeline(
        manual_payload=manual_payload,
        targets_cfg=targets_cfg,
        repo_root=repo_root,
        dry_run=args.dry_run,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] closed-loop pipeline finished: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
