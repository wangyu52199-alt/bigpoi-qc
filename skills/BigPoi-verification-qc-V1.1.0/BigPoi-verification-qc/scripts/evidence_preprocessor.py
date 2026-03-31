#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证据预处理模块。

职责：
1. 过滤无效证据（is_valid=false、附属点位、政府关联设施非主实体）
2. 统一 source.source_type 到 DSL 可识别枚举
3. 对常用证据字段做轻量补齐，便于规则稳定消费
"""

import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


ANCILLARY_NAME_KEYWORDS = (
    '东门',
    '西门',
    '南门',
    '北门',
    '正门',
    '后门',
    '侧门',
    '北侧门',
    '南侧门',
    '入口',
    '出口',
    '出入口',
    '停车场',
    '地下停车场',
    '停车楼',
    '门岗',
    '门卫',
)
GOVERNMENT_MAIN_ENTITY_KEYWORDS = ('人民政府', '政府')
GOVERNMENT_AFFILIATED_FACILITY_KEYWORDS = (
    '政务中心',
    '政务服务中心',
    '办事大厅',
    '便民服务中心',
    '市民中心',
    '服务中心',
)
SOURCE_TYPE_ALIAS_GROUPS = {
    'business_license': (
        'business_license',
        'businesslicense',
        '营业执照',
        '营业执照信息',
        '企业营业执照',
        '执照',
    ),
    'official_registry': (
        'official_registry',
        'officialregistry',
        '工商登记',
        '工商注册',
        '登记信息',
        '注册信息',
        '国家企业信用信息公示系统',
        '企查查',
        '天眼查',
    ),
    'government': (
        'government',
        'gov',
        '政府',
        '政府官网',
        '政府网站',
        '政府机关',
        '政务公开',
    ),
    'official_data': (
        'official_data',
        'officialdata',
        'official',
        '官网',
        '官方网站',
        '官方',
        '官方数据',
    ),
    'map_data': (
        'map_data',
        'mapdata',
        'map',
        'map_vendor',
        '地图',
        '地图数据',
        '地图平台',
    ),
    'platform': (
        'platform',
        '互联网平台',
        '平台',
    ),
    'ota': (
        'ota',
        'ota平台',
        '旅游平台',
        '携程',
        '去哪儿',
        '飞猪',
        '同程',
    ),
    'merchant': (
        'merchant',
        '商户',
        '商户自报',
    ),
    'ugc': (
        'ugc',
        '用户生成',
        '用户上传',
    ),
    'review': (
        'review',
        '点评',
        '评论',
        '评价',
    ),
    'unknown': (
        'unknown',
        '未知',
    ),
}
MAP_SOURCE_HINTS = ('高德', '百度地图', '腾讯地图', 'amap', 'map.baidu', 'qqmap', 'map.qq')
GOVERNMENT_SOURCE_HINTS = ('政府', '人民政府', 'gov.cn', '政务')
REGISTRY_SOURCE_HINTS = ('国家企业信用信息公示系统', '企查查', '天眼查', '市场监督')
OTA_SOURCE_HINTS = ('携程', '去哪儿', '飞猪', '同程', 'ctrip', 'qunar', 'fliggy', 'ly.com')
REVIEW_SOURCE_HINTS = ('大众点评', '点评', '评价', '评论', 'dianping')
PLATFORM_SOURCE_HINTS = ('美团', '抖音', '快手', 'meituan', 'douyin', 'kuaishou')


def _copy_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return {}


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == '':
            continue
        return value
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_probability(value: Any, default: float = 0.5) -> float:
    number = _to_float(value)
    if number is None:
        return default
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def _parse_location_string(value: Any) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(value, str):
        return None, None
    parts = [part.strip() for part in value.split(',')]
    if len(parts) != 2:
        return None, None
    return _to_float(parts[0]), _to_float(parts[1])


def _normalize_text(value: Any) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    return re.sub(r'[\s\-\_()（）\[\]【】,，、.;；:：/\\]+', '', text)


def _normalize_source_type_text(value: Any) -> str:
    return _normalize_text(value)


def _contains_any_keyword(text: str, keywords: Tuple[str, ...]) -> bool:
    normalized_text = str(text or '').lower()
    return any(str(keyword).lower() in normalized_text for keyword in keywords)


def normalize_source_type(source: Dict[str, Any]) -> str:
    raw_source_type = str(_first_non_empty(source.get('source_type'), '') or '')
    normalized_type = _normalize_source_type_text(raw_source_type)
    source_name = str(_first_non_empty(source.get('source_name'), '') or '')
    source_url = str(_first_non_empty(source.get('source_url'), '') or '').lower()

    for canonical, aliases in SOURCE_TYPE_ALIAS_GROUPS.items():
        alias_set = {_normalize_source_type_text(alias) for alias in aliases}
        if normalized_type in alias_set:
            if canonical == 'official_data':
                if _contains_any_keyword(source_name, REGISTRY_SOURCE_HINTS) or any(
                    hint in source_url for hint in ('gsxt.gov.cn', 'qcc.com', 'tianyancha.com')
                ):
                    return 'official_registry'
                if _contains_any_keyword(source_name, GOVERNMENT_SOURCE_HINTS) or 'gov.cn' in source_url:
                    return 'government'
            return canonical

    if _contains_any_keyword(source_name, MAP_SOURCE_HINTS) or any(
        hint in source_url for hint in ('amap.com', 'map.baidu.com', 'map.qq.com')
    ):
        return 'map_data'
    if _contains_any_keyword(source_name, REGISTRY_SOURCE_HINTS) or any(
        hint in source_url for hint in ('gsxt.gov.cn', 'qcc.com', 'tianyancha.com')
    ):
        return 'official_registry'
    if _contains_any_keyword(source_name, OTA_SOURCE_HINTS) or any(
        hint in source_url for hint in ('ctrip.com', 'qunar.com', 'fliggy.com', 'ly.com')
    ):
        return 'ota'
    if _contains_any_keyword(source_name, REVIEW_SOURCE_HINTS) or 'dianping.com' in source_url:
        return 'review'
    if _contains_any_keyword(source_name, PLATFORM_SOURCE_HINTS) or any(
        hint in source_url for hint in ('meituan.com', 'douyin.com', 'kuaishou.com')
    ):
        return 'platform'
    if _contains_any_keyword(source_name, GOVERNMENT_SOURCE_HINTS) or 'gov.cn' in source_url:
        return 'government'
    if raw_source_type.strip():
        return raw_source_type.strip()
    return 'unknown'


def _strip_ancillary_suffix(name: str) -> str:
    stripped = name
    changed = True
    while changed and stripped:
        changed = False
        for keyword in sorted(ANCILLARY_NAME_KEYWORDS, key=len, reverse=True):
            if stripped.endswith(keyword):
                stripped = stripped[: -len(keyword)]
                changed = True
                break
    return stripped


def _invalid_evidence_reason(record: Dict[str, Any], evidence: Dict[str, Any]) -> Optional[str]:
    verification = _copy_json_dict(evidence.get('verification'))
    if not bool(verification.get('is_valid', True)):
        return 'verification_marked_invalid'

    record_name = str(_copy_json_dict(record).get('name') or '')
    evidence_name = str(_copy_json_dict(evidence.get('data')).get('name') or '')
    if not record_name or not evidence_name:
        return None

    normalized_record_name = _normalize_text(record_name)
    normalized_evidence_name = _normalize_text(evidence_name)
    if not normalized_record_name or not normalized_evidence_name:
        return None
    if normalized_record_name == normalized_evidence_name:
        return None

    if _strip_ancillary_suffix(normalized_evidence_name) == normalized_record_name:
        return 'ancillary_entry_or_facility_name'

    if (
        _contains_any_keyword(record_name, GOVERNMENT_MAIN_ENTITY_KEYWORDS)
        and _contains_any_keyword(evidence_name, GOVERNMENT_AFFILIATED_FACILITY_KEYWORDS)
        and normalized_record_name not in normalized_evidence_name
    ):
        return 'government_affiliated_facility_not_primary_entity'

    return None


def _normalize_evidence_item(item: Dict[str, Any]) -> Dict[str, Any]:
    evidence = copy.deepcopy(item)
    source = _copy_json_dict(evidence.get('source'))
    data = _copy_json_dict(evidence.get('data'))
    verification = _copy_json_dict(evidence.get('verification'))
    raw_data = _copy_json_dict(data.get('raw_data'))
    raw_core = _copy_json_dict(raw_data.get('data'))

    source['source_type'] = normalize_source_type(source)
    evidence['source'] = source

    verification['is_valid'] = bool(verification.get('is_valid', True))
    confidence = _to_probability(verification.get('confidence'), default=source.get('weight') or 0.5)
    verification['confidence'] = confidence
    evidence['verification'] = verification

    address_value = _first_non_empty(data.get('address'), _copy_json_dict(data.get('location')).get('address'), raw_core.get('address'))
    if address_value is not None:
        data['address'] = str(address_value)

    coordinates = _copy_json_dict(data.get('coordinates'))
    location = _copy_json_dict(data.get('location'))
    lon = _first_non_empty(coordinates.get('longitude'), location.get('longitude'))
    lat = _first_non_empty(coordinates.get('latitude'), location.get('latitude'))
    if lon is None or lat is None:
        parsed_lon, parsed_lat = _parse_location_string(raw_core.get('location'))
        lon = _first_non_empty(lon, parsed_lon)
        lat = _first_non_empty(lat, parsed_lat)
    lon_value = _to_float(lon)
    lat_value = _to_float(lat)
    if lon_value is not None and lat_value is not None:
        data['coordinates'] = {'longitude': lon_value, 'latitude': lat_value}

    if _first_non_empty(data.get('name'), raw_core.get('name')) is not None:
        data['name'] = str(_first_non_empty(data.get('name'), raw_core.get('name')))

    admin = _copy_json_dict(data.get('administrative'))
    city_value = _first_non_empty(
        admin.get('city'),
        raw_data.get('cityname'),
        raw_core.get('cityname'),
        raw_data.get('adname'),
    )
    if city_value is not None:
        admin['city'] = str(city_value)
    if admin:
        data['administrative'] = admin

    evidence['data'] = data
    return evidence


def preprocess_evidence_record(record: Dict[str, Any], evidence_record: Iterable[Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    retained: List[Dict[str, Any]] = []
    filtered: List[Dict[str, Any]] = []
    raw_items = list(evidence_record) if not isinstance(evidence_record, list) else evidence_record

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            filtered.append({'evidence_id': '', 'reason': 'invalid_evidence_payload', 'name': ''})
            continue

        item = _normalize_evidence_item(raw_item)
        reason = _invalid_evidence_reason(record, item)
        if reason is None:
            retained.append(item)
            continue
        filtered.append(
            {
                'evidence_id': str(_first_non_empty(item.get('evidence_id'), '')),
                'reason': reason,
                'name': str(_copy_json_dict(item.get('data')).get('name') or ''),
            }
        )

    summary = {
        'input_evidence_count': len(raw_items),
        'retained_evidence_count': len(retained),
        'filtered_evidence_count': len(filtered),
        'filtered_evidence': filtered,
    }
    return retained, summary


def preprocess_flat_input(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    normalized = copy.deepcopy(payload or {})
    record = {'name': str(normalized.get('name') or '')}
    evidence_record = normalized.get('evidence_record')
    if not isinstance(evidence_record, list):
        summary = {
            'input_evidence_count': 0,
            'retained_evidence_count': 0,
            'filtered_evidence_count': 0,
            'filtered_evidence': [],
        }
        normalized['evidence_record'] = []
        return normalized, summary

    retained, summary = preprocess_evidence_record(record, evidence_record)
    normalized['evidence_record'] = retained
    return normalized, summary

