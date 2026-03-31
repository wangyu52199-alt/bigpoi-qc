#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hybrid adjudication runner.

用途：
1. 读取规则初判结果（包含 dimension_results）
2. 读取模型裁决 DSL（qc_model_judgement）
3. 按 hybrid_policy 执行可控覆盖
4. 统一走 finalize_qc_result 收敛最终结果
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema
except Exception:  # pragma: no cover - optional dependency
    jsonschema = None

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from result_contract import finalize_qc_result  # noqa: E402


def _read_json(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def _write_json(payload: dict, path: str = None) -> None:
    if path:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _validate_model_judgement(model_judgement: dict, schema_path: str = None) -> list:
    if not schema_path:
        return []
    schema_file = Path(schema_path)
    if not schema_file.exists():
        return [f'model judgement schema 不存在：{schema_file}']
    if jsonschema is None:
        return ['jsonschema 未安装，跳过 model judgement schema 校验']
    try:
        schema = _read_json(str(schema_file))
        jsonschema.validate(instance=model_judgement, schema=schema)
        return []
    except Exception as exc:
        return [f'model judgement schema 校验失败：{exc}']


def main() -> int:
    parser = argparse.ArgumentParser(description='执行规则 + 模型裁决的 hybrid finalize')
    parser.add_argument('--input', required=True, help='规则初判结果 JSON')
    parser.add_argument('--model-judgement', required=True, help='模型裁决 DSL JSON')
    parser.add_argument('--output', default=None, help='输出文件路径；不传则 stdout')
    parser.add_argument(
        '--judgement-schema',
        default=str(SCRIPT_DIR.parent / 'schema' / 'qc_model_judgement.schema.json'),
        help='模型裁决 DSL schema 路径',
    )
    parser.add_argument(
        '--scoring-policy',
        default=None,
        help='评分策略路径；不传时使用默认 config/scoring_policy.json',
    )
    parser.add_argument(
        '--hybrid-policy',
        default=None,
        help='hybrid 策略路径；不传时使用默认 config/hybrid_policy.json',
    )
    parser.add_argument(
        '--poi-type',
        default=None,
        help='可选：输入 poi_type，用于类型语义回退注入',
    )
    args = parser.parse_args()

    qc_payload = _read_json(args.input)
    model_judgement = _read_json(args.model_judgement)

    validation_errors = _validate_model_judgement(model_judgement, args.judgement_schema)
    if validation_errors and any('校验失败' in item for item in validation_errors):
        for message in validation_errors:
            print(message, file=sys.stderr)
        return 2
    for message in validation_errors:
        print(message, file=sys.stderr)

    finalized = finalize_qc_result(
        qc_payload,
        scoring_policy_path=args.scoring_policy,
        poi_type_hint=args.poi_type,
        model_judgement=model_judgement,
        hybrid_policy_path=args.hybrid_policy,
    )
    _write_json(finalized, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
