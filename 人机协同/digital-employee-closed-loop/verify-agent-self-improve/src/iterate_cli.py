from __future__ import annotations

import argparse
import json
from pathlib import Path

from iter_engine import run_verify_auto_iteration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run verify auto iteration (merged in verify-agent-self-improve)")
    parser.add_argument("--improvement-input", required=True)
    parser.add_argument("--second-routing-input", required=True)
    parser.add_argument("--target-skill-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "config" / "auto_iteration_config.yaml"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    improvement_payload = json.loads(Path(args.improvement_input).read_text(encoding="utf-8"))
    second_payload = json.loads(Path(args.second_routing_input).read_text(encoding="utf-8"))

    result = run_verify_auto_iteration(
        improvement_payload=improvement_payload,
        second_routing_payload=second_payload,
        target_skill_path=args.target_skill_path,
        config_path=args.config,
        dry_run=args.dry_run,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"[OK] verify auto iteration result saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
