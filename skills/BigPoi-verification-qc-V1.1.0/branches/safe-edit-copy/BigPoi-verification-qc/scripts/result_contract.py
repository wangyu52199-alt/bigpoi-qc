#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BigPOI 质检结果契约计算模块。

职责：
1. 统一派生字段的计算逻辑
2. 生成稳定的 triggered_rules
3. 将可反算字段从模型自由输出收敛为程序确定性输出
"""

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from poi_type_mapping import evaluate_fallback_support, load_mapping
except Exception:  # pragma: no cover - optional runtime dependency
    evaluate_fallback_support = None
    load_mapping = None


CORE_DIMENSIONS = (
    'existence',
    'name',
    'location',
    'address',
    'administrative',
    'category',
)
REVIEW_DIMENSIONS = ('evidence_sufficiency',)
ALL_DIMENSIONS = CORE_DIMENSIONS + REVIEW_DIMENSIONS + ('downgrade_consistency',)
RISK_STATUSES = {'risk', 'fail'}
AUTHORITATIVE_SOURCE_TYPES = {'business_license', 'official_registry', 'government', 'official_data'}
FALLBACK_SUPPORT_LEVELS = {'strong', 'medium', 'weak', 'none', 'conflict'}
_POI_TYPE_MAPPING_CACHE: Optional[Dict[str, Any]] = None
ADDRESS_ANCHOR_TOKENS = (
    '路',
    '街',
    '巷',
    '号',
    '国道',
    '省道',
    '县道',
    '大道',
    '道',
    '村',
    '社区',
    '开发区',
    '工业区',
    '交叉口',
)
ROAD_PATTERN = re.compile(r'([A-Za-z0-9\u4e00-\u9fff]{1,24}(?:路|街|巷|大道|国道|省道|县道|道))')
HOUSE_NUMBER_PATTERN = re.compile(r'(\d+)\s*号')
ROAD_CODE_PATTERN = re.compile(r'([gs]\d{2,4})')
CJK_CHAR_PATTERN = re.compile(r'[\u4e00-\u9fff]')
ASCII_ALPHA_PATTERN = re.compile(r'[A-Za-z]')
HYBRID_DEFAULT_POLICY = {
    'version': '1.0.0',
    'enabled': False,
    'allowed_dimensions': ['name', 'address', 'administrative', 'category'],
    'candidate_statuses': ['risk'],
    'allowed_transitions': ['risk->pass'],
    'min_confidence_default': 0.85,
    'min_confidence_by_dimension': {
        'name': 0.88,
        'address': 0.85,
        'administrative': 0.85,
        'category': 0.85,
    },
    'min_evidence_ids_by_dimension': {
        'name': 1,
        'address': 1,
        'administrative': 1,
        'category': 1,
    },
    'allow_override_when_hard_conflict': False,
    'hard_conflict_issue_codes': {
        'name': [
            'all_name_similarity_below_threshold',
        ],
        'address': [
            'address_direct_conflict',
        ],
        'administrative': [
            'administrative_direct_conflict',
        ],
        'category': [
            'typecode_conflict',
        ],
    },
    'allowed_reason_codes': {
        'name': [
            'NAME_ALIAS_MATCH',
            'NAME_PREFIX_SUFFIX_EQUIV',
        ],
        'address': [
            'ADDR_PREFIX_OR_ROADCODE_EQUIV',
            'ADDR_MAIN_ANCHOR_EQUIV',
        ],
        'administrative': [
            'ADMIN_CITY_INFERRED_SUPPORT',
        ],
        'category': [
            'CATEGORY_SEMANTIC_FALLBACK_STRONG',
            'CATEGORY_NAME_LEVEL_SUPPORT',
        ],
    },
    'hard_conflict_keywords': {
        'name': [
            '硬冲突',
            '完全不一致',
            '名称失败',
        ],
        'address': [
            '直接冲突',
            '门牌号不一致',
            '道路主干不一致',
            '城市级',
            '地址失败',
        ],
        'administrative': [
            '行政区划失败',
            '城市冲突',
            'city冲突',
        ],
        'category': [
            '类型失败',
            'typecode冲突',
            '类型冲突',
        ],
    },
    'reason_templates': {
        'NAME_ALIAS_MATCH': '名称别名/简称语义一致，主要实体未发生变化。',
        'NAME_PREFIX_SUFFIX_EQUIV': '名称仅存在行政层级前后缀差异，核心名称一致。',
        'ADDR_PREFIX_OR_ROADCODE_EQUIV': '地址仅存在行政前缀或道路编号表达差异，主锚点一致。',
        'ADDR_MAIN_ANCHOR_EQUIV': '地址主道路与门牌语义一致，附属后缀差异不影响同址判断。',
        'ADMIN_CITY_INFERRED_SUPPORT': '结构化 city 缺失时，地址/名称/原始字段可稳定支持输入 city。',
        'CATEGORY_SEMANTIC_FALLBACK_STRONG': '缺失 typecode 时，语义回退信号为 strong，支持类型通过。',
        'CATEGORY_NAME_LEVEL_SUPPORT': '类型大类与名称层级同时命中，可判定类型一致。',
    },
}

RULE_METADATA = {
    'R1': {
        'rule_name': '存在性一致性检查',
        'dimension': 'existence',
        'severity': 'high',
    },
    'R2': {
        'rule_name': '名称一致性检查',
        'dimension': 'name',
        'severity': 'high',
    },
    'R3': {
        'rule_name': '坐标一致性检查',
        'dimension': 'location',
        'severity': 'high',
    },
    'R4': {
        'rule_name': '地址一致性检查',
        'dimension': 'address',
        'severity': 'high',
    },
    'R5': {
        'rule_name': '行政区划一致性检查',
        'dimension': 'administrative',
        'severity': 'high',
    },
    'R6': {
        'rule_name': '类型一致性检查',
        'dimension': 'category',
        'severity': 'medium',
    },
    'R7': {
        'rule_name': '人工核实一致性检查',
        'dimension': 'downgrade_consistency',
        'severity': 'medium',
    },
    'R8': {
        'rule_name': '证据充分性检查',
        'dimension': 'evidence_sufficiency',
        'severity': 'medium',
    },
}
DEFAULT_RULE_BY_DIMENSION = {
    meta['dimension']: rule_id for rule_id, meta in RULE_METADATA.items()
}
DIMENSION_LABELS = {
    'existence': '存在性',
    'name': '名称',
    'location': '坐标',
    'address': '地址',
    'administrative': '行政区划',
    'category': '类型',
    'evidence_sufficiency': '证据充分性',
    'downgrade_consistency': '降级一致性',
}
QC_STATUS_LABELS = {
    'qualified': '通过',
    'risky': '有风险',
    'unqualified': '不通过',
}
DIMENSION_EXPLANATION_FALLBACKS = {
    'existence': {
        'pass': '存在性通过：存在性证据可稳定支撑该 POI 存在。',
        'risk': '存在性风险：存在性证据支撑不足，建议人工复核。',
        'fail': '存在性失败：缺少有效存在性证据或存在性冲突明显。',
    },
    'name': {
        'pass': '名称通过：名称证据与输入名称一致。',
        'risk': '名称风险：名称证据支撑不足或仅形成中等匹配。',
        'fail': '名称失败：名称证据与输入名称不一致。',
    },
    'location': {
        'pass': '坐标通过：坐标证据与输入坐标一致。',
        'risk': '坐标风险：坐标偏离处于风险区间，建议人工复核。',
        'fail': '坐标失败：坐标偏离明显或缺少有效坐标证据。',
    },
    'address': {
        'pass': '地址通过：地址证据与输入地址语义一致。',
        'risk': '地址风险：地址仅形成软匹配，需进一步核实。',
        'fail': '地址失败：地址存在直接冲突或缺少有效地址证据。',
    },
    'administrative': {
        'pass': '行政区划通过：行政区划证据支持输入城市一致。',
        'risk': '行政区划风险：行政区划证据不足，建议人工复核。',
        'fail': '行政区划失败：行政区划冲突或缺少有效城市证据。',
    },
    'category': {
        'pass': '类型通过：类型证据与输入类型一致。',
        'risk': '类型风险：类型证据仅形成中等支撑，建议人工复核。',
        'fail': '类型失败：类型冲突或缺少有效类型证据。',
    },
    'evidence_sufficiency': {
        'pass': '证据充分性通过：当前证据可支撑自动通过。',
        'risk': '证据充分性风险：事实维度虽可匹配，但证据支撑仍偏弱。',
        'fail': '证据充分性失败：缺少支撑自动通过的有效证据。',
    },
    'downgrade_consistency': {
        'pass': '降级一致性通过：QC 与上游对人工核实结论一致。',
        'risk': '降级一致性风险：QC 与上游人工核实信号存在不确定性。',
        'fail': '降级一致性失败：QC 与上游对人工核实结论不一致。',
    },
}


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def load_scoring_policy(scoring_policy_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if scoring_policy_path is None:
        scoring_policy_path = str(Path(__file__).resolve().parent.parent / 'config' / 'scoring_policy.json')
    return load_json(Path(scoring_policy_path))


def _deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def load_hybrid_policy(hybrid_policy_path: Optional[str] = None) -> Dict[str, Any]:
    policy = copy.deepcopy(HYBRID_DEFAULT_POLICY)
    if hybrid_policy_path is None:
        hybrid_policy_path = str(Path(__file__).resolve().parent.parent / 'config' / 'hybrid_policy.json')
    loaded = load_json(Path(hybrid_policy_path))
    if isinstance(loaded, dict):
        policy = _deep_update(policy, loaded)
    return policy


def _dimension_status(dimension_results: Dict[str, Any], dim_name: str) -> Optional[str]:
    dim_result = dimension_results.get(dim_name, {})
    if not isinstance(dim_result, dict):
        return None
    return _normalize_status_value(dim_result.get('status'))


def _normalize_status_value(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {'pass', 'risk', 'fail'}:
        return normalized
    return None


def _normalize_risk_level_value(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {'none', 'low', 'medium', 'high'}:
        return normalized
    return None


def _dedupe_evidence_items(evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique_items: List[Dict[str, Any]] = []
    seen = set()
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get('evidence_id')
        if evidence_id:
            key = ('evidence_id', str(evidence_id))
        else:
            key = (
                'payload',
                json.dumps(
                    {
                        'source': item.get('source', {}),
                        'data': item.get('data', {}),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(copy.deepcopy(item))
    return unique_items


def _evidence_confidence(evidence: Dict[str, Any]) -> float:
    verification = evidence.get('verification', {})
    if not isinstance(verification, dict):
        return 0.0
    confidence = verification.get('confidence')
    try:
        return max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        return 0.0


def _evidence_source_type(evidence: Dict[str, Any]) -> str:
    source = evidence.get('source', {})
    if not isinstance(source, dict):
        return ''
    return str(source.get('source_type') or '').strip()


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _copy_present(mapping: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            result[key] = copy.deepcopy(value)
    return result


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _extract_typecode(data: Dict[str, Any]) -> Optional[Any]:
    raw_data = data.get('raw_data')
    if not isinstance(raw_data, dict):
        return None
    nested_raw = raw_data.get('data')
    if isinstance(nested_raw, dict) and nested_raw.get('typecode') is not None:
        return nested_raw.get('typecode')
    return raw_data.get('typecode')


def _get_poi_type_mapping() -> Optional[Dict[str, Any]]:
    global _POI_TYPE_MAPPING_CACHE
    if _POI_TYPE_MAPPING_CACHE is not None:
        return _POI_TYPE_MAPPING_CACHE
    if load_mapping is None:
        return None
    try:
        _POI_TYPE_MAPPING_CACHE = load_mapping()
    except Exception:
        _POI_TYPE_MAPPING_CACHE = None
    return _POI_TYPE_MAPPING_CACHE


def _normalize_support_level(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in FALLBACK_SUPPORT_LEVELS:
        return normalized
    return None


def _inject_category_fallback_support(evidence: Dict[str, Any], poi_type_hint: Optional[str]) -> None:
    if not isinstance(evidence, dict):
        return
    if not poi_type_hint:
        return

    data = evidence.get('data')
    if not isinstance(data, dict):
        return
    if _extract_typecode(data) is not None:
        return

    matching = evidence.get('matching')
    if not isinstance(matching, dict):
        matching = {}

    existing_level = _normalize_support_level(matching.get('category_fallback_support'))
    if existing_level is not None:
        matching['category_fallback_support'] = existing_level
        evidence['matching'] = matching
        return

    if evaluate_fallback_support is None:
        matching['category_fallback_support'] = 'none'
        evidence['matching'] = matching
        return

    mapping = _get_poi_type_mapping()
    if not isinstance(mapping, dict):
        matching['category_fallback_support'] = 'none'
        evidence['matching'] = matching
        return

    fallback = evaluate_fallback_support(
        poi_type_hint,
        data.get('category'),
        data.get('name'),
        mapping,
    )
    support_level = _normalize_support_level((fallback or {}).get('support_level')) or 'none'
    matching['category_fallback_support'] = support_level
    evidence['matching'] = matching


def _build_location_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    location_payload: Dict[str, Any] = {}
    coordinates = data.get('coordinates')
    if isinstance(coordinates, dict):
        longitude = coordinates.get('longitude')
        latitude = coordinates.get('latitude')
        if longitude is not None:
            location_payload['longitude'] = longitude
        if latitude is not None:
            location_payload['latitude'] = latitude

    location = data.get('location')
    if isinstance(location, dict):
        longitude = _first_non_empty(location_payload.get('longitude'), location.get('longitude'))
        latitude = _first_non_empty(location_payload.get('latitude'), location.get('latitude'))
        address = _first_non_empty(location.get('address'), data.get('address'))
        if longitude is not None:
            location_payload['longitude'] = longitude
        if latitude is not None:
            location_payload['latitude'] = latitude
        if address is not None:
            location_payload['address'] = address
    else:
        address = data.get('address')
        if address is not None:
            location_payload['address'] = address

    return location_payload


def _project_evidence_item(
    dim_name: str,
    evidence: Dict[str, Any],
    poi_type_hint: Optional[str] = None,
) -> Dict[str, Any]:
    projected: Dict[str, Any] = {}
    if evidence.get('evidence_id') is not None:
        projected['evidence_id'] = evidence.get('evidence_id')
    if evidence.get('collected_at') is not None:
        projected['collected_at'] = evidence.get('collected_at')

    source = evidence.get('source')
    if isinstance(source, dict):
        projected_source = _copy_present(source, ['source_id', 'source_name', 'source_type', 'source_url', 'weight'])
        if projected_source:
            projected['source'] = projected_source

    verification = evidence.get('verification')
    if isinstance(verification, dict):
        projected_verification = _copy_present(verification, ['is_valid', 'confidence', 'validation_errors'])
        if projected_verification:
            projected['verification'] = projected_verification

    matching = evidence.get('matching')
    data = evidence.get('data')
    if dim_name == 'category':
        enriched = copy.deepcopy(evidence)
        _inject_category_fallback_support(enriched, poi_type_hint)
        matching = enriched.get('matching')
        data = enriched.get('data')
    if not isinstance(data, dict):
        data = {}

    if dim_name == 'existence':
        projected_data = _copy_present(
            data,
            ['name', 'address', 'existence'],
        )
    elif dim_name == 'name':
        projected_data = _copy_present(data, ['name'])
        if isinstance(matching, dict):
            projected_matching = _copy_present(matching, ['name_similarity'])
            if projected_matching:
                projected['matching'] = projected_matching
    elif dim_name == 'location':
        location_payload = _build_location_payload(data)
        projected_data = {'location': location_payload} if location_payload else {}
        if isinstance(matching, dict):
            projected_matching = _copy_present(matching, ['location_distance'])
            if projected_matching:
                projected['matching'] = projected_matching
    elif dim_name == 'address':
        address = _first_non_empty(data.get('address'), data.get('location', {}).get('address') if isinstance(data.get('location'), dict) else None)
        projected_data = {'address': address} if address is not None else {}
    elif dim_name == 'administrative':
        administrative = data.get('administrative')
        city = None
        if isinstance(administrative, dict):
            city = administrative.get('city')
        projected_data = {'administrative': {'city': city}} if city is not None else {}
        name = data.get('name')
        if name is not None:
            projected_data['name'] = name
        address = _first_non_empty(
            data.get('address'),
            data.get('location', {}).get('address') if isinstance(data.get('location'), dict) else None,
        )
        if address is not None:
            projected_data['address'] = address
    elif dim_name == 'category':
        projected_data = {}
        category = data.get('category')
        typecode = _extract_typecode(data)
        if category is not None:
            projected_data['category'] = category
        if typecode is not None:
            projected_data['raw_data'] = {'typecode': typecode}
        if isinstance(matching, dict):
            projected_matching = _copy_present(matching, ['category_match', 'category_fallback_support'])
            if projected_matching:
                projected['matching'] = projected_matching
    elif dim_name == 'evidence_sufficiency':
        projected_data = {}
    else:
        projected_data = copy.deepcopy(data)

    if projected_data:
        projected['data'] = projected_data

    return projected


def _build_evidence_index(evidence_record: Any) -> Dict[str, Dict[str, Any]]:
    evidence_index: Dict[str, Dict[str, Any]] = {}
    if not isinstance(evidence_record, list):
        return evidence_index
    for item in evidence_record:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get('evidence_id')
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            continue
        evidence_index[evidence_id.strip()] = copy.deepcopy(item)
    return evidence_index


def _is_reference_only_evidence(item: Dict[str, Any]) -> bool:
    for key in ('source', 'data', 'verification', 'matching'):
        value = item.get(key)
        if isinstance(value, dict) and value:
            return False
    keys = [key for key in item.keys() if key not in {'evidence_id', 'collected_at'}]
    if not keys:
        return True
    for key in keys:
        value = item.get(key)
        if value not in (None, '', [], {}):
            return False
    return True


def _project_dimension_evidence(
    dim_name: str,
    evidence_items: Any,
    poi_type_hint: Optional[str] = None,
    evidence_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(evidence_items, list):
        return []
    projected_items = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        effective_item = item
        if evidence_index and _is_reference_only_evidence(item):
            evidence_id = item.get('evidence_id')
            if isinstance(evidence_id, str):
                matched = evidence_index.get(evidence_id.strip())
                if isinstance(matched, dict):
                    effective_item = copy.deepcopy(matched)
                    if effective_item.get('evidence_id') is None:
                        effective_item['evidence_id'] = evidence_id
                    if item.get('collected_at') is not None and effective_item.get('collected_at') is None:
                        effective_item['collected_at'] = item.get('collected_at')

        projected_item = _project_evidence_item(dim_name, effective_item, poi_type_hint=poi_type_hint)
        if projected_item:
            projected_items.append(projected_item)
    return _dedupe_evidence_items(projected_items)


def _trim_explanation(text: Any) -> str:
    if not isinstance(text, str):
        return ''
    return ' '.join(text.strip().split())


def _is_non_chinese_explanation(text: str) -> bool:
    if not text:
        return True
    cjk_count = len(CJK_CHAR_PATTERN.findall(text))
    ascii_count = len(ASCII_ALPHA_PATTERN.findall(text))
    if cjk_count > 0:
        return False
    return ascii_count >= 4


def _fallback_explanation(dim_name: str, status: Optional[str], risk_level: Optional[str]) -> str:
    status_text = status if isinstance(status, str) else ''
    templates = DIMENSION_EXPLANATION_FALLBACKS.get(dim_name, {})
    message = templates.get(status_text)
    if message:
        return message
    label = DIMENSION_LABELS.get(dim_name, dim_name)
    if status_text == 'pass':
        return f'{label}通过：证据支持结论。'
    if status_text == 'risk':
        level = risk_level if isinstance(risk_level, str) and risk_level else 'medium'
        return f'{label}风险：当前结论存在{level}级风险，建议人工复核。'
    return f'{label}失败：当前证据不足或存在冲突。'


def _normalize_dimension_explanations(dimension_results: Dict[str, Any]) -> None:
    for dim_name in ALL_DIMENSIONS:
        dim_result = dimension_results.get(dim_name)
        if not isinstance(dim_result, dict):
            continue
        status = _normalize_status_value(dim_result.get('status'))
        if status is None:
            continue
        normalized = _trim_explanation(dim_result.get('explanation'))
        if normalized and not _is_non_chinese_explanation(normalized):
            dim_result['explanation'] = normalized
            continue
        dim_result['explanation'] = _fallback_explanation(
            dim_name,
            status,
            _normalize_risk_level_value(dim_result.get('risk_level')),
        )


def derive_overall_explanation(
    dimension_results: Dict[str, Any],
    qc_status: str,
    qc_score: int,
) -> str:
    parts: List[str] = [f"质检结果：{QC_STATUS_LABELS.get(qc_status, qc_status)}，得分 {qc_score} 分。"]

    passed_core = [DIMENSION_LABELS[dim] for dim in CORE_DIMENSIONS if _dimension_status(dimension_results, dim) == 'pass']
    if passed_core:
        parts.append(f"通过维度：{'、'.join(passed_core)}。")

    findings: List[str] = []
    for dim_name in ALL_DIMENSIONS:
        dim_result = dimension_results.get(dim_name, {})
        if not isinstance(dim_result, dict):
            continue
        status = dim_result.get('status')
        if status not in RISK_STATUSES:
            continue
        explanation = _trim_explanation(dim_result.get('explanation'))
        label = DIMENSION_LABELS.get(dim_name, dim_name)
        if explanation:
            findings.append(f"{label}{'失败' if status == 'fail' else '风险'}：{explanation}")
        else:
            findings.append(f"{label}{'失败' if status == 'fail' else '风险'}。")

    if findings:
        parts.extend(findings)
    elif len(passed_core) == len(CORE_DIMENSIONS):
        parts.append("核心事实维度全部通过。")

    return ' '.join(parts)


def _extract_location_distances(evidence_items: List[Dict[str, Any]]) -> List[float]:
    distances: List[float] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        matching = item.get('matching')
        if not isinstance(matching, dict):
            continue
        distance = _safe_float(matching.get('location_distance'))
        if distance is None:
            continue
        if distance < 0:
            continue
        distances.append(distance)
    return distances


def _extract_confidences(evidence_items: List[Dict[str, Any]]) -> List[float]:
    values: List[float] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        value = _evidence_confidence(item)
        if value > 0:
            values.append(value)
    return values


def _extract_addresses(evidence_items: List[Dict[str, Any]]) -> List[str]:
    addresses: List[str] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            continue
        address = data.get('address')
        if not isinstance(address, str) or not address.strip():
            continue
        addresses.append(address.strip())
    return addresses


def _normalize_address_for_compare(text: str) -> str:
    normalized = text.strip().lower()
    replacements = {
        '（': '(',
        '）': ')',
        '，': ',',
        '。': '.',
        '　': '',
        ' ': '',
    }
    for src, dst in replacements.items():
        normalized = normalized.replace(src, dst)
    for token in ('省', '市', '区', '县', '镇', '乡', '街道'):
        normalized = normalized.replace(token, '')
    normalized = normalized.replace('人民西路', '人民路')
    normalized = normalized.replace('国道', 'g')
    normalized = re.sub(r'g\s*(\d+)', r'g\1', normalized)
    normalized = re.sub(r'(\d+)g', r'g\1', normalized)
    normalized = normalized.replace('大道', '路')
    return normalized


def _is_low_information_address(address: str) -> bool:
    text = address.strip()
    if not text:
        return True
    if any(char.isdigit() for char in text):
        return False
    if any(token in text for token in ADDRESS_ANCHOR_TOKENS):
        return False
    normalized = _normalize_address_for_compare(text)
    return len(normalized) <= 6


def _extract_informative_addresses(evidence_items: List[Dict[str, Any]]) -> List[str]:
    informative: List[str] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            continue
        address = data.get('address')
        if not isinstance(address, str):
            continue
        address = address.strip()
        if not address or _is_low_information_address(address):
            continue
        informative.append(address)
    return informative


def _extract_informative_address_confidences(evidence_items: List[Dict[str, Any]]) -> List[float]:
    values: List[float] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            continue
        address = data.get('address')
        if not isinstance(address, str):
            continue
        address = address.strip()
        if not address or _is_low_information_address(address):
            continue
        confidence = _evidence_confidence(item)
        if confidence > 0:
            values.append(confidence)
    return values


def _are_two_addresses_semantically_consistent(base: str, candidate: str) -> bool:
    normalized_base = _normalize_address_for_compare(base)
    normalized_candidate = _normalize_address_for_compare(candidate)
    if not normalized_base or not normalized_candidate:
        return True
    if normalized_candidate == normalized_base:
        return True
    # 允许包含关系，兼容“完整地址 vs 简写地址”
    if normalized_candidate in normalized_base or normalized_base in normalized_candidate:
        return True
    base_road_code = _extract_road_code(base)
    candidate_road_code = _extract_road_code(candidate)
    if base_road_code and candidate_road_code and base_road_code == candidate_road_code:
        return True
    return False


def _extract_road_anchor(address: str) -> Optional[str]:
    match = ROAD_PATTERN.search(address)
    if not match:
        return None
    return match.group(1)


def _extract_house_number(address: str) -> Optional[str]:
    match = HOUSE_NUMBER_PATTERN.search(address)
    if not match:
        return None
    return match.group(1)


def _extract_road_code(address: str) -> Optional[str]:
    normalized = _normalize_address_for_compare(address)
    match = ROAD_CODE_PATTERN.search(normalized)
    if not match:
        return None
    return match.group(1)


def _describe_address_conflict(addresses: List[str]) -> str:
    if len(addresses) < 2:
        return '证据地址主锚点不一致，无法判定为同一地址。'
    base = addresses[0]
    for candidate in addresses[1:]:
        if _are_two_addresses_semantically_consistent(base, candidate):
            continue
        base_house = _extract_house_number(base)
        candidate_house = _extract_house_number(candidate)
        if base_house and candidate_house and base_house != candidate_house:
            return f'门牌号不一致（{base_house}号 vs {candidate_house}号）。冲突样例："{base}" vs "{candidate}"。'
        base_road = _extract_road_anchor(base)
        candidate_road = _extract_road_anchor(candidate)
        if base_road and candidate_road and _normalize_address_for_compare(base_road) != _normalize_address_for_compare(candidate_road):
            return f'道路主干不一致（{base_road} vs {candidate_road}）。冲突样例："{base}" vs "{candidate}"。'
        return f'主地址锚点不一致。冲突样例："{base}" vs "{candidate}"。'
    return '证据地址之间存在无法消解的语义冲突。'


def _are_addresses_semantically_consistent(addresses: List[str]) -> bool:
    if len(addresses) <= 1:
        return True
    base = addresses[0]
    for candidate in addresses[1:]:
        if _are_two_addresses_semantically_consistent(base, candidate):
            continue
        return False
    return True


def _apply_location_semantic_adjustment(dimension_results: Dict[str, Any]) -> None:
    dim_result = dimension_results.get('location')
    if not isinstance(dim_result, dict):
        return
    if dim_result.get('status') != 'risk':
        return

    evidence = dim_result.get('evidence')
    if not isinstance(evidence, list):
        return

    distances = _extract_location_distances(evidence)
    if len(distances) < 3:
        return

    close_count = sum(1 for distance in distances if distance <= 200)
    mid_count = sum(1 for distance in distances if 200 < distance <= 500)
    far_count = sum(1 for distance in distances if distance > 500)

    # 稳健规则：允许单个中距离离群点，不允许 >500m 的硬离群。
    if far_count > 0:
        return
    if close_count < 2 or mid_count != 1:
        return

    confidences = _extract_confidences(evidence)
    confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.85
    dim_result['status'] = 'pass'
    dim_result['risk_level'] = 'none'
    dim_result['confidence'] = max(confidence, 0.85)
    dim_result['explanation'] = (
        '坐标通过：检测到单个离群坐标证据，其余多数有效证据在 200 米内，按稳健规则判定坐标一致。'
    )


def _apply_address_semantic_adjustment(dimension_results: Dict[str, Any]) -> None:
    dim_result = dimension_results.get('address')
    if not isinstance(dim_result, dict):
        return
    if dim_result.get('status') != 'risk':
        return

    evidence = dim_result.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        return

    explanation = _trim_explanation(dim_result.get('explanation'))
    soft_risk_keywords = (
        '软匹配',
        '别名',
        '门牌缺失',
        '仅有单条精确匹配但置信度不足',
        '单条精确匹配但置信度不足',
        '主地址',
        '前缀',
    )
    if not any(keyword in explanation for keyword in soft_risk_keywords):
        return

    informative_confidences = _extract_informative_address_confidences(evidence)
    if not informative_confidences:
        dim_result['explanation'] = '地址风险：有效证据仅包含省市级或低信息地址，无法确认道路与门牌是否一致。'
        return
    confidences = informative_confidences
    max_confidence = max(confidences) if confidences else 0.0
    # 对“仅前缀差异（如省市区/镇街道）+ 主地址一致”场景放宽阈值，避免误判为风险。
    prefix_only_hints = ('主地址', '前缀', '省市区', '镇街道')
    required_confidence = 0.75 if any(hint in explanation for hint in prefix_only_hints) else 0.85
    if max_confidence < required_confidence:
        return

    addresses = _extract_informative_addresses(evidence)
    if not addresses:
        dim_result['explanation'] = '地址风险：有效证据仅包含省市级或低信息地址，无法确认道路与门牌是否一致。'
        return
    if not _are_addresses_semantically_consistent(addresses):
        dim_result['explanation'] = f"地址风险：{_describe_address_conflict(addresses)}"
        return

    dim_result['status'] = 'pass'
    dim_result['risk_level'] = 'none'
    dim_result['confidence'] = round(max(max_confidence, required_confidence), 4)
    if required_confidence < 0.85:
        dim_result['explanation'] = '地址通过：仅存在行政区/镇街道前缀差异，主地址语义一致，判定地址一致。'
    else:
        dim_result['explanation'] = '地址通过：软匹配证据语义一致，且存在高置信度支持，判定地址一致。'


def apply_semantic_adjustments(dimension_results: Dict[str, Any]) -> Dict[str, Any]:
    adjusted = copy.deepcopy(dimension_results)
    _apply_location_semantic_adjustment(adjusted)
    _apply_address_semantic_adjustment(adjusted)
    return adjusted


def _collect_supporting_evidence(dimension_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    supporting: List[Dict[str, Any]] = []
    for dim_name in CORE_DIMENSIONS:
        dim_result = dimension_results.get(dim_name, {})
        if not isinstance(dim_result, dict):
            continue
        if dim_result.get('status') != 'pass':
            continue
        evidence = dim_result.get('evidence')
        if isinstance(evidence, list):
            supporting.extend(item for item in evidence if isinstance(item, dict))

    if supporting:
        return _dedupe_evidence_items(supporting)

    fallback: List[Dict[str, Any]] = []
    for dim_name in CORE_DIMENSIONS:
        dim_result = dimension_results.get(dim_name, {})
        if not isinstance(dim_result, dict):
            continue
        evidence = dim_result.get('evidence')
        if isinstance(evidence, list):
            fallback.extend(item for item in evidence if isinstance(item, dict))
    return _dedupe_evidence_items(fallback)


def _derive_evidence_sufficiency(dimension_results: Dict[str, Any]) -> Dict[str, Any]:
    supporting_evidence = _collect_supporting_evidence(dimension_results)
    evidence_count = len(supporting_evidence)
    max_confidence = max((_evidence_confidence(item) for item in supporting_evidence), default=0.0)
    avg_confidence = (
        sum(_evidence_confidence(item) for item in supporting_evidence) / evidence_count
        if evidence_count > 0
        else 0.0
    )

    if evidence_count == 0:
        return {
            'status': 'fail',
            'risk_level': 'high',
            'explanation': '证据充分性失败：未找到足以支撑自动通过的有效支持证据。',
            'confidence': 0.0,
            'related_rules': ['R8'],
            'evidence': [],
        }

    if evidence_count >= 2:
        return {
            'status': 'pass',
            'risk_level': 'none',
            'explanation': '证据充分性通过：至少两条有效支持证据共同支撑最终结论，可支撑自动通过。',
            'confidence': round(avg_confidence, 4),
            'related_rules': ['R8'],
            'evidence': supporting_evidence,
        }

    only_evidence = supporting_evidence[0]
    only_source_type = _evidence_source_type(only_evidence)
    only_confidence = _evidence_confidence(only_evidence)
    if only_source_type in AUTHORITATIVE_SOURCE_TYPES and only_confidence >= 0.85:
        return {
            'status': 'pass',
            'risk_level': 'none',
            'explanation': '证据充分性通过：单条高权威高置信度证据已足以支撑自动通过。',
            'confidence': round(only_confidence, 4),
            'related_rules': ['R8'],
            'evidence': supporting_evidence,
        }

    risk_level = 'low' if only_source_type in AUTHORITATIVE_SOURCE_TYPES and only_confidence >= 0.75 else 'medium'
    return {
        'status': 'risk',
        'risk_level': risk_level,
        'explanation': '证据充分性风险：事实维度已匹配，但当前仅有一条有效支持证据，支撑不足以直接自动通过，建议人工复核。',
        'confidence': round(only_confidence, 4),
        'related_rules': ['R8'],
        'evidence': supporting_evidence,
    }


def derive_qc_manual_review_required(dimension_results: Dict[str, Any]) -> bool:
    if any(_dimension_status(dimension_results, dim_name) in RISK_STATUSES for dim_name in CORE_DIMENSIONS):
        return True
    return _dimension_status(dimension_results, 'evidence_sufficiency') in RISK_STATUSES


def derive_downgrade_issue_type(qc_manual_review_required: bool, upstream_manual_review_required: bool) -> str:
    if qc_manual_review_required == upstream_manual_review_required:
        return 'consistent'
    if qc_manual_review_required and not upstream_manual_review_required:
        return 'missed_downgrade'
    return 'unnecessary_downgrade'


def _default_downgrade_explanation(qc_manual: bool, upstream_manual: bool) -> str:
    if qc_manual == upstream_manual:
        return '降级一致性通过：QC 与上游对是否需要人工核实的判断一致。'
    if qc_manual and not upstream_manual:
        return '降级一致性失败：QC 认为需要人工核实，但上游未降级。'
    return '降级一致性失败：上游执行了人工核实，但 QC 认为无需人工核实。'


def _recompute_downgrade_consistency(dimension_results: Dict[str, Any]) -> None:
    consistency = dimension_results.get('downgrade_consistency')
    if not isinstance(consistency, dict):
        return

    qc_manual = derive_qc_manual_review_required(dimension_results)
    consistency['qc_manual_review_required'] = qc_manual

    upstream_manual_raw = consistency.get('upstream_manual_review_required')
    upstream_manual = upstream_manual_raw if isinstance(upstream_manual_raw, bool) else False
    consistency['upstream_manual_review_required'] = upstream_manual
    is_consistent = qc_manual == upstream_manual
    consistency['is_consistent'] = is_consistent
    consistency['issue_type'] = derive_downgrade_issue_type(qc_manual, upstream_manual)
    consistency['status'] = 'pass' if is_consistent else 'fail'
    consistency['risk_level'] = 'none' if is_consistent else 'high'
    consistency['explanation'] = _default_downgrade_explanation(qc_manual, upstream_manual)
    consistency['related_rules'] = ['R7']


def normalize_dimension_results(
    dimension_results: Dict[str, Any],
    poi_type_hint: Optional[Any] = None,
    evidence_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    normalized = copy.deepcopy(dimension_results or {})
    poi_type_text = str(poi_type_hint).strip() if poi_type_hint is not None else ''
    if not poi_type_text:
        poi_type_text = None

    normalized['evidence_sufficiency'] = _derive_evidence_sufficiency(normalized)

    for dim_name in ALL_DIMENSIONS:
        dim_result = normalized.get(dim_name)
        if not isinstance(dim_result, dict):
            continue

        default_rule_id = DEFAULT_RULE_BY_DIMENSION.get(dim_name)
        related_rules = dim_result.get('related_rules')
        if isinstance(related_rules, list):
            sanitized = []
            for rule_id in related_rules:
                if rule_id in RULE_METADATA and rule_id not in sanitized:
                    sanitized.append(rule_id)
            related_rules = sanitized
        else:
            related_rules = []

        if default_rule_id and not related_rules:
            related_rules = [default_rule_id]
        dim_result['related_rules'] = related_rules
        dim_result['evidence'] = _project_dimension_evidence(
            dim_name,
            dim_result.get('evidence'),
            poi_type_hint=poi_type_text,
            evidence_index=evidence_index,
        )

    adjusted = apply_semantic_adjustments(normalized)
    _recompute_downgrade_consistency(adjusted)
    _normalize_dimension_explanations(adjusted)
    return adjusted


def _normalize_dim_name(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return value.strip()


def _normalize_reason_code(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return value.strip().upper()


def _normalize_issue_code(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return value.strip().lower()


def _extract_dim_evidence_ids(dim_result: Dict[str, Any]) -> Set[str]:
    evidence_ids: Set[str] = set()
    evidence = dim_result.get('evidence')
    if not isinstance(evidence, list):
        return evidence_ids
    for item in evidence:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get('evidence_id')
        if isinstance(evidence_id, str) and evidence_id.strip():
            evidence_ids.add(evidence_id.strip())
    return evidence_ids


def _is_dimension_hard_conflict(dim_name: str, dim_result: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    status = str(dim_result.get('status') or '').strip()
    if status == 'fail':
        return True

    issue_code = _normalize_issue_code(dim_result.get('issue_code'))
    hard_issue_codes = {
        _normalize_issue_code(code)
        for code in ((policy.get('hard_conflict_issue_codes') or {}).get(dim_name) or [])
        if _normalize_issue_code(code)
    }
    if issue_code and issue_code in hard_issue_codes:
        return True

    hard_conflict_value = dim_result.get('hard_conflict')
    if isinstance(hard_conflict_value, bool):
        return hard_conflict_value

    # 兼容历史数据：当结构化字段缺失时，回退到 explanation 关键词识别
    explanation = _trim_explanation(dim_result.get('explanation')).lower()
    if not explanation:
        return False

    hard_keywords = ((policy.get('hard_conflict_keywords') or {}).get(dim_name) or [])
    for keyword in hard_keywords:
        if not isinstance(keyword, str):
            continue
        if keyword.strip().lower() and keyword.strip().lower() in explanation:
            return True
    return False


def derive_uncertain_dims(dimension_results: Dict[str, Any], hybrid_policy: Dict[str, Any]) -> List[str]:
    allowed_dimensions = {
        _normalize_dim_name(dim_name)
        for dim_name in (hybrid_policy.get('allowed_dimensions') or [])
        if _normalize_dim_name(dim_name) in CORE_DIMENSIONS
    }
    candidate_statuses = {
        str(status).strip()
        for status in (hybrid_policy.get('candidate_statuses') or [])
        if isinstance(status, str) and status.strip()
    }
    uncertain_dims: List[str] = []

    for dim_name in ALL_DIMENSIONS:
        if dim_name not in allowed_dimensions:
            continue
        dim_result = dimension_results.get(dim_name)
        if not isinstance(dim_result, dict):
            continue
        status = str(dim_result.get('status') or '').strip()
        if status not in candidate_statuses:
            continue
        if _is_dimension_hard_conflict(dim_name, dim_result, hybrid_policy):
            continue
        uncertain_dims.append(dim_name)
    return uncertain_dims


def _normalize_used_evidence_ids(raw_value: Any) -> List[str]:
    if not isinstance(raw_value, list):
        return []
    result: List[str] = []
    seen = set()
    for item in raw_value:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _override_transition(before_status: str, proposed_status: str) -> str:
    return f'{before_status}->{proposed_status}'


def apply_model_adjudication(
    dimension_results: Dict[str, Any],
    model_judgement: Optional[Dict[str, Any]],
    hybrid_policy: Dict[str, Any],
    task_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    adjusted = copy.deepcopy(dimension_results or {})
    policy = hybrid_policy or copy.deepcopy(HYBRID_DEFAULT_POLICY)

    report: Dict[str, Any] = {
        'mode': 'rules_only',
        'policy_enabled': bool(policy.get('enabled', False)),
        'task_id': task_id,
        'uncertain_dims': [],
        'model_override_count': 0,
        'applied_overrides': [],
        'rejected_overrides': [],
    }

    if not report['policy_enabled']:
        return adjusted, report

    report['mode'] = 'hybrid'
    uncertain_dims = derive_uncertain_dims(adjusted, policy)
    report['uncertain_dims'] = uncertain_dims

    if not isinstance(model_judgement, dict):
        report['mode'] = 'hybrid_no_model_judgement'
        return adjusted, report

    judgement_task_id = str(model_judgement.get('task_id') or '').strip()
    if task_id and judgement_task_id and judgement_task_id != str(task_id):
        report['mode'] = 'hybrid_rejected_task_mismatch'
        report['rejected_overrides'].append(
            {
                'reason': 'task_id_mismatch',
                'message': f'model_judgement.task_id={judgement_task_id} 与 qc_result.task_id={task_id} 不一致',
            }
        )
        return adjusted, report

    raw_overrides = model_judgement.get('overrides')
    if not isinstance(raw_overrides, list):
        report['mode'] = 'hybrid_no_override'
        return adjusted, report

    report['model_override_count'] = len(raw_overrides)
    if len(raw_overrides) == 0:
        report['mode'] = 'hybrid_no_override'
        return adjusted, report

    allowed_dimensions = {
        _normalize_dim_name(dim_name)
        for dim_name in (policy.get('allowed_dimensions') or [])
        if _normalize_dim_name(dim_name)
    }
    allowed_transitions = {
        str(item).strip()
        for item in (policy.get('allowed_transitions') or [])
        if isinstance(item, str) and item.strip()
    }
    min_conf_default = _safe_float(policy.get('min_confidence_default'))
    if min_conf_default is None:
        min_conf_default = 0.85
    min_conf_by_dim = policy.get('min_confidence_by_dimension') or {}
    min_evidence_by_dim = policy.get('min_evidence_ids_by_dimension') or {}
    allowed_reason_codes = policy.get('allowed_reason_codes') or {}
    reason_templates = policy.get('reason_templates') or {}
    allow_hard_conflict = bool(policy.get('allow_override_when_hard_conflict', False))

    for raw_override in raw_overrides:
        if not isinstance(raw_override, dict):
            report['rejected_overrides'].append(
                {
                    'reason': 'invalid_override_payload',
                    'message': f'override 项不是对象：{raw_override!r}',
                }
            )
            continue

        dim_name = _normalize_dim_name(raw_override.get('dimension'))
        proposed_status = str(raw_override.get('proposed_status') or '').strip()
        reason_code = _normalize_reason_code(raw_override.get('reason_code'))
        used_evidence_ids = _normalize_used_evidence_ids(raw_override.get('used_evidence_ids'))
        confidence_value = _safe_float(raw_override.get('confidence'))
        confidence = None if confidence_value is None else max(0.0, min(1.0, confidence_value))

        dim_result = adjusted.get(dim_name)
        before_status = str(dim_result.get('status') or '').strip() if isinstance(dim_result, dict) else ''

        rejection_base = {
            'dimension': dim_name,
            'proposed_status': proposed_status,
            'reason_code': reason_code,
            'used_evidence_ids': used_evidence_ids,
        }

        if dim_name not in allowed_dimensions:
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'dimension_not_allowed',
                    'message': f'维度 {dim_name} 不在 hybrid 覆盖白名单中',
                }
            )
            continue

        if dim_name not in uncertain_dims:
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'dimension_not_uncertain',
                    'message': f'维度 {dim_name} 不是当前可裁决争议维度',
                }
            )
            continue

        if not isinstance(dim_result, dict):
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'dimension_result_missing',
                    'message': f'维度 {dim_name} 结果缺失或结构非法',
                }
            )
            continue

        transition = _override_transition(before_status, proposed_status)
        if transition not in allowed_transitions:
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'transition_not_allowed',
                    'message': f'状态迁移 {transition} 不在允许列表中',
                }
            )
            continue

        if (not allow_hard_conflict) and _is_dimension_hard_conflict(dim_name, dim_result, policy):
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'hard_conflict_guard',
                    'message': f'维度 {dim_name} 命中硬冲突保护，不允许覆盖',
                }
            )
            continue

        dim_min_conf = _safe_float(min_conf_by_dim.get(dim_name))
        if dim_min_conf is None:
            dim_min_conf = min_conf_default
        if confidence is None or confidence < dim_min_conf:
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'confidence_too_low',
                    'message': f'置信度不足：需要 >= {dim_min_conf:.2f}，实际={confidence}',
                }
            )
            continue

        dim_reason_whitelist = {
            _normalize_reason_code(code)
            for code in (allowed_reason_codes.get(dim_name) or [])
            if _normalize_reason_code(code)
        }
        if reason_code not in dim_reason_whitelist:
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'reason_code_not_allowed',
                    'message': f'reason_code={reason_code} 不在维度 {dim_name} 白名单内',
                }
            )
            continue

        dim_evidence_ids = _extract_dim_evidence_ids(dim_result)
        min_required = _safe_int(min_evidence_by_dim.get(dim_name, 1))
        if min_required is None or min_required < 0:
            min_required = 1
        if len(used_evidence_ids) < min_required:
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'insufficient_evidence_ids',
                    'message': f'used_evidence_ids 不足：至少需要 {min_required} 条',
                }
            )
            continue
        if dim_evidence_ids and not set(used_evidence_ids).issubset(dim_evidence_ids):
            report['rejected_overrides'].append(
                {
                    **rejection_base,
                    'reason': 'evidence_id_not_in_dimension',
                    'message': 'used_evidence_ids 含不属于当前维度 evidence 的证据',
                }
            )
            continue

        override_explanation = _trim_explanation(raw_override.get('explanation'))
        if not override_explanation:
            override_explanation = _trim_explanation(reason_templates.get(reason_code))
        if not override_explanation:
            override_explanation = f'原因码 {reason_code} 满足覆盖策略。'

        dim_result['status'] = proposed_status
        dim_result['risk_level'] = 'none' if proposed_status == 'pass' else dim_result.get('risk_level', 'medium')
        dim_result['explanation'] = f'模型裁决通过：{override_explanation}'
        dim_result['confidence'] = round(confidence, 4)

        report['applied_overrides'].append(
            {
                'dimension': dim_name,
                'before_status': before_status,
                'after_status': proposed_status,
                'reason_code': reason_code,
                'confidence': round(confidence, 4),
                'used_evidence_ids': used_evidence_ids,
            }
        )

    if report['applied_overrides']:
        report['mode'] = 'hybrid_applied'
    elif report['rejected_overrides']:
        report['mode'] = 'hybrid_rejected'
    else:
        report['mode'] = 'hybrid_no_effect'

    return adjusted, report


def derive_risk_dims(dimension_results: Dict[str, Any]) -> List[str]:
    return [
        dim_name
        for dim_name in ALL_DIMENSIONS
        if _dimension_status(dimension_results, dim_name) in RISK_STATUSES
    ]


def derive_has_risk(dimension_results: Dict[str, Any]) -> bool:
    return len(derive_risk_dims(dimension_results)) > 0


def derive_qc_status(dimension_results: Dict[str, Any]) -> str:
    has_core_fail = any(_dimension_status(dimension_results, dim_name) == 'fail' for dim_name in CORE_DIMENSIONS)
    has_core_risk = any(_dimension_status(dimension_results, dim_name) == 'risk' for dim_name in CORE_DIMENSIONS)
    sufficiency_status = _dimension_status(dimension_results, 'evidence_sufficiency')
    consistency_status = _dimension_status(dimension_results, 'downgrade_consistency')

    if has_core_fail:
        return 'unqualified'
    if has_core_risk or sufficiency_status in RISK_STATUSES or consistency_status in RISK_STATUSES:
        return 'risky'
    return 'qualified'


def calculate_qc_score(
    dimension_results: Dict[str, Any],
    scoring_policy: Optional[Dict[str, Any]],
) -> int:
    if not scoring_policy:
        return 0

    weights = scoring_policy.get('dimension_weights', {})
    factors = scoring_policy.get('status_factors', {})
    pass_factor = factors.get('pass', 1.0)
    risk_factors = factors.get('risk', {})
    fail_factor = factors.get('fail', 0.0)

    total = 0.0
    for dim_name, weight in weights.items():
        dim_result = dimension_results.get(dim_name, {})
        if not isinstance(dim_result, dict):
            continue

        status = _normalize_status_value(dim_result.get('status'))
        risk_level = _normalize_risk_level_value(dim_result.get('risk_level'))
        if status == 'pass':
            factor = pass_factor
        elif status == 'risk':
            factor = risk_factors.get(risk_level, 0.0)
        else:
            factor = fail_factor
        total += float(weight) * float(factor)

    return int(round(total))


def derive_triggered_rules(dimension_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    triggered_rules: List[Dict[str, Any]] = []
    seen_rule_ids = set()

    for dim_name in ALL_DIMENSIONS:
        dim_result = dimension_results.get(dim_name, {})
        if not isinstance(dim_result, dict):
            continue
        if dim_result.get('status') not in RISK_STATUSES:
            continue

        related_rules = dim_result.get('related_rules')
        if isinstance(related_rules, list) and related_rules:
            candidate_rule_ids = [rule_id for rule_id in related_rules if rule_id in RULE_METADATA]
        else:
            default_rule_id = DEFAULT_RULE_BY_DIMENSION.get(dim_name)
            candidate_rule_ids = [default_rule_id] if default_rule_id else []

        for rule_id in candidate_rule_ids:
            if not rule_id or rule_id in seen_rule_ids:
                continue
            seen_rule_ids.add(rule_id)
            metadata = RULE_METADATA[rule_id]
            triggered_rules.append(
                {
                    'rule_id': rule_id,
                    'rule_name': metadata['rule_name'],
                    'dimension': metadata['dimension'],
                    'severity': metadata['severity'],
                }
            )

    return triggered_rules


def derive_statistics_flags(dimension_results: Dict[str, Any], qc_status: Optional[str] = None) -> Dict[str, Any]:
    resolved_qc_status = qc_status or derive_qc_status(dimension_results)
    qc_manual = derive_qc_manual_review_required(dimension_results)
    consistency_result = dimension_results.get('downgrade_consistency', {})
    consistency_status = _dimension_status(dimension_results, 'downgrade_consistency')
    upstream_manual = None
    issue_type = None
    if isinstance(consistency_result, dict):
        upstream_manual = consistency_result.get('upstream_manual_review_required')
        issue_type = consistency_result.get('issue_type')

    # 运营侧自动放行仍需考虑与上游降级一致性，避免“状态通过但降级冲突”直接放行。
    is_auto_approvable = (
        resolved_qc_status == 'qualified'
        and consistency_status not in RISK_STATUSES
    )

    return {
        'is_qualified': resolved_qc_status == 'qualified',
        'is_auto_approvable': is_auto_approvable,
        'is_manual_required': qc_manual,
        'qc_manual_review_required': qc_manual,
        'upstream_manual_review_required': upstream_manual,
        'downgrade_issue_type': issue_type,
    }


def _to_number(value: Any) -> Any:
    number = _safe_float(value)
    if number is None:
        return value
    return number


def _copy_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return {}


def _extract_recompute_input(
    finalized: Dict[str, Any],
    explicit_raw_input: Optional[Dict[str, Any]],
    evidence_record: Any,
    poi_type_hint: Optional[Any],
) -> Optional[Dict[str, Any]]:
    if isinstance(explicit_raw_input, dict):
        candidate = copy.deepcopy(explicit_raw_input)
    else:
        candidate: Dict[str, Any] = {}
        flat_keys = (
            'task_id',
            'name',
            'address',
            'x_coord',
            'y_coord',
            'poi_type',
            'city',
            'poi_status',
            'verify_result',
            'evidence_record',
        )
        for key in flat_keys:
            if key in finalized:
                candidate[key] = copy.deepcopy(finalized.get(key))

        record = finalized.get('record')
        if isinstance(record, dict):
            if candidate.get('task_id') is None:
                candidate['task_id'] = copy.deepcopy(record.get('task_id'))
            if candidate.get('name') is None:
                candidate['name'] = copy.deepcopy(record.get('name'))
            if candidate.get('address') is None:
                candidate['address'] = copy.deepcopy(
                    record.get('address') or _copy_json_dict(record.get('location')).get('address')
                )
            if candidate.get('poi_type') is None:
                candidate['poi_type'] = copy.deepcopy(record.get('poi_type') or record.get('category'))
            if candidate.get('city') is None:
                candidate['city'] = copy.deepcopy(
                    record.get('city') or _copy_json_dict(record.get('administrative')).get('city')
                )
            if candidate.get('poi_status') is None:
                candidate['poi_status'] = copy.deepcopy(record.get('poi_status') or record.get('existence'))
            if candidate.get('x_coord') is None:
                candidate['x_coord'] = copy.deepcopy(
                    record.get('x_coord') or _copy_json_dict(record.get('location')).get('longitude')
                )
            if candidate.get('y_coord') is None:
                candidate['y_coord'] = copy.deepcopy(
                    record.get('y_coord') or _copy_json_dict(record.get('location')).get('latitude')
                )

        if candidate.get('evidence_record') is None:
            evidence_data = finalized.get('evidence_data')
            if isinstance(evidence_data, list):
                candidate['evidence_record'] = copy.deepcopy(evidence_data)

    if candidate.get('poi_type') in (None, '') and poi_type_hint not in (None, ''):
        candidate['poi_type'] = copy.deepcopy(poi_type_hint)
    if candidate.get('evidence_record') is None and isinstance(evidence_record, list):
        candidate['evidence_record'] = copy.deepcopy(evidence_record)

    if 'x_coord' in candidate:
        candidate['x_coord'] = _to_number(candidate.get('x_coord'))
    if 'y_coord' in candidate:
        candidate['y_coord'] = _to_number(candidate.get('y_coord'))

    required = ('name', 'address', 'x_coord', 'y_coord', 'poi_type', 'city', 'evidence_record')
    for key in required:
        if candidate.get(key) is None or candidate.get(key) == '':
            return None
    if not isinstance(candidate.get('evidence_record'), list):
        return None
    return candidate


def _merge_core_dimension_results(
    original_dimension_results: Any,
    recomputed_core_dimensions: Dict[str, Any],
) -> Dict[str, Any]:
    merged = copy.deepcopy(original_dimension_results) if isinstance(original_dimension_results, dict) else {}
    for dim_name in CORE_DIMENSIONS:
        dim_result = recomputed_core_dimensions.get(dim_name)
        if isinstance(dim_result, dict):
            merged[dim_name] = copy.deepcopy(dim_result)
    return merged


def _recompute_core_dimensions(
    raw_input: Dict[str, Any],
    dsl_path: Optional[str],
    preprocess_evidence: bool,
) -> Dict[str, Any]:
    from dsl_executor import execute_core_dimensions  # 局部导入，避免循环依赖

    return execute_core_dimensions(
        raw_input,
        dsl_path=dsl_path,
        preprocess=preprocess_evidence,
    )


def finalize_qc_result(
    qc_result: Dict[str, Any],
    scoring_policy: Optional[Dict[str, Any]] = None,
    scoring_policy_path: Optional[str] = None,
    poi_type_hint: Optional[Any] = None,
    model_judgement: Optional[Dict[str, Any]] = None,
    hybrid_policy: Optional[Dict[str, Any]] = None,
    hybrid_policy_path: Optional[str] = None,
    raw_input: Optional[Dict[str, Any]] = None,
    recompute_core: bool = True,
    dsl_path: Optional[str] = None,
    preprocess_evidence: bool = True,
) -> Dict[str, Any]:
    finalized = copy.deepcopy(qc_result or {})
    resolved_poi_type_hint = poi_type_hint
    if resolved_poi_type_hint is None:
        resolved_poi_type_hint = finalized.get('poi_type')
    evidence_record = finalized.get('evidence_record')
    recompute_input = _extract_recompute_input(
        finalized,
        explicit_raw_input=raw_input,
        evidence_record=evidence_record,
        poi_type_hint=resolved_poi_type_hint,
    )
    if recompute_core and recompute_input is not None:
        recompute_result = _recompute_core_dimensions(
            recompute_input,
            dsl_path=dsl_path,
            preprocess_evidence=preprocess_evidence,
        )
        recomputed_dimensions = _copy_json_dict(recompute_result.get('dimension_results'))
        if recomputed_dimensions:
            finalized['dimension_results'] = _merge_core_dimension_results(
                finalized.get('dimension_results'),
                recomputed_dimensions,
            )
        recompute_payload = _copy_json_dict(recompute_result.get('payload'))
        recompute_evidence = recompute_payload.get('evidence_record')
        if isinstance(recompute_evidence, list):
            evidence_record = recompute_evidence

    finalized.pop('evidence_record', None)
    evidence_index = _build_evidence_index(evidence_record)
    finalized.pop('poi_type', None)
    finalized.pop('adjudication', None)
    normalized_dimensions = normalize_dimension_results(
        finalized.get('dimension_results', {}),
        poi_type_hint=resolved_poi_type_hint,
        evidence_index=evidence_index,
    )

    if model_judgement is not None:
        resolved_hybrid_policy = hybrid_policy or load_hybrid_policy(hybrid_policy_path)
        normalized_dimensions, adjudication_report = apply_model_adjudication(
            normalized_dimensions,
            model_judgement=model_judgement,
            hybrid_policy=resolved_hybrid_policy,
            task_id=finalized.get('task_id'),
        )
        normalized_dimensions['evidence_sufficiency'] = _derive_evidence_sufficiency(normalized_dimensions)
        _recompute_downgrade_consistency(normalized_dimensions)
        _normalize_dimension_explanations(normalized_dimensions)
        finalized['adjudication'] = adjudication_report

    finalized['dimension_results'] = normalized_dimensions

    resolved_scoring_policy = scoring_policy or load_scoring_policy(scoring_policy_path)
    finalized['risk_dims'] = derive_risk_dims(normalized_dimensions)
    finalized['has_risk'] = len(finalized['risk_dims']) > 0
    finalized['qc_status'] = derive_qc_status(normalized_dimensions)
    finalized['qc_score'] = calculate_qc_score(normalized_dimensions, resolved_scoring_policy)
    finalized['triggered_rules'] = derive_triggered_rules(normalized_dimensions)
    finalized['statistics_flags'] = derive_statistics_flags(normalized_dimensions, finalized['qc_status'])
    finalized['explanation'] = derive_overall_explanation(
        normalized_dimensions,
        finalized['qc_status'],
        finalized['qc_score'],
    )
    return finalized
