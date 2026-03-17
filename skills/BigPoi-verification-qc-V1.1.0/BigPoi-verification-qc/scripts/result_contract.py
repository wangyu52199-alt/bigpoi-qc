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
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def _project_evidence_item(dim_name: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
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
    elif dim_name == 'evidence_sufficiency':
        projected_data = {}
    else:
        projected_data = copy.deepcopy(data)

    if projected_data:
        projected['data'] = projected_data

    return projected


def _project_dimension_evidence(dim_name: str, evidence_items: Any) -> List[Dict[str, Any]]:
    if not isinstance(evidence_items, list):
        return []
    projected_items = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        projected_item = _project_evidence_item(dim_name, item)
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


def normalize_dimension_results(dimension_results: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(dimension_results or {})

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
        dim_result['evidence'] = _project_dimension_evidence(dim_name, dim_result.get('evidence'))

    consistency = normalized.get('downgrade_consistency')
    if isinstance(consistency, dict):
        qc_manual = derive_qc_manual_review_required(normalized)
        consistency['qc_manual_review_required'] = qc_manual

        upstream_manual = consistency.get('upstream_manual_review_required')
        if isinstance(upstream_manual, bool):
            is_consistent = qc_manual == upstream_manual
            consistency['is_consistent'] = is_consistent
            consistency['issue_type'] = derive_downgrade_issue_type(qc_manual, upstream_manual)
            consistency['status'] = 'pass' if is_consistent else 'fail'
            consistency['risk_level'] = 'none' if is_consistent else 'high'
            consistency['explanation'] = _default_downgrade_explanation(qc_manual, upstream_manual)
        consistency['related_rules'] = ['R7']

    return normalized


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
    qc_manual = derive_qc_manual_review_required(dimension_results)
    consistency_result = dimension_results.get('downgrade_consistency', {})
    upstream_manual = None
    issue_type = None
    if isinstance(consistency_result, dict):
        upstream_manual = consistency_result.get('upstream_manual_review_required')
        issue_type = consistency_result.get('issue_type')

    return {
        'is_qualified': resolved_qc_status == 'qualified',
        'is_auto_approvable': resolved_qc_status == 'qualified',
        'is_manual_required': qc_manual,
        'qc_manual_review_required': qc_manual,
        'upstream_manual_review_required': upstream_manual,
        'downgrade_issue_type': issue_type,
    }


def finalize_qc_result(
    qc_result: Dict[str, Any],
    scoring_policy: Optional[Dict[str, Any]] = None,
    scoring_policy_path: Optional[str] = None,
) -> Dict[str, Any]:
    finalized = copy.deepcopy(qc_result or {})
    normalized_dimensions = normalize_dimension_results(finalized.get('dimension_results', {}))
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
