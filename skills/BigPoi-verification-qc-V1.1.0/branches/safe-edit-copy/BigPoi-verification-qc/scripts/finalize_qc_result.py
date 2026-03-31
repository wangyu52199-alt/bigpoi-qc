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


def _read_optional_json(path: str = None) -> dict:
    if not path:
        return None
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


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
    parser.add_argument(
        '--poi-type',
        default=None,
        help='可选：输入 poi_type，用于在缺失 typecode 时自动补齐 category_fallback_support',
    )
    parser.add_argument(
        '--model-judgement',
        default=None,
        help='可选：模型维度裁决 DSL JSON 文件路径',
    )
    parser.add_argument(
        '--hybrid-policy',
        default=None,
        help='可选：hybrid 裁决策略路径；不传时使用默认 config/hybrid_policy.json',
    )
    parser.add_argument(
        '--raw-input',
        default=None,
        help='可选：平铺原始输入 JSON；用于在 finalize 前强制重算核心维度',
    )
    parser.add_argument(
        '--no-recompute-core',
        action='store_true',
        help='禁用核心维度重算（默认启用）',
    )
    parser.add_argument(
        '--dsl',
        default=None,
        help='可选：decision_tables.json 路径；用于核心维度重算',
    )
    parser.add_argument(
        '--no-preprocess-evidence',
        action='store_true',
        help='核心维度重算时跳过证据预处理（默认执行预处理）',
    )
    args = parser.parse_args()

    payload = _read_payload(args.input)
    model_judgement = _read_optional_json(args.model_judgement)
    raw_input = _read_optional_json(args.raw_input)
    finalized = finalize_qc_result(
        payload,
        scoring_policy_path=args.scoring_policy,
        poi_type_hint=args.poi_type,
        model_judgement=model_judgement,
        hybrid_policy_path=args.hybrid_policy,
        raw_input=raw_input,
        recompute_core=not args.no_recompute_core,
        dsl_path=args.dsl,
        preprocess_evidence=not args.no_preprocess_evidence,
    )
    _write_payload(finalized, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
