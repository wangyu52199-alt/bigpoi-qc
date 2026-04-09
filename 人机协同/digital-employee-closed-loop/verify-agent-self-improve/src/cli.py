from __future__ import annotations

import argparse
import json
from pathlib import Path

from improver import build_verify_improvement_record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build verify agent improvement record")
    parser.add_argument("--manual-input", required=True)
    parser.add_argument("--first-routing-input", required=True)
    parser.add_argument("--second-routing-input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manual_payload = json.loads(Path(args.manual_input).read_text(encoding="utf-8"))
    first_payload = json.loads(Path(args.first_routing_input).read_text(encoding="utf-8"))
    second_payload = json.loads(Path(args.second_routing_input).read_text(encoding="utf-8"))

    result = build_verify_improvement_record(manual_payload, first_payload, second_payload)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"[OK] verify improvement record saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
