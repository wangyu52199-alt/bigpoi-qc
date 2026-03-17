#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POI 类型映射与中文类目回退匹配。

用途：
1. 将内部 poi_type 解析为白名单类型 key
2. 在证据缺少 typecode 时，使用中文 category_aliases 做确定性回退匹配
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR.parent / 'config' / 'poi_type_mapping.json'


def load_mapping(config_path: Optional[str] = None) -> Dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def resolve_mapping_entry(poi_type: Any, mapping: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    poi_type_str = str(poi_type or '').strip()
    if not poi_type_str:
        return None

    mappings = mapping.get('mappings', {})
    for key, entry in mappings.items():
        type_codes = entry.get('type_codes', [])
        exact_codes = [code for code in type_codes if poi_type_str == str(code)]
        if exact_codes:
            return {'category_key': key, 'matched_code': exact_codes[0], 'match_mode': 'exact', 'entry': entry}

    for key, entry in mappings.items():
        type_codes = entry.get('type_codes', [])
        for code in type_codes:
            code_str = str(code)
            if poi_type_str.startswith(code_str):
                return {'category_key': key, 'matched_code': code_str, 'match_mode': 'prefix', 'entry': entry}
    return None


def match_category_text(poi_type: Any, evidence_category: Any, mapping: Dict[str, Any]) -> Dict[str, Any]:
    evidence_category_str = str(evidence_category or '').strip()
    resolved = resolve_mapping_entry(poi_type, mapping)
    if not resolved:
        return {
            'matched': False,
            'support_level': 'none',
            'reason': 'poi_type_unmapped',
        }

    if not evidence_category_str:
        return {
            'matched': False,
            'support_level': 'none',
            'reason': 'empty_evidence_category',
            'category_key': resolved['category_key'],
        }

    aliases = resolved['entry'].get('category_aliases', [])
    matched_aliases = [alias for alias in aliases if alias and alias in evidence_category_str]
    matched = len(matched_aliases) > 0
    return {
        'matched': matched,
        'support_level': 'weak' if matched else 'none',
        'reason': 'category_alias_match' if matched else 'category_alias_miss',
        'category_key': resolved['category_key'],
        'matched_code': resolved['matched_code'],
        'type_match_mode': resolved['match_mode'],
        'matched_aliases': matched_aliases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Resolve poi_type and match evidence category text.')
    parser.add_argument('--poi-type', required=True, help='内部 poi_type')
    parser.add_argument('--evidence-category', help='证据 category 中文文本')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG_PATH), help='映射配置路径')
    args = parser.parse_args()

    mapping = load_mapping(args.config)
    resolved = resolve_mapping_entry(args.poi_type, mapping)
    category_match = match_category_text(args.poi_type, args.evidence_category, mapping)

    print(
        json.dumps(
            {
                'poi_type': args.poi_type,
                'resolved_mapping': resolved,
                'category_text_match': category_match,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
