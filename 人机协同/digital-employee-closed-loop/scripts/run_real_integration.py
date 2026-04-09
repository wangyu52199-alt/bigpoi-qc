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


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run real integration (closed-loop pipeline)")
    parser.add_argument(
        "--manual-input",
        default=str(repo_root / "shared" / "examples" / "sample_03_both_issue.json"),
        help="Path to manual result JSON",
    )
    parser.add_argument(
        "--targets-config",
        default=str(repo_root / "integrations" / "targets.yaml"),
        help="Path to targets YAML",
    )
    parser.add_argument(
        "--output",
        default=str(repo_root / "integration-output" / "last_integration_result.json"),
        help="Path to output JSON",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not apply writes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    pipeline_module = _load_module(
        "closed_loop_pipeline",
        repo_root / "scripts" / "run_closed_loop_pipeline.py",
    )

    manual_payload = _load_json(args.manual_input)
    targets_cfg = _load_yaml(args.targets_config)
    summary = pipeline_module.run_pipeline(
        manual_payload=manual_payload,
        targets_cfg=targets_cfg,
        repo_root=repo_root,
        dry_run=args.dry_run,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] integration finished: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
