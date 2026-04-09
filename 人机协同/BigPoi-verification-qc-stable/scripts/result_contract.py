#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BigPOI 质检结果契约计算模块。

职责：
1. 统一派生字段的计算逻辑
2. 生成稳定的 triggered_rules
3. 将可反算字段从模型自由输出收敛为程序确定性输出
"""

import ast
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
MANUAL_REVIEW_TRIGGER_ISSUE_CODES = {
    'all_name_similarity_below_threshold',
    'address_direct_conflict',
    'administrative_direct_conflict',
    'typecode_conflict',
    'authoritative_distance_gt_500m',
    'no_valid_coordinate_evidence',
    'no_valid_category_evidence',
}
NON_BLOCKING_DOWNGRADE_ISSUE_TYPES = {'unnecessary_downgrade'}
ADVISORY_RISK_ISSUE_CODES = {
    'address': {'soft_address_match_only', 'single_exact_address_support'},
    'location': {'coordinate_distance_between_201_and_500', 'coordinate_far_outlier_with_close_support'},
    'category': {'category_text_only_support'},
}
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
ROAD_SEGMENT_SUFFIX_PATTERN = re.compile(r'(大道|路|街|巷|国道|省道|县道|道)(?:中段|东段|西段|南段|北段|中|东|西|南|北)$')
ADMIN_PREFIX_PATTERN = re.compile(
    r'^(?:中国|[\u4e00-\u9fff]{2,9}(?:省|市|自治区|特别行政区|地区|盟|自治州|州|县|区|镇|乡|街道))+'
)
ROAD_LOCALITY_BREAK_TOKENS = (
    '街道',
    '社区',
    '镇',
    '乡',
    '村',
    '新区',
    '开发区',
    '工业区',
    '工业园',
    '园区',
    '片区',
)
ROAD_CONNECTOR_TOKENS = ('与', '和', '及', '、')
ROAD_NOISE_SUFFIX_KEYWORDS = (
    '街道办事处',
    '街道办',
    '办事处',
    '居民委员会',
    '居委会',
    '村民委员会',
    '村委会',
    '村委',
    '社区',
    '村',
)
CITY_NAME_PATTERN = re.compile(r'([\u4e00-\u9fff]{2,12}市)')
LOCATION_AUXILIARY_KEYWORDS = (
    '停车场',
    '入口',
    '出口',
    '东门',
    '西门',
    '南门',
    '北门',
    '充电站',
    '检察室',
    '法庭',
    '居委会',
    '居民委员会',
    '村委会',
    '村民委员会',
    '道路',
    '大道',
    '广场',
    '服务中心',
    '征兵办公室',
    '住房规划建设局',
)
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
    return dim_result.get('status')


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


def _is_informative_evidence_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    for key in ('source', 'data', 'verification', 'matching'):
        value = item.get(key)
        if isinstance(value, dict) and value:
            return True
    return False


def _collect_fallback_evidence_for_location(dimension_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []
    for dim_name in ('location', 'address', 'name'):
        dim_result = dimension_results.get(dim_name)
        if not isinstance(dim_result, dict):
            continue
        evidence = dim_result.get('evidence')
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if _is_informative_evidence_item(item):
                collected.append(copy.deepcopy(item))
    deduped = _dedupe_evidence_items(collected)
    return deduped[:3]


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


def _extract_cityname_from_raw_data(data: Dict[str, Any]) -> Optional[str]:
    raw_data = data.get('raw_data')
    if not isinstance(raw_data, dict):
        return None

    nested_raw = raw_data.get('data')
    if isinstance(nested_raw, dict):
        nested_city = _first_non_empty(
            nested_raw.get('city'),
            nested_raw.get('cityname'),
        )
        if isinstance(nested_city, str) and nested_city.strip():
            return nested_city.strip()

    raw_city = _first_non_empty(
        raw_data.get('city'),
        raw_data.get('cityname'),
    )
    if isinstance(raw_city, str) and raw_city.strip():
        return raw_city.strip()
    return None


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
            projected_matching = _copy_present(matching, ['location_distance', 'name_similarity'])
            if projected_matching:
                projected['matching'] = projected_matching
    elif dim_name == 'address':
        address = _first_non_empty(data.get('address'), data.get('location', {}).get('address') if isinstance(data.get('location'), dict) else None)
        projected_data = {'address': address} if address is not None else {}
        if isinstance(matching, dict):
            projected_matching = _copy_present(matching, ['name_similarity', 'address_match_level'])
            if projected_matching:
                projected['matching'] = projected_matching
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
        cityname = _extract_cityname_from_raw_data(data)
        if cityname is not None:
            projected_data['cityname'] = cityname
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


def _project_dimension_evidence(
    dim_name: str,
    evidence_items: Any,
    poi_type_hint: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(evidence_items, list):
        return []
    projected_items = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        projected_item = _project_evidence_item(dim_name, item, poi_type_hint=poi_type_hint)
        if projected_item:
            projected_items.append(projected_item)
    return _dedupe_evidence_items(projected_items)


def _trim_explanation(text: Any) -> str:
    if not isinstance(text, str):
        return ''
    return ' '.join(text.strip().split())


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


def _extract_distance_confidence_pairs(evidence_items: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    pairs: List[Tuple[float, float]] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        matching = item.get('matching')
        if not isinstance(matching, dict):
            continue
        distance = _safe_float(matching.get('location_distance'))
        if distance is None or distance < 0:
            continue
        pairs.append((distance, _evidence_confidence(item)))
    return pairs


def _extract_location_signals(evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        matching = item.get('matching')
        if not isinstance(matching, dict):
            continue
        distance = _safe_float(matching.get('location_distance'))
        if distance is None or distance < 0:
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            data = {}
        name_similarity = _safe_float(matching.get('name_similarity'))
        signals.append(
            {
                'distance': float(distance),
                'confidence': _evidence_confidence(item),
                'name_similarity': name_similarity,
                'source_type': _evidence_source_type(item),
                'name': data.get('name'),
                'category': data.get('category'),
            }
        )
    return signals


def _is_relevant_location_signal(signal: Dict[str, Any]) -> bool:
    name_similarity = signal.get('name_similarity')
    if name_similarity is None:
        return True
    try:
        return float(name_similarity) >= 0.6
    except (TypeError, ValueError):
        return True


def _contains_any_keyword(text: str, keywords: Tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_auxiliary_location_name(name: Any, category: Any) -> bool:
    name_text = str(name or '').strip()
    category_text = str(category or '').strip()
    merged = f'{name_text} {category_text}'
    if not merged.strip():
        return False
    if _contains_any_keyword(merged, LOCATION_AUXILIARY_KEYWORDS):
        return True
    return False


def _is_exact_target_location_signal(signal: Dict[str, Any]) -> bool:
    similarity = _safe_float(signal.get('name_similarity'))
    if similarity is None or similarity < 0.88:
        return False
    name_text = str(signal.get('name') or '').strip()
    if not name_text:
        return False
    if _is_auxiliary_location_name(signal.get('name'), signal.get('category')):
        return False
    return True


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


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
        address = _normalize_address_text(data.get('address'))
        if not address:
            continue
        addresses.append(address.strip())
    return addresses


def _normalize_address_text(value: Any) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if (
            (text.startswith('{') and text.endswith('}'))
            or (text.startswith('[') and text.endswith(']'))
        ):
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return text
            nested = _normalize_address_text(parsed)
            return nested or text
        return text

    if isinstance(value, dict):
        candidates: List[Any] = [
            value.get('full'),
            value.get('address'),
        ]
        street = value.get('street')
        street_number = value.get('street_number')
        if isinstance(street, str) and street.strip():
            street_text = street.strip()
            candidates.append(street_text)
            if isinstance(street_number, str) and street_number.strip():
                street_number_text = street_number.strip()
                if street_number_text not in street_text:
                    candidates.append(f'{street_text}{street_number_text}')
        for candidate in candidates:
            normalized = _normalize_address_text(candidate)
            if normalized:
                return normalized
        return None

    if isinstance(value, (list, tuple)):
        for item in value:
            normalized = _normalize_address_text(item)
            if normalized:
                return normalized
        return None

    text = str(value).strip()
    return text or None


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
    normalized = normalized.replace('村民委员会', '村')
    normalized = normalized.replace('村委会', '村')
    normalized = normalized.replace('村委', '村')
    normalized = normalized.replace('居民委员会', '社区')
    normalized = normalized.replace('居委会', '社区')
    normalized = normalized.replace('居委', '社区')
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
        address = _normalize_address_text(data.get('address'))
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
        address = _normalize_address_text(data.get('address'))
        if not address or _is_low_information_address(address):
            continue
        confidence = _evidence_confidence(item)
        if confidence > 0:
            values.append(confidence)
    return values


def _has_authoritative_hard_address_conflict(evidence_items: List[Dict[str, Any]]) -> bool:
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        matching = item.get('matching')
        if not isinstance(matching, dict):
            continue
        level = str(matching.get('address_match_level') or '').strip().lower()
        if level not in {'house_number_conflict', 'city_district_conflict'}:
            continue
        confidence = _evidence_confidence(item)
        if confidence < 0.9:
            continue
        source_type = _evidence_source_type(item)
        if source_type in AUTHORITATIVE_SOURCE_TYPES or source_type in {'government', 'official_data', 'official_registry'}:
            return True
    return False


def _filter_address_semantic_evidence(evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        matching = item.get('matching')
        if not isinstance(matching, dict):
            filtered.append(item)
            continue
        if matching.get('subject_consistent') is False:
            continue
        similarity = _safe_float(matching.get('name_similarity'))
        if similarity is None or similarity >= 0.6:
            filtered.append(item)
    # 至少保留两条时才启用过滤，否则回退原证据避免误删。
    if len(filtered) >= 2:
        return filtered
    return evidence_items


def _normalize_city_name(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = ''.join(value.strip().split())
    if not text:
        return None
    match = CITY_NAME_PATTERN.search(text)
    if match:
        text = match.group(1)
    if text.endswith('市'):
        text = text[:-1]
    return text or None


def _extract_city_name_from_text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    match = CITY_NAME_PATTERN.search(text)
    if match:
        return _normalize_city_name(match.group(1))
    return None


def _collect_city_signals(evidence_items: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    city_support: Dict[str, Dict[str, float]] = {}
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            continue
        confidence = _evidence_confidence(item)
        candidates: List[Any] = []
        administrative = data.get('administrative')
        if isinstance(administrative, dict):
            candidates.append(administrative.get('city'))
        candidates.append(data.get('cityname'))
        candidates.append(data.get('address'))
        candidates.append(data.get('name'))

        for candidate in candidates:
            city_name = _normalize_city_name(candidate) if candidate is not None else None
            if city_name is None:
                city_name = _extract_city_name_from_text(candidate)
            if city_name is None:
                continue
            stats = city_support.setdefault(city_name, {'count': 0.0, 'max_conf': 0.0})
            stats['count'] += 1.0
            if confidence > stats['max_conf']:
                stats['max_conf'] = confidence
    return city_support


def _dominant_address_cluster_indices(addresses: List[str]) -> List[int]:
    if not addresses:
        return []
    if len(addresses) == 1:
        return [0]

    best_cluster: List[int] = [0]
    best_count = 1
    for base_idx, base_addr in enumerate(addresses):
        cluster = [base_idx]
        for candidate_idx, candidate_addr in enumerate(addresses):
            if base_idx == candidate_idx:
                continue
            if _are_two_addresses_semantically_consistent(base_addr, candidate_addr):
                cluster.append(candidate_idx)
        cluster = sorted(set(cluster))
        if len(cluster) > best_count:
            best_cluster = cluster
            best_count = len(cluster)

    return best_cluster


def _assess_address_same_place(
    addresses: List[str],
    confidences: List[float],
) -> Dict[str, Any]:
    if not addresses:
        return {
            'same_place': False,
            'confidence': 0.0,
            'semantic_relation': 'insufficient_address_signal',
            'conflict_points': '缺少可用于语义比对的地址信息。',
        }

    cluster_indices = _dominant_address_cluster_indices(addresses)
    required_cluster_size = max(2, (len(addresses) + 1) // 2)
    if len(addresses) == 1:
        required_cluster_size = 1

    if not _are_addresses_semantically_consistent(addresses):
        return {
            'same_place': False,
            'confidence': 0.0,
            'semantic_relation': 'hard_conflict',
            'conflict_points': _describe_address_conflict(addresses),
        }

    if len(cluster_indices) < required_cluster_size:
        return {
            'same_place': False,
            'confidence': 0.0,
            'semantic_relation': 'hard_conflict',
            'conflict_points': _describe_address_conflict(addresses),
        }

    clustered_addresses = [addresses[index] for index in cluster_indices if 0 <= index < len(addresses)]
    clustered_confidences = [
        confidences[index]
        for index in cluster_indices
        if 0 <= index < len(confidences)
    ]

    road_anchors = [
        _normalize_address_for_compare(anchor)
        for anchor in (_extract_road_anchor(addr) for addr in clustered_addresses)
        if isinstance(anchor, str) and anchor.strip()
    ]
    house_numbers = [
        number
        for number in (_extract_house_number(addr) for addr in clustered_addresses)
        if isinstance(number, str) and number.strip()
    ]

    has_shared_road_anchor = len(road_anchors) >= 1 and len(set(road_anchors)) == 1
    has_house_number = len(house_numbers) >= 1
    has_consistent_house_number = len(house_numbers) >= 1 and len(set(house_numbers)) == 1
    has_road_code_signal = any(_extract_road_code(addr) for addr in clustered_addresses)

    confidence_base = max(clustered_confidences) if clustered_confidences else (max(confidences) if confidences else 0.0)
    if len(clustered_addresses) >= 2:
        confidence_base += 0.04
    if has_shared_road_anchor:
        confidence_base += 0.04
    if has_consistent_house_number:
        confidence_base += 0.03
    if has_road_code_signal:
        confidence_base += 0.02
    confidence = round(min(0.98, confidence_base), 4)

    if has_shared_road_anchor and has_consistent_house_number:
        semantic_relation = 'same_road_same_house_number'
    elif has_shared_road_anchor and not has_house_number:
        semantic_relation = 'same_road_house_number_missing'
    elif has_shared_road_anchor:
        semantic_relation = 'same_road_house_number_partially_missing'
    else:
        semantic_relation = 'prefix_or_abbreviation_equivalent'

    return {
        'same_place': True,
        'confidence': confidence,
        'semantic_relation': semantic_relation,
        'conflict_points': '',
    }


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
    base_road = _extract_road_anchor(base)
    candidate_road = _extract_road_anchor(candidate)
    base_house = _extract_house_number(base)
    candidate_house = _extract_house_number(candidate)
    if (
        isinstance(base_road, str)
        and isinstance(candidate_road, str)
    ):
        base_road_norm = _normalize_road_anchor_for_match(base_road)
        candidate_road_norm = _normalize_road_anchor_for_match(candidate_road)
        road_semantic_same = (
            bool(base_road_norm)
            and bool(candidate_road_norm)
            and (
                base_road_norm == candidate_road_norm
                or base_road_norm in candidate_road_norm
                or candidate_road_norm in base_road_norm
            )
        )
        if not road_semantic_same:
            return False
        if (
            isinstance(base_house, str)
            and isinstance(candidate_house, str)
            and base_house == candidate_house
        ):
            return True
        if not base_house or not candidate_house:
            return True
    return False


def _strip_admin_prefix(address: str) -> str:
    text = str(address or '').strip()
    return ADMIN_PREFIX_PATTERN.sub('', text)


def _normalize_road_anchor_text(value: str) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    text = _strip_admin_prefix(text)

    for token in ROAD_LOCALITY_BREAK_TOKENS:
        if token not in text:
            continue
        head = text.rsplit(token, 1)[0].strip()
        if head:
            text = head

    for token in ROAD_CONNECTOR_TOKENS:
        if token not in text:
            continue
        parts = [part.strip() for part in text.split(token) if part.strip()]
        if parts:
            text = parts[-1]

    road_end = re.search(r'.*?(?:路|街|巷|大道|国道|省道|县道|道)', text)
    if road_end:
        text = road_end.group(0).strip()

    for suffix in ROAD_NOISE_SUFFIX_KEYWORDS:
        if not text.endswith(suffix):
            continue
        stripped = text[:-len(suffix)].strip()
        if stripped:
            text = stripped

    return text


def _extract_road_anchor(address: str) -> Optional[str]:
    text = str(address or '').strip()
    if not text:
        return None
    matches = [match.group(1) for match in ROAD_PATTERN.finditer(text)]
    if not matches:
        return None
    road_text = _normalize_road_anchor_text(matches[-1])
    return road_text or None


def _normalize_road_anchor_for_match(anchor: str) -> str:
    text = str(anchor or '').strip()
    if not text:
        return ''
    text = ROAD_SEGMENT_SUFFIX_PATTERN.sub(r'\1', text)
    return _normalize_address_for_compare(text)


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
        if base_road and candidate_road:
            base_road_norm = _normalize_road_anchor_for_match(base_road)
            candidate_road_norm = _normalize_road_anchor_for_match(candidate_road)
            road_semantic_same = (
                bool(base_road_norm)
                and bool(candidate_road_norm)
                and (
                    base_road_norm == candidate_road_norm
                    or base_road_norm in candidate_road_norm
                    or candidate_road_norm in base_road_norm
                )
            )
            if not road_semantic_same:
                return f'道路主干不一致（{base_road} vs {candidate_road}）。冲突样例："{base}" vs "{candidate}"。'
        return f'主地址锚点不一致。冲突样例："{base}" vs "{candidate}"。'
    return '证据地址之间存在无法消解的语义冲突。'


def _are_addresses_semantically_consistent(addresses: List[str]) -> bool:
    if len(addresses) <= 1:
        return True
    cluster_indices = _dominant_address_cluster_indices(addresses)
    required_cluster_size = max(2, (len(addresses) + 1) // 2)
    return len(cluster_indices) >= required_cluster_size


def _apply_location_semantic_adjustment(dimension_results: Dict[str, Any]) -> None:
    dim_result = dimension_results.get('location')
    if not isinstance(dim_result, dict):
        return
    status = dim_result.get('status')
    if status not in {'risk', 'fail'}:
        return

    issue_code = _normalize_issue_code(dim_result.get('issue_code'))
    if status == 'fail' and issue_code in {'no_valid_coordinate_evidence'}:
        name_pass = _dimension_status(dimension_results, 'name') == 'pass'
        address_pass = _dimension_status(dimension_results, 'address') == 'pass'
        if name_pass and address_pass:
            dim_result['status'] = 'risk'
            dim_result['risk_level'] = 'low'
            dim_result['confidence'] = max(dim_result.get('confidence', 0.0) or 0.0, 0.75)
            dim_result['issue_code'] = 'coordinate_missing_but_fact_supported'
            dim_result['hard_conflict'] = False
            dim_result['explanation'] = '坐标风险：缺少可用坐标证据，但名称与地址已通过，建议补采坐标后复核。'
            evidence = dim_result.get('evidence')
            if not isinstance(evidence, list) or not any(_is_informative_evidence_item(item) for item in evidence):
                fallback_evidence = _collect_fallback_evidence_for_location(dimension_results)
                if fallback_evidence:
                    dim_result['evidence'] = fallback_evidence
            return

    evidence = dim_result.get('evidence')
    if not isinstance(evidence, list):
        return

    signals = _extract_location_signals(evidence)
    if len(signals) < 2:
        return

    relevant_signals = [signal for signal in signals if _is_relevant_location_signal(signal)]
    considered_signals = relevant_signals if len(relevant_signals) >= 2 else signals

    distances = [signal['distance'] for signal in considered_signals]
    close_count = sum(1 for distance in distances if distance <= 200)
    mid_count = sum(1 for distance in distances if 200 < distance <= 500)
    far_count = sum(1 for distance in distances if distance > 500)
    high_conf_close_count = sum(
        1
        for signal in considered_signals
        if signal['distance'] <= 200 and signal['confidence'] >= 0.8
    )
    high_conf_far_count = sum(
        1
        for signal in considered_signals
        if signal['distance'] > 500 and signal['confidence'] >= 0.8
    )
    total = len(distances)
    close_ratio = close_count / total if total > 0 else 0.0
    median_distance = _median(distances)

    exact_near_signals = [
        signal
        for signal in considered_signals
        if signal['distance'] <= 200 and _is_exact_target_location_signal(signal)
    ]
    exact_far_high_conf_signals = [
        signal
        for signal in considered_signals
        if signal['distance'] > 500 and _is_exact_target_location_signal(signal) and signal['confidence'] >= 0.8
    ]
    if (
        issue_code in {'coordinate_far_outlier_with_close_support', 'authoritative_distance_gt_500m'}
        and len(exact_near_signals) >= 1
        and len(exact_far_high_conf_signals) == 0
    ):
        confidences = [signal['confidence'] for signal in considered_signals]
        confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.85
        dim_result['status'] = 'pass'
        dim_result['risk_level'] = 'none'
        dim_result['confidence'] = max(confidence, 0.85)
        dim_result['issue_code'] = 'location_far_outlier_name_irrelevant'
        dim_result['hard_conflict'] = False
        dim_result['explanation'] = (
            '坐标通过：离群点名称与目标 POI 不构成同目标高置信相关，近距离同目标证据占优。'
        )
        return

    if (
        total >= 2
        and close_count >= 2
        and close_ratio >= 0.6
        and high_conf_close_count >= 1
        and median_distance is not None
        and median_distance <= 200
    ):
        confidences = [signal['confidence'] for signal in considered_signals]
        confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.85
        ignored_count = max(0, len(signals) - len(considered_signals))
        dim_result['status'] = 'pass'
        dim_result['risk_level'] = 'none'
        dim_result['confidence'] = max(confidence, 0.85)
        dim_result['issue_code'] = 'location_supported_by_relevant_cluster'
        dim_result['hard_conflict'] = False
        if ignored_count > 0:
            dim_result['explanation'] = (
                f'坐标通过：名称相关的坐标证据形成近距离稳定簇（已忽略 {ignored_count} 条低相关离群点）。'
            )
        else:
            dim_result['explanation'] = '坐标通过：多数坐标证据形成近距离稳定簇，判定坐标一致。'
        return

    # 场景A：仅有单个 201-500m 的中距离离群，其余证据稳定在 200m 内。
    if (
        far_count == 0
        and close_count >= 2
        and mid_count >= 1
        and high_conf_close_count >= 1
        and median_distance is not None
        and median_distance <= 200
    ):
        confidences = _extract_confidences(evidence)
        confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.85
        dim_result['status'] = 'pass'
        dim_result['risk_level'] = 'none'
        dim_result['confidence'] = max(confidence, 0.85)
        dim_result['issue_code'] = 'location_supported_with_single_mid_outlier'
        dim_result['hard_conflict'] = False
        dim_result['explanation'] = (
            '坐标通过：仅存在单个 201-500 米中距离离群点，其余多数证据在 200 米内，按稳健规则判定坐标一致。'
        )
        return

    # 场景B：单个 >500m 离群点，但其余坐标形成稳定多数（避免“单点离群导致 fail”）。
    if (
        far_count == 1
        and close_count >= 3
        and high_conf_close_count >= 2
        and total >= 4
        and (close_count / total) >= 0.6
        and median_distance is not None
        and median_distance <= 200
    ):
        confidences = _extract_confidences(evidence)
        confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.85
        dim_result['status'] = 'pass'
        dim_result['risk_level'] = 'none'
        dim_result['confidence'] = max(confidence, 0.85)
        dim_result['issue_code'] = 'location_supported_with_single_far_outlier'
        dim_result['hard_conflict'] = False
        dim_result['explanation'] = (
            '坐标通过：检测到 1 条 >500 米离群坐标证据，但其余多数证据在 200 米内且形成稳定簇，按稳健规则判定一致。'
        )
        return

    # 场景C：fail 但存在明显近距离支持簇，降级为 risk 以避免极端离群一票否决。
    if (
        status == 'fail'
        and issue_code in {'authoritative_distance_gt_500m'}
        and close_count >= 1
        and close_ratio >= 0.5
        and high_conf_far_count == 0
    ):
        confidence = max((signal['confidence'] for signal in considered_signals), default=0.8)
        dim_result['status'] = 'risk'
        dim_result['risk_level'] = 'medium'
        dim_result['confidence'] = round(confidence, 4)
        dim_result['issue_code'] = 'coordinate_far_outlier_with_close_support'
        dim_result['hard_conflict'] = False
        dim_result['explanation'] = '坐标风险：存在远距离离群点，但近距离证据形成支撑簇，建议人工复核离群点。'


def _apply_address_semantic_adjustment(dimension_results: Dict[str, Any]) -> None:
    dim_result = dimension_results.get('address')
    if not isinstance(dim_result, dict):
        return
    status = dim_result.get('status')
    if status not in {'risk', 'fail'}:
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
    issue_code = _normalize_issue_code(dim_result.get('issue_code'))
    if status == 'risk':
        if issue_code not in {'soft_address_match_only', 'single_exact_address_support'} and not any(
            keyword in explanation for keyword in soft_risk_keywords
        ):
            return
    else:
        if issue_code not in {'address_direct_conflict'}:
            return

    semantic_evidence = _filter_address_semantic_evidence(evidence)
    if _has_authoritative_hard_address_conflict(semantic_evidence):
        dim_result['hard_conflict'] = True
        if status == 'fail':
            if not explanation:
                dim_result['explanation'] = '地址失败：存在高置信权威来源门牌或行政区划直接冲突。'
        else:
            if not explanation:
                dim_result['explanation'] = '地址风险：存在高置信权威来源门牌或行政区划直接冲突。'
        return

    addresses = _extract_informative_addresses(semantic_evidence)
    informative_confidences = _extract_informative_address_confidences(semantic_evidence)
    if not addresses or not informative_confidences:
        if status == 'risk':
            dim_result['explanation'] = '地址风险：有效证据仅包含省市级或低信息地址，无法确认道路与门牌是否一致。'
        else:
            dim_result['explanation'] = '地址失败：缺少可用于语义同址复核的有效地址证据。'
        return

    semantic = _assess_address_same_place(addresses, informative_confidences)
    if not semantic.get('same_place'):
        dim_result['hard_conflict'] = True
        if status == 'fail':
            dim_result['explanation'] = f"地址失败：{semantic.get('conflict_points') or _describe_address_conflict(addresses)}"
        else:
            dim_result['explanation'] = f"地址风险：{semantic.get('conflict_points') or _describe_address_conflict(addresses)}"
        return

    max_confidence = max(informative_confidences) if informative_confidences else 0.0
    semantic_confidence = _safe_float(semantic.get('confidence')) or 0.0
    semantic_relation = str(semantic.get('semantic_relation') or '').strip()
    prefix_only_hints = ('主地址', '前缀', '省市区', '镇街道')
    required_confidence = 0.8 if any(hint in explanation for hint in prefix_only_hints) else 0.82
    if issue_code == 'single_exact_address_support':
        required_confidence = min(required_confidence, 0.8)
    if status == 'fail':
        required_confidence = max(required_confidence, 0.85)
    final_confidence = max(max_confidence, semantic_confidence)
    if final_confidence < required_confidence:
        if status == 'fail':
            dim_result['explanation'] = (
                f'地址失败：语义同址候选成立，但证据置信度不足（需要 >= {required_confidence:.2f}，当前 {final_confidence:.2f}）。'
            )
        else:
            dim_result['explanation'] = (
                f'地址风险：语义同址候选成立，但证据置信度不足（需要 >= {required_confidence:.2f}，当前 {final_confidence:.2f}）。'
            )
        return

    dim_result['status'] = 'pass'
    dim_result['risk_level'] = 'none'
    dim_result['confidence'] = round(max(final_confidence, required_confidence), 4)
    dim_result['issue_code'] = 'address_semantic_same_place'
    dim_result['hard_conflict'] = False
    if required_confidence < 0.85 or semantic_relation == 'prefix_or_abbreviation_equivalent':
        dim_result['explanation'] = '地址通过：语义补判认为地址仅存在行政前缀/简称差异，指向同一地点。'
    elif semantic_relation == 'same_road_house_number_missing':
        dim_result['explanation'] = '地址通过：语义补判认为主道路一致，门牌在部分证据中缺失，仍可判定同址。'
    else:
        dim_result['explanation'] = '地址通过：语义补判认为主道路与门牌锚点一致，指向同一地点。'


def _apply_administrative_semantic_adjustment(dimension_results: Dict[str, Any]) -> None:
    dim_result = dimension_results.get('administrative')
    if not isinstance(dim_result, dict):
        return

    status = dim_result.get('status')
    if status not in {'risk', 'fail'}:
        return

    evidence = dim_result.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        return

    issue_code = _normalize_issue_code(dim_result.get('issue_code'))
    if status == 'risk' and issue_code not in {'single_exact_admin_support'}:
        return
    if status == 'fail' and issue_code not in {'administrative_direct_conflict'}:
        return

    city_signals = _collect_city_signals(evidence)
    if not city_signals:
        return

    top_city, top_stats = max(
        city_signals.items(),
        key=lambda item: (item[1].get('count', 0.0), item[1].get('max_conf', 0.0), item[0]),
    )
    support_count = int(top_stats.get('count', 0.0))
    top_confidence = float(top_stats.get('max_conf', 0.0))
    has_structured_city = False
    for item in evidence:
        if not isinstance(item, dict):
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            continue
        administrative = data.get('administrative')
        if isinstance(administrative, dict) and isinstance(administrative.get('city'), str) and administrative.get('city').strip():
            has_structured_city = True
            break

    if status == 'risk':
        if top_confidence >= 0.8 and (support_count >= 2 or has_structured_city):
            dim_result['status'] = 'pass'
            dim_result['risk_level'] = 'none'
            dim_result['confidence'] = round(max(top_confidence, 0.8), 4)
            dim_result['issue_code'] = 'administrative_supported_by_multi_signal'
            dim_result['hard_conflict'] = False
            dim_result['explanation'] = (
                f'行政区划通过：city 的结构化/语义信号可交叉支持（主城市信号：{top_city}）。'
            )
        return

    # fail -> risk：仅当冲突证据不足以形成硬冲突主导时放宽，避免一票否决。
    if top_confidence >= 0.8 and support_count >= 2:
        dim_result['status'] = 'risk'
        dim_result['risk_level'] = 'medium'
        dim_result['confidence'] = round(top_confidence, 4)
        dim_result['issue_code'] = 'administrative_conflict_needs_review'
        dim_result['hard_conflict'] = False
        dim_result['explanation'] = (
            f'行政区划风险：存在 city 冲突线索，但多条证据语义支持 {top_city}，建议人工复核。'
        )


def _apply_category_semantic_adjustment(dimension_results: Dict[str, Any]) -> None:
    dim_result = dimension_results.get('category')
    if not isinstance(dim_result, dict):
        return

    status = dim_result.get('status')
    if status not in {'risk', 'fail'}:
        return

    evidence = dim_result.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        return

    typecode_match_confidences: List[float] = []
    fallback_strong_confidences: List[float] = []
    fallback_conflict_count = 0
    explicit_typecode_conflict_count = 0

    for item in evidence:
        if not isinstance(item, dict):
            continue
        matching = item.get('matching')
        confidence = _evidence_confidence(item)
        if isinstance(matching, dict):
            category_match = _safe_float(matching.get('category_match'))
            if category_match is not None:
                if category_match >= 0.999:
                    typecode_match_confidences.append(confidence)
                elif category_match < 0.5:
                    explicit_typecode_conflict_count += 1

            fallback_support = _normalize_support_level(matching.get('category_fallback_support'))
            if fallback_support == 'strong':
                fallback_strong_confidences.append(confidence)
            elif fallback_support == 'conflict':
                fallback_conflict_count += 1

    max_typecode_match_conf = max(typecode_match_confidences) if typecode_match_confidences else 0.0
    max_fallback_strong_conf = max(fallback_strong_confidences) if fallback_strong_confidences else 0.0
    issue_code = _normalize_issue_code(dim_result.get('issue_code'))

    if status == 'risk':
        if max_typecode_match_conf >= 0.8 or max_fallback_strong_conf >= 0.8:
            resolved_conf = max(max_typecode_match_conf, max_fallback_strong_conf, 0.8)
            dim_result['status'] = 'pass'
            dim_result['risk_level'] = 'none'
            dim_result['confidence'] = round(resolved_conf, 4)
            dim_result['issue_code'] = 'category_supported_by_semantic_or_typecode'
            dim_result['hard_conflict'] = False
            if max_typecode_match_conf >= 0.8:
                dim_result['explanation'] = '类型通过：存在 typecode 精确匹配，且证据置信度满足稳定支持阈值。'
            else:
                dim_result['explanation'] = '类型通过：typecode 缺失时，中文类目/名称语义回退达到 strong 支持。'
        return

    # fail -> risk：仅回退语义冲突，不应与强 typecode 冲突同级处理。
    if (
        issue_code == 'typecode_conflict'
        and fallback_conflict_count >= 1
        and explicit_typecode_conflict_count == 0
        and max_typecode_match_conf == 0.0
    ):
        dim_result['status'] = 'risk'
        dim_result['risk_level'] = 'medium'
        dim_result['confidence'] = round(max(max_fallback_strong_conf, 0.7), 4)
        dim_result['issue_code'] = 'category_fallback_conflict_only'
        dim_result['hard_conflict'] = False
        dim_result['explanation'] = '类型风险：当前主要为语义回退冲突，缺少足够 typecode 强证据，建议人工复核。'


def _has_high_confidence_negative_existence(evidence_items: List[Dict[str, Any]]) -> bool:
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            continue
        existence_value = data.get('existence')
        if isinstance(existence_value, bool) and existence_value is False:
            if _evidence_confidence(item) >= 0.85:
                return True
    return False


def _count_supporting_existence_items(evidence_items: List[Dict[str, Any]]) -> int:
    count = 0
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        data = item.get('data')
        if not isinstance(data, dict):
            continue
        existence_value = data.get('existence')
        if isinstance(existence_value, bool):
            if existence_value:
                count += 1
            continue
        if isinstance(data.get('name'), str) and data.get('name').strip():
            count += 1
            continue
        if isinstance(data.get('address'), str) and data.get('address').strip():
            count += 1
            continue
    return count


def _apply_existence_semantic_adjustment(dimension_results: Dict[str, Any]) -> None:
    existence_result = dimension_results.get('existence')
    if not isinstance(existence_result, dict):
        return
    if existence_result.get('status') != 'risk':
        return

    name_pass = _dimension_status(dimension_results, 'name') == 'pass'
    support_dim_pass_count = sum(
        1
        for dim_name in ('address', 'location', 'administrative', 'category')
        if _dimension_status(dimension_results, dim_name) == 'pass'
    )
    if not name_pass:
        return
    if support_dim_pass_count < 1:
        return

    evidence = existence_result.get('evidence')
    evidence_items = evidence if isinstance(evidence, list) else []
    if evidence_items and _has_high_confidence_negative_existence(evidence_items):
        return

    support_count = _count_supporting_existence_items(evidence_items)
    if evidence_items and support_count <= 0:
        return

    confidences = _extract_confidences(evidence_items)
    avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    resolved_confidence = max(0.7, avg_confidence)

    existence_result['status'] = 'pass'
    existence_result['risk_level'] = 'none'
    existence_result['confidence'] = round(resolved_confidence, 4)
    existence_result['issue_code'] = 'existence_supported_by_fact_dimensions'
    existence_result['hard_conflict'] = False
    existence_result['explanation'] = (
        '存在性通过：名称与地址/坐标已形成事实支撑，且未发现高置信反证，判定 POI 存在。'
    )


def _is_advisory_risk_dimension(
    dim_name: str,
    dim_result: Dict[str, Any],
    dimension_results: Dict[str, Any],
) -> bool:
    if str(dim_result.get('status') or '').strip() != 'risk':
        return False
    if str(dim_result.get('risk_level') or '').strip().lower() == 'high':
        return False

    issue_code = _normalize_issue_code(dim_result.get('issue_code'))
    advisory_codes = ADVISORY_RISK_ISSUE_CODES.get(dim_name, set())
    if issue_code not in advisory_codes:
        return False

    if dim_name == 'address':
        return not bool(dim_result.get('hard_conflict'))

    if dim_name == 'location':
        evidence = dim_result.get('evidence')
        evidence_items = evidence if isinstance(evidence, list) else []
        distances = _extract_location_distances(evidence_items)
        if not distances:
            return False
        if issue_code == 'coordinate_distance_between_201_and_500':
            return max(distances) <= 500
        if issue_code == 'coordinate_far_outlier_with_close_support':
            return any(distance <= 200 for distance in distances)
        return False

    if dim_name == 'category':
        name_status = _dimension_status(dimension_results, 'name')
        return name_status == 'pass'

    return False


def _apply_advisory_risk_demotion(dimension_results: Dict[str, Any]) -> None:
    for dim_name in CORE_DIMENSIONS:
        dim_result = dimension_results.get(dim_name)
        if not isinstance(dim_result, dict):
            continue
        if not _is_advisory_risk_dimension(dim_name, dim_result, dimension_results):
            continue

        dim_result['status'] = 'pass'
        dim_result['risk_level'] = 'none'
        dim_result['hard_conflict'] = False

        confidence = _safe_float(dim_result.get('confidence'))
        if confidence is None:
            confidence = 0.8
        dim_result['confidence'] = round(max(confidence, 0.8), 4)

        if dim_name == 'address':
            dim_result['issue_code'] = 'address_supported_by_soft_signal'
            dim_result['explanation'] = '地址通过：软匹配场景可由语义同址支撑，不再单独降级为风险。'
        elif dim_name == 'location':
            dim_result['issue_code'] = 'location_supported_by_tolerant_distance_policy'
            dim_result['explanation'] = '坐标通过：偏移属于可容忍区间或离群点被近距离证据簇吸收，无需单独降级。'
        elif dim_name == 'category':
            dim_result['issue_code'] = 'category_supported_by_text_semantics'
            dim_result['explanation'] = '类型通过：中文类目语义可稳定支撑类型一致，不再单独降级为风险。'


def apply_semantic_adjustments(dimension_results: Dict[str, Any]) -> Dict[str, Any]:
    adjusted = copy.deepcopy(dimension_results)
    _apply_location_semantic_adjustment(adjusted)
    _apply_address_semantic_adjustment(adjusted)
    _apply_administrative_semantic_adjustment(adjusted)
    _apply_category_semantic_adjustment(adjusted)
    _apply_existence_semantic_adjustment(adjusted)
    _apply_advisory_risk_demotion(adjusted)
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
    all_core_pass = all(_dimension_status(dimension_results, dim_name) == 'pass' for dim_name in CORE_DIMENSIONS)
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

    if all_core_pass and only_confidence >= 0.8:
        return {
            'status': 'pass',
            'risk_level': 'none',
            'explanation': '证据充分性通过：核心事实维度已全部通过，单条高置信度证据可作为共享支撑，无需重复降级。',
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


def _requires_manual_review_for_dimension(dim_name: str, dim_result: Dict[str, Any]) -> bool:
    status = str(dim_result.get('status') or '').strip()
    if status == 'fail':
        return True
    if status != 'risk':
        return False

    risk_level = str(dim_result.get('risk_level') or '').strip().lower()
    if risk_level == 'high':
        return True

    issue_code = _normalize_issue_code(dim_result.get('issue_code'))
    if issue_code in MANUAL_REVIEW_TRIGGER_ISSUE_CODES:
        return True
    return False


def derive_qc_manual_review_required(dimension_results: Dict[str, Any]) -> bool:
    for dim_name in CORE_DIMENSIONS:
        dim_result = dimension_results.get(dim_name, {})
        if not isinstance(dim_result, dict):
            continue
        if _requires_manual_review_for_dimension(dim_name, dim_result):
            return True

    evidence_sufficiency = dimension_results.get('evidence_sufficiency', {})
    if isinstance(evidence_sufficiency, dict):
        if _requires_manual_review_for_dimension('evidence_sufficiency', evidence_sufficiency):
            return True
    return False


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
        )

    adjusted = apply_semantic_adjustments(normalized)
    adjusted['evidence_sufficiency'] = _derive_evidence_sufficiency(adjusted)
    _recompute_downgrade_consistency(adjusted)
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
    risk_dims: List[str] = []
    for dim_name in ALL_DIMENSIONS:
        if _dimension_status(dimension_results, dim_name) not in RISK_STATUSES:
            continue
        if dim_name == 'downgrade_consistency':
            consistency = dimension_results.get(dim_name)
            issue_type = ''
            if isinstance(consistency, dict):
                issue_type = str(consistency.get('issue_type') or '').strip().lower()
            if issue_type in NON_BLOCKING_DOWNGRADE_ISSUE_TYPES:
                continue
        risk_dims.append(dim_name)
    return risk_dims


def derive_has_risk(dimension_results: Dict[str, Any]) -> bool:
    return len(derive_risk_dims(dimension_results)) > 0


def derive_qc_status(dimension_results: Dict[str, Any]) -> str:
    has_core_fail = any(_dimension_status(dimension_results, dim_name) == 'fail' for dim_name in CORE_DIMENSIONS)
    has_core_risk = any(_dimension_status(dimension_results, dim_name) == 'risk' for dim_name in CORE_DIMENSIONS)
    sufficiency_status = _dimension_status(dimension_results, 'evidence_sufficiency')
    consistency_result = dimension_results.get('downgrade_consistency')
    consistency_status = _dimension_status(dimension_results, 'downgrade_consistency')
    consistency_issue_type = ''
    if isinstance(consistency_result, dict):
        consistency_issue_type = str(consistency_result.get('issue_type') or '').strip().lower()
    consistency_blocks = (
        consistency_status in RISK_STATUSES
        and consistency_issue_type not in NON_BLOCKING_DOWNGRADE_ISSUE_TYPES
    )

    if has_core_fail:
        return 'unqualified'
    if has_core_risk or sufficiency_status in RISK_STATUSES or consistency_blocks:
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

        status = dim_result.get('status')
        if status == 'pass':
            factor = pass_factor
        elif status == 'risk':
            factor = risk_factors.get(dim_result.get('risk_level'), 0.0)
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
    # 运营策略：risky / unqualified 都需要人工查看。
    # 这里用于回库与下游消费，不改变降级一致性维度内部的计算口径。
    manual_required_by_status = resolved_qc_status in {'risky', 'unqualified'}
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
        'is_manual_required': manual_required_by_status,
        'qc_manual_review_required': manual_required_by_status,
        'upstream_manual_review_required': upstream_manual,
        'downgrade_issue_type': issue_type,
    }


def finalize_qc_result(
    qc_result: Dict[str, Any],
    scoring_policy: Optional[Dict[str, Any]] = None,
    scoring_policy_path: Optional[str] = None,
    poi_type_hint: Optional[Any] = None,
    model_judgement: Optional[Dict[str, Any]] = None,
    hybrid_policy: Optional[Dict[str, Any]] = None,
    hybrid_policy_path: Optional[str] = None,
) -> Dict[str, Any]:
    finalized = copy.deepcopy(qc_result or {})
    resolved_poi_type_hint = poi_type_hint
    if resolved_poi_type_hint is None:
        resolved_poi_type_hint = finalized.get('poi_type')
    finalized.pop('poi_type', None)
    finalized.pop('adjudication', None)
    normalized_dimensions = normalize_dimension_results(
        finalized.get('dimension_results', {}),
        poi_type_hint=resolved_poi_type_hint,
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
