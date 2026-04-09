#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POI 类型映射与中文类目回退匹配。

用途：
1. 将内部 poi_type 解析为白名单类型 group
2. 尝试解析对应的层级/子类语义（如省/市/区县级政府）
3. 在证据缺少 typecode 时，使用中文 category_aliases 做确定性回退匹配
"""

import argparse
import json
import re
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
        code_definitions = entry.get('code_definitions', {})
        if poi_type_str in code_definitions:
            code_entry = code_definitions[poi_type_str]
            return {
                'group_key': key,
                'group_label_zh': entry.get('group_label_zh', key),
                'matched_code': poi_type_str,
                'match_mode': 'exact',
                'level': code_entry.get('level'),
                'label_zh': code_entry.get('label_zh'),
                'aliases': code_entry.get('aliases', []),
                'entry': entry,
                'code_entry': code_entry,
            }

    for key, entry in mappings.items():
        type_codes = entry.get('type_codes', [])
        exact_codes = [code for code in type_codes if poi_type_str == str(code)]
        if exact_codes:
            return {
                'group_key': key,
                'group_label_zh': entry.get('group_label_zh', key),
                'matched_code': exact_codes[0],
                'match_mode': 'exact',
                'level': None,
                'label_zh': entry.get('group_label_zh', key),
                'aliases': entry.get('group_aliases', entry.get('category_aliases', [])),
                'entry': entry,
                'code_entry': None,
            }

    for key, entry in mappings.items():
        prefix_codes = entry.get('prefix_codes', [])
        for code in prefix_codes:
            code_str = str(code)
            if poi_type_str.startswith(code_str):
                return {
                    'group_key': key,
                    'group_label_zh': entry.get('group_label_zh', key),
                    'matched_code': code_str,
                    'match_mode': 'prefix',
                    'level': None,
                    'label_zh': entry.get('group_label_zh', key),
                    'aliases': entry.get('group_aliases', entry.get('category_aliases', [])),
                    'entry': entry,
                    'code_entry': None,
                }

    for key, entry in mappings.items():
        type_codes = entry.get('type_codes', [])
        for code in type_codes:
            code_str = str(code)
            if poi_type_str.startswith(code_str):
                return {
                    'group_key': key,
                    'group_label_zh': entry.get('group_label_zh', key),
                    'matched_code': code_str,
                    'match_mode': 'prefix',
                    'level': None,
                    'label_zh': entry.get('group_label_zh', key),
                    'aliases': entry.get('group_aliases', entry.get('category_aliases', [])),
                    'entry': entry,
                    'code_entry': None,
                }
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
            'group_key': resolved['group_key'],
        }

    group_aliases = resolved['entry'].get('group_aliases', resolved['entry'].get('category_aliases', []))
    specific_aliases = resolved.get('aliases', [])
    group_matches = [alias for alias in group_aliases if alias and alias in evidence_category_str]
    specific_matches = [alias for alias in specific_aliases if alias and alias in evidence_category_str]
    if resolved.get('label_zh') and resolved['label_zh'] in evidence_category_str:
        specific_matches.append(resolved['label_zh'])

    group_matched = len(group_matches) > 0
    level_matched = len(specific_matches) > 0
    matched = group_matched or level_matched
    return {
        'matched': matched,
        'support_level': 'medium' if level_matched else ('weak' if group_matched else 'none'),
        'reason': 'category_level_alias_match' if level_matched else ('category_group_alias_match' if group_matched else 'category_alias_miss'),
        'group_key': resolved['group_key'],
        'group_label_zh': resolved.get('group_label_zh'),
        'matched_code': resolved['matched_code'],
        'type_match_mode': resolved['match_mode'],
        'resolved_level': resolved.get('level'),
        'resolved_label_zh': resolved.get('label_zh'),
        'group_matched': group_matched,
        'level_matched': level_matched,
        'matched_group_aliases': group_matches,
        'matched_level_aliases': specific_matches,
    }


def extract_name_semantics(evidence_name: Any) -> Dict[str, Any]:
    name = str(evidence_name or '').strip()
    if not name:
        return {
            'matched': False,
            'reason': 'empty_evidence_name',
        }

    direct_municipality_pattern = re.compile(r'^(北京市|上海市|天津市|重庆市)人民政府$')
    province_pattern = re.compile(r'.*(省人民政府|自治区人民政府|特别行政区政府)$')
    city_pattern = re.compile(r'.*(市人民政府|州人民政府|地区行政公署)$')
    county_pattern = re.compile(r'.*(县人民政府|区人民政府)$')
    town_pattern = re.compile(r'.*(乡人民政府|镇人民政府)$')

    if direct_municipality_pattern.match(name):
        return {
            'matched': True,
            'group_key': 'government',
            'level': 'province',
            'reason': 'direct_municipality_government_name',
            'matched_pattern': direct_municipality_pattern.pattern,
        }
    if province_pattern.match(name):
        return {
            'matched': True,
            'group_key': 'government',
            'level': 'province',
            'reason': 'province_government_name',
            'matched_pattern': province_pattern.pattern,
        }
    if city_pattern.match(name):
        return {
            'matched': True,
            'group_key': 'government',
            'level': 'city',
            'reason': 'city_government_name',
            'matched_pattern': city_pattern.pattern,
        }
    if county_pattern.match(name):
        return {
            'matched': True,
            'group_key': 'government',
            'level': 'county',
            'reason': 'county_government_name',
            'matched_pattern': county_pattern.pattern,
        }
    if town_pattern.match(name):
        return {
            'matched': True,
            'group_key': 'government',
            'level': 'town',
            'reason': 'town_government_name',
            'matched_pattern': town_pattern.pattern,
        }

    return {
        'matched': False,
        'reason': 'no_name_semantics_match',
    }


def match_name_semantics(poi_type: Any, evidence_name: Any, mapping: Dict[str, Any]) -> Dict[str, Any]:
    resolved = resolve_mapping_entry(poi_type, mapping)
    if not resolved:
        return {
            'matched': False,
            'support_level': 'none',
            'reason': 'poi_type_unmapped',
        }

    extracted = extract_name_semantics(evidence_name)
    if not extracted.get('matched'):
        return {
            'matched': False,
            'support_level': 'none',
            'reason': extracted.get('reason', 'no_name_semantics_match'),
            'group_key': resolved['group_key'],
            'resolved_level': resolved.get('level'),
        }

    group_matched = extracted.get('group_key') == resolved.get('group_key')
    level_matched = extracted.get('level') == resolved.get('level') and extracted.get('level') is not None
    matched = group_matched or level_matched
    return {
        'matched': matched,
        'support_level': 'medium' if level_matched else ('weak' if group_matched else 'none'),
        'reason': 'name_level_match' if level_matched else ('name_group_match' if group_matched else 'name_group_miss'),
        'group_key': resolved.get('group_key'),
        'group_label_zh': resolved.get('group_label_zh'),
        'resolved_level': resolved.get('level'),
        'resolved_label_zh': resolved.get('label_zh'),
        'name_group_key': extracted.get('group_key'),
        'name_level': extracted.get('level'),
        'matched_pattern': extracted.get('matched_pattern'),
    }


def evaluate_fallback_support(poi_type: Any, evidence_category: Any, evidence_name: Any, mapping: Dict[str, Any]) -> Dict[str, Any]:
    category_match = match_category_text(poi_type, evidence_category, mapping)
    name_match = match_name_semantics(poi_type, evidence_name, mapping)

    category_level = category_match.get('level_matched', False)
    name_level = name_match.get('reason') == 'name_level_match'
    category_group = category_match.get('group_matched', False)
    name_group = name_match.get('reason') in {'name_level_match', 'name_group_match'}

    if category_level and name_level:
        support_level = 'strong'
        reason = 'category_and_name_level_match'
    elif name_level and category_group:
        support_level = 'strong'
        reason = 'name_level_plus_category_group_match'
    elif category_level or name_level:
        support_level = 'medium'
        reason = 'single_level_match'
    elif category_group or name_group:
        support_level = 'weak'
        reason = 'group_only_match'
    else:
        support_level = 'none'
        reason = 'no_fallback_match'

    return {
        'support_level': support_level,
        'reason': reason,
        'category_text_match': category_match,
        'name_semantics_match': name_match,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Resolve poi_type and match evidence category text/name semantics.')
    parser.add_argument('--poi-type', required=True, help='内部 poi_type')
    parser.add_argument('--evidence-category', help='证据 category 中文文本')
    parser.add_argument('--evidence-name', help='证据 name 名称文本')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG_PATH), help='映射配置路径')
    args = parser.parse_args()

    mapping = load_mapping(args.config)
    resolved = resolve_mapping_entry(args.poi_type, mapping)
    category_match = match_category_text(args.poi_type, args.evidence_category, mapping)
    name_match = match_name_semantics(args.poi_type, args.evidence_name, mapping)
    fallback_support = evaluate_fallback_support(args.poi_type, args.evidence_category, args.evidence_name, mapping)

    print(
        json.dumps(
            {
                'poi_type': args.poi_type,
                'resolved_mapping': resolved,
                'category_text_match': category_match,
                'name_semantics_match': name_match,
                'fallback_support': fallback_support,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
