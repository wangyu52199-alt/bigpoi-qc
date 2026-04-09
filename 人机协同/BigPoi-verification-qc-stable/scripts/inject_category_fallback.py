#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为平铺输入 evidence_record 自动补齐 category_fallback_support。

适用场景：
1. 输入是平铺格式（包含 poi_type + evidence_record）
2. 证据缺少 typecode，需要通过中文 category/name 语义回退参与类型判定
"""

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from poi_type_mapping import DEFAULT_CONFIG_PATH, evaluate_fallback_support, load_mapping


FALLBACK_SUPPORT_LEVELS = {'strong', 'medium', 'weak', 'none', 'conflict'}


def _read_payload(input_path: Optional[str]) -> Dict[str, Any]:
    if input_path:
        with open(input_path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    return json.load(sys.stdin)


def _write_payload(payload: Dict[str, Any], output_path: Optional[str]) -> None:
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _extract_typecode(data: Dict[str, Any]) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    raw_data = data.get('raw_data')
    if not isinstance(raw_data, dict):
        return None
    nested = raw_data.get('data')
    if isinstance(nested, dict) and nested.get('typecode') is not None:
        value = str(nested.get('typecode')).strip()
        return value or None
    if raw_data.get('typecode') is not None:
        value = str(raw_data.get('typecode')).strip()
        return value or None
    return None


def _normalize_support_level(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in FALLBACK_SUPPORT_LEVELS:
        return normalized
    return None


def enrich_payload(payload: Dict[str, Any], mapping: Dict[str, Any]) -> Dict[str, Any]:
    enriched = copy.deepcopy(payload)
    poi_type = str(enriched.get('poi_type') or '').strip()
    evidence_record = enriched.get('evidence_record')

    if not poi_type or not isinstance(evidence_record, list):
        return enriched

    for evidence in evidence_record:
        if not isinstance(evidence, dict):
            continue
        data = evidence.get('data')
        if not isinstance(data, dict):
            continue
        if _extract_typecode(data) is not None:
            continue

        matching = evidence.get('matching')
        if not isinstance(matching, dict):
            matching = {}

        current = _normalize_support_level(matching.get('category_fallback_support'))
        if current is not None:
            matching['category_fallback_support'] = current
            evidence['matching'] = matching
            continue

        fallback = evaluate_fallback_support(
            poi_type,
            data.get('category'),
            data.get('name'),
            mapping,
        )
        support_level = _normalize_support_level((fallback or {}).get('support_level')) or 'none'
        matching['category_fallback_support'] = support_level
        evidence['matching'] = matching

    return enriched


def main() -> int:
    parser = argparse.ArgumentParser(
        description='在平铺输入 evidence_record 中自动补齐 matching.category_fallback_support'
    )
    parser.add_argument('--input', help='输入 JSON 文件路径；不传时从 stdin 读取')
    parser.add_argument('--output', help='输出 JSON 文件路径；不传时输出到 stdout')
    parser.add_argument(
        '--config',
        default=str(DEFAULT_CONFIG_PATH),
        help='poi_type 映射配置路径（默认：config/poi_type_mapping.json）',
    )
    args = parser.parse_args()

    payload = _read_payload(args.input)
    mapping = load_mapping(args.config)
    enriched = enrich_payload(payload, mapping)
    _write_payload(enriched, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
