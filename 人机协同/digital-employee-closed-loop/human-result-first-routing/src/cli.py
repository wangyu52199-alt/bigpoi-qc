from __future__ import annotations

import argparse
import json
from pathlib import Path

from router import FirstRoutingEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run first routing")
    parser.add_argument("--input", required=True, help="Path to manual result JSON")
    parser.add_argument("--output", required=True, help="Path to first routing result JSON")
    parser.add_argument(
        "--rules",
        default=str(Path(__file__).resolve().parents[1] / "config" / "first_routing_rules.yaml"),
        help="Path to routing rule YAML",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    engine = FirstRoutingEngine(args.rules)
    result = engine.route(payload)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"[OK] first routing result saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
