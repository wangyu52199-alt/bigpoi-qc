from __future__ import annotations

import argparse
import json
from pathlib import Path

from router import SecondRoutingEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run second routing")
    parser.add_argument("--manual-input", required=True, help="Path to manual input JSON")
    parser.add_argument("--first-routing-input", required=True, help="Path to first routing result JSON")
    parser.add_argument("--output", required=True, help="Path to second routing result JSON")
    parser.add_argument(
        "--rules",
        default=str(Path(__file__).resolve().parents[1] / "config" / "second_routing_rules.yaml"),
        help="Path to second routing rule YAML",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manual_payload = json.loads(Path(args.manual_input).read_text(encoding="utf-8"))
    first_payload = json.loads(Path(args.first_routing_input).read_text(encoding="utf-8"))

    engine = SecondRoutingEngine(args.rules)
    result = engine.route(manual_payload, first_payload)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"[OK] second routing result saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
