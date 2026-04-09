from __future__ import annotations

import argparse
import json
from pathlib import Path

from validator import load_thresholds, validate_regression


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pre-release regression validation")
    parser.add_argument("--input", required=True, help="Path to regression input JSON")
    parser.add_argument("--output-json", required=True, help="Path to output regression JSON report")
    parser.add_argument("--output-md", required=True, help="Path to output regression markdown report")
    parser.add_argument(
        "--thresholds",
        default=str(Path(__file__).resolve().parents[1] / "config" / "regression_thresholds.yaml"),
        help="Path to threshold YAML",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    thresholds = load_thresholds(args.thresholds)

    report, markdown = validate_regression(payload, thresholds)

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    output_md.write_text(markdown, encoding="utf-8")

    print(f"[OK] json report saved: {output_json}")
    print(f"[OK] markdown report saved: {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
