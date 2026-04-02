#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证据预处理模块。

职责：
1. 过滤无效证据（is_valid=false、附属点位、政府关联设施非主实体）
2. 统一 source.source_type 到 DSL 可识别枚举
3. 对常用证据字段做轻量补齐，便于规则稳定消费
"""

import ast
import copy
import re
from difflib import SequenceMatcher
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
SUBJECT_TYPE_KEYWORDS = {
    'government': ('人民政府', '政府'),
    'community_committee': ('居委会', '居民委员会', '社区居委会'),
    'village_committee': ('村委会', '村民委员会'),
    'police_station': ('派出所',),
    'police': ('公安局', '公安分局', '公安机关'),
    'court': ('法院', '人民法院'),
    'procuratorate': ('检察院', '人民检察院'),
    'hospital': ('医院', '卫生院', '医疗中心'),
    'school': ('学校', '中学', '小学', '大学', '学院'),
}
GENERIC_SUBJECT_WORDS = (
    '街道',
    '社区',
    '镇',
    '乡',
    '村',
    '广东省',
    '广西',
    '北京市',
    '上海市',
    '天津市',
    '重庆市',
    '自治区',
    '特别行政区',
    '省',
    '市',
    '区',
    '县',
)


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


def _name_similarity(left_name: str, right_name: str) -> float:
    left = _normalize_text(left_name)
    right = _normalize_text(right_name)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    if left in right or right in left:
        ratio = max(ratio, 0.9)
    return max(0.0, min(1.0, float(ratio)))


def _detect_subject_type(name_text: str, category_text: str = '') -> Optional[str]:
    merged = f'{name_text} {category_text}'.strip()
    if not merged:
        return None
    for subject_type, keywords in SUBJECT_TYPE_KEYWORDS.items():
        if _contains_any_keyword(merged, keywords):
            return subject_type
    return None


def _extract_core_subject_anchor(name_text: str) -> str:
    text = str(name_text or '').strip()
    if not text:
        return ''
    for token in GENERIC_SUBJECT_WORDS:
        text = text.replace(token, '')
    for keywords in SUBJECT_TYPE_KEYWORDS.values():
        for keyword in keywords:
            text = text.replace(keyword, '')
    text = re.sub(r'[\s\-\_()（）\[\]【】,，、.;；:：/\\]+', '', text)
    return text


def _is_subject_mismatch(record: Dict[str, Any], evidence: Dict[str, Any]) -> Optional[str]:
    record_name = str(record.get('name') or '')
    data = _copy_json_dict(evidence.get('data'))
    raw_data = _copy_json_dict(data.get('raw_data'))
    raw_core = _copy_json_dict(raw_data.get('data'))
    evidence_name = str(_first_non_empty(data.get('name'), raw_core.get('name')) or '')
    if not record_name or not evidence_name:
        return None

    data_category = str(_first_non_empty(data.get('category'), raw_core.get('type')) or '')
    record_subject = _detect_subject_type(record_name, '')
    evidence_subject = _detect_subject_type(evidence_name, data_category)

    similarity = _name_similarity(record_name, evidence_name)
    record_anchor = _extract_core_subject_anchor(record_name)
    evidence_anchor = _extract_core_subject_anchor(evidence_name)

    if record_subject and evidence_subject and record_subject != evidence_subject:
        # 主体类型明确且冲突时直接过滤，避免“居委会 vs 派出所”误参与维度比较。
        return 'subject_type_mismatch'

    # 无法明确类型时，仍用名称相似度 + 主体锚点做兜底过滤。
    if similarity < 0.45:
        if not record_anchor or not evidence_anchor:
            return 'subject_name_mismatch'
        if record_anchor not in evidence_anchor and evidence_anchor not in record_anchor:
            return 'subject_name_mismatch'
    return None


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

    subject_mismatch_reason = _is_subject_mismatch(record, evidence)
    if subject_mismatch_reason is not None:
        return subject_mismatch_reason

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

    address_value = _first_non_empty(
        data.get('address'),
        _copy_json_dict(data.get('location')).get('address'),
        raw_core.get('address'),
    )
    normalized_address = _normalize_address_text(address_value)
    if normalized_address is not None:
        data['address'] = normalized_address

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
        matching = _copy_json_dict(item.get('matching'))
        if reason in {'subject_type_mismatch', 'subject_name_mismatch'}:
            matching['subject_consistent'] = False
        else:
            data_name = str(_copy_json_dict(item.get('data')).get('name') or '')
            if str(record.get('name') or '').strip() and data_name.strip():
                matching['subject_consistent'] = True
        if matching:
            item['matching'] = matching

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
