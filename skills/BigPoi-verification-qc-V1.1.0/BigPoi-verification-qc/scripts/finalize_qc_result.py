#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终质检结果组装脚本。

输入：包含 task_id、dimension_results、explanation 等维度级结果的 qc_result 草稿
输出：补齐 qc_status、qc_score、risk_dims、triggered_rules、statistics_flags 的完整 qc_result
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from result_contract import finalize_qc_result  # noqa: E402


def _read_payload(input_path: str = None) -> dict:
    if input_path:
        with open(input_path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    return json.load(sys.stdin)


def _write_payload(payload: dict, output_path: str = None) -> None:
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description='组装 BigPOI QC 的派生结果字段')
    parser.add_argument('--input', help='输入 JSON 文件路径；不传时从 stdin 读取')
    parser.add_argument('--output', help='输出 JSON 文件路径；不传时输出到 stdout')
    parser.add_argument(
        '--scoring-policy',
        default=None,
        help='评分策略路径；不传时使用默认 config/scoring_policy.json',
    )
    args = parser.parse_args()

    payload = _read_payload(args.input)
    finalized = finalize_qc_result(payload, scoring_policy_path=args.scoring_policy)
    _write_payload(finalized, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
