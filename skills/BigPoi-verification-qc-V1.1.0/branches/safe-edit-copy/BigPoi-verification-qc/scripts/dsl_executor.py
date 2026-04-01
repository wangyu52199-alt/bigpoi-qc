#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSL 核心维度执行器。

作用：
1. 对平铺输入执行证据预处理
2. 按 decision_tables.json 计算 6 个核心维度（R1-R6）
3. 输出可直接交给 finalize 的 dimension_results
"""

import argparse
import copy
import json
import math
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from evidence_preprocessor import preprocess_flat_input  # noqa: E402
from inject_category_fallback import enrich_payload as inject_category_fallback  # noqa: E402
from poi_type_mapping import load_mapping  # noqa: E402


CORE_DIMENSIONS = ('existence', 'name', 'location', 'address', 'administrative', 'category')
DEFAULT_DSL_PATH = SCRIPT_DIR.parent / 'rules' / 'decision_tables.json'
DEFAULT_MAPPING_PATH = SCRIPT_DIR.parent / 'config' / 'poi_type_mapping.json'
BRANCH_SUFFIX_KEYWORDS = (
    '分店',
    '门店',
    '旗舰店',
    '东门',
    '西门',
    '南门',
    '北门',
    '政务中心',
    '办事大厅',
    '便民服务中心',
)
ADMIN_PREFIX_PATTERN = re.compile(
    r'^(?:中国|[\u4e00-\u9fff]{2,9}(?:省|市|自治区|特别行政区|地区|盟|自治州|州|县|区|镇|乡|街道))+'
)
ROAD_PATTERN = re.compile(r'([A-Za-z0-9\u4e00-\u9fff]{1,24}(?:路|街|巷|大道|国道|省道|县道|道))')
HOUSE_NUMBER_PATTERN = re.compile(r'(\d+)\s*号')
ROAD_CODE_PATTERN = re.compile(r'([gs]\d{2,4})', re.IGNORECASE)
CITY_PATTERN = re.compile(r'([\u4e00-\u9fff]{1,12}市)')


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f'JSON 根节点必须是对象：{path}')
    return payload


def _copy_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return {}


def _get_by_path(obj: Any, path: str) -> Any:
    current = obj
    for token in path.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(token)
    return current


def _set_by_path(obj: Dict[str, Any], path: str, value: Any) -> None:
    tokens = path.split('.')
    cursor = obj
    for token in tokens[:-1]:
        child = cursor.get(token)
        if not isinstance(child, dict):
            child = {}
            cursor[token] = child
        cursor = child
    cursor[tokens[-1]] = value


def _normalize_text(value: Any) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    return re.sub(r'[\s\-\_()（）\[\]【】,，、.;；:：/\\]+', '', text)


def _normalize_address_for_compare(text: str) -> str:
    normalized = str(text or '').strip().lower()
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
    normalized = normalized.replace('大道', '路')
    normalized = normalized.replace('国道', 'g')
    normalized = re.sub(r'g\s*(\d+)', r'g\1', normalized)
    normalized = re.sub(r'(\d+)g', r'g\1', normalized)
    return normalized


def _extract_city(address: str) -> Optional[str]:
    match = CITY_PATTERN.search(str(address or ''))
    if not match:
        return None
    return match.group(1)


def _extract_house_number(address: str) -> Optional[str]:
    match = HOUSE_NUMBER_PATTERN.search(str(address or ''))
    if not match:
        return None
    return match.group(1)


def _extract_road_anchor(address: str) -> Optional[str]:
    match = ROAD_PATTERN.search(str(address or ''))
    if not match:
        return None
    return _normalize_address_for_compare(match.group(1))


def _extract_road_code(address: str) -> Optional[str]:
    normalized = _normalize_address_for_compare(str(address or ''))
    match = ROAD_CODE_PATTERN.search(normalized)
    if not match:
        return None
    return match.group(1).lower()


def _strip_admin_prefix(address: str) -> str:
    text = str(address or '').strip()
    return ADMIN_PREFIX_PATTERN.sub('', text)


def _address_match_level(record_address: str, evidence_address: str) -> str:
    record_text = str(record_address or '').strip()
    evidence_text = str(evidence_address or '').strip()
    if not record_text or not evidence_text:
        return 'ambiguous'

    record_city = _extract_city(record_text)
    evidence_city = _extract_city(evidence_text)
    if record_city and evidence_city and record_city != evidence_city:
        return 'city_district_conflict'

    record_house = _extract_house_number(record_text)
    evidence_house = _extract_house_number(evidence_text)
    if record_house and evidence_house and record_house != evidence_house:
        return 'house_number_conflict'

    normalized_record = _normalize_address_for_compare(record_text)
    normalized_evidence = _normalize_address_for_compare(evidence_text)
    if normalized_record == normalized_evidence:
        return 'exact'

    record_code = _extract_road_code(record_text)
    evidence_code = _extract_road_code(evidence_text)
    if record_code and evidence_code and record_code == evidence_code and (
        record_house == evidence_house or not record_house or not evidence_house
    ):
        return 'exact'

    record_road = _extract_road_anchor(record_text)
    evidence_road = _extract_road_anchor(evidence_text)
    if record_road and evidence_road and record_road != evidence_road:
        return 'street_conflict'

    record_core = _normalize_address_for_compare(_strip_admin_prefix(record_text))
    evidence_core = _normalize_address_for_compare(_strip_admin_prefix(evidence_text))
    if record_core and evidence_core and (record_core in evidence_core or evidence_core in record_core):
        branch_hit = any(keyword in evidence_text for keyword in BRANCH_SUFFIX_KEYWORDS) or any(
            keyword in record_text for keyword in BRANCH_SUFFIX_KEYWORDS
        )
        if branch_hit:
            return 'branch_suffix_only'
        return 'main_address_only'

    if record_road and evidence_road and record_road == evidence_road and (not record_house or not evidence_house):
        return 'missing_house_number'

    return 'ambiguous'


def _name_similarity(record_name: str, evidence_name: str) -> float:
    left = _normalize_text(record_name)
    right = _normalize_text(evidence_name)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    ratio = SequenceMatcher(None, left, right).ratio()
    if left in right or right in left:
        ratio = max(ratio, 0.9)
    return round(min(max(ratio, 0.0), 1.0), 4)


def _haversine_meters(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371000.0
    lon1_r = math.radians(lon1)
    lat1_r = math.radians(lat1)
    lon2_r = math.radians(lon2)
    lat2_r = math.radians(lat2)
    dlon = lon2_r - lon1_r
    dlat = lat2_r - lat1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def _extract_evidence_coordinates(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    coordinates = _copy_dict(data.get('coordinates'))
    location = _copy_dict(data.get('location'))
    raw_data = _copy_dict(data.get('raw_data'))
    raw_core = _copy_dict(raw_data.get('data'))

    lon = coordinates.get('longitude')
    lat = coordinates.get('latitude')
    if lon is None or lat is None:
        lon = location.get('longitude')
        lat = location.get('latitude')
    if lon is None or lat is None:
        location_text = raw_core.get('location') if isinstance(raw_core, dict) else None
        if isinstance(location_text, str) and ',' in location_text:
            parts = [part.strip() for part in location_text.split(',')]
            if len(parts) == 2:
                lon = lon if lon is not None else parts[0]
                lat = lat if lat is not None else parts[1]
    return _safe_float(lon), _safe_float(lat)


def _enrich_evidence_for_metrics(payload: Dict[str, Any]) -> None:
    record_name = str(payload.get('name') or '')
    record_lon = _safe_float(payload.get('x_coord'))
    record_lat = _safe_float(payload.get('y_coord'))
    evidence_record = payload.get('evidence_record')
    if not isinstance(evidence_record, list):
        return

    for evidence in evidence_record:
        if not isinstance(evidence, dict):
            continue
        data = _copy_dict(evidence.get('data'))
        matching = _copy_dict(evidence.get('matching'))

        if data.get('address') is None:
            location = _copy_dict(data.get('location'))
            address_value = location.get('address')
            if address_value is not None:
                data['address'] = str(address_value)

        if data.get('coordinates') is None:
            lon, lat = _extract_evidence_coordinates(data)
            if lon is not None and lat is not None:
                data['coordinates'] = {'longitude': lon, 'latitude': lat}

        if data.get('administrative') is None:
            data['administrative'] = {}
        admin = _copy_dict(data.get('administrative'))
        if admin.get('city') is None:
            raw_data = _copy_dict(data.get('raw_data'))
            raw_core = _copy_dict(raw_data.get('data'))
            city_value = raw_data.get('cityname') if raw_data.get('cityname') is not None else raw_core.get('cityname')
            if city_value is not None:
                admin['city'] = str(city_value)
        data['administrative'] = admin

        evidence_name = str(data.get('name') or '')
        if evidence_name and matching.get('name_similarity') is None:
            matching['name_similarity'] = _name_similarity(record_name, evidence_name)

        if matching.get('location_distance') is None and record_lon is not None and record_lat is not None:
            ev_lon, ev_lat = _extract_evidence_coordinates(data)
            if ev_lon is not None and ev_lat is not None:
                matching['location_distance'] = round(_haversine_meters(record_lon, record_lat, ev_lon, ev_lat), 4)

        evidence['data'] = data
        evidence['matching'] = matching


def _select_items(selector: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if selector == 'evidence_record[]':
        data = payload.get('evidence_record')
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []
    return []


def _resolve_ref(
    ref: str,
    payload: Dict[str, Any],
    evidence: Optional[Dict[str, Any]],
    metrics: Dict[str, Any],
    dimension_results: Dict[str, Any],
    derived: Dict[str, Any],
) -> Any:
    if ref.startswith('metric.'):
        return metrics.get(ref[7:])
    if ref.startswith('evidence.'):
        if evidence is None:
            return None
        return _get_by_path(evidence, ref[9:])
    if ref.startswith('dimension.'):
        return _get_by_path(dimension_results, ref[10:])
    if ref.startswith('derived.'):
        return _get_by_path(derived, ref[8:])
    if ref.startswith('record.'):
        return _get_by_path(payload, ref[7:])
    return _get_by_path(payload, ref)


def _resolve_value(
    value_spec: Any,
    payload: Dict[str, Any],
    evidence: Optional[Dict[str, Any]],
    metrics: Dict[str, Any],
    dimension_results: Dict[str, Any],
    derived: Dict[str, Any],
) -> Any:
    if isinstance(value_spec, dict) and 'ref' in value_spec:
        return _resolve_ref(str(value_spec.get('ref') or ''), payload, evidence, metrics, dimension_results, derived)
    return value_spec


def _evaluate_condition(
    condition: Any,
    payload: Dict[str, Any],
    evidence: Optional[Dict[str, Any]],
    metrics: Dict[str, Any],
    dimension_results: Dict[str, Any],
    derived: Dict[str, Any],
) -> bool:
    if condition is None:
        return True
    if not isinstance(condition, dict):
        return bool(condition)
    if 'all' in condition:
        items = condition.get('all')
        return isinstance(items, list) and all(
            _evaluate_condition(item, payload, evidence, metrics, dimension_results, derived) for item in items
        )
    if 'any' in condition:
        items = condition.get('any')
        return isinstance(items, list) and any(
            _evaluate_condition(item, payload, evidence, metrics, dimension_results, derived) for item in items
        )
    if 'not' in condition:
        return not _evaluate_condition(condition.get('not'), payload, evidence, metrics, dimension_results, derived)

    op = str(condition.get('op') or '').strip()
    left = _resolve_value(condition.get('left'), payload, evidence, metrics, dimension_results, derived)
    right = _resolve_value(condition.get('right'), payload, evidence, metrics, dimension_results, derived)

    if op == 'exists':
        return left is not None and left != ''
    if op == 'eq':
        return left == right
    if op == 'ne':
        return left != right
    if op == 'lt':
        return left is not None and right is not None and left < right
    if op == 'lte':
        return left is not None and right is not None and left <= right
    if op == 'gt':
        return left is not None and right is not None and left > right
    if op == 'gte':
        return left is not None and right is not None and left >= right
    if op == 'between':
        lower = _resolve_value(condition.get('lower'), payload, evidence, metrics, dimension_results, derived)
        upper = _resolve_value(condition.get('upper'), payload, evidence, metrics, dimension_results, derived)
        return left is not None and lower is not None and upper is not None and lower <= left <= upper
    if op == 'in':
        return isinstance(right, list) and left in right
    if op == 'contains':
        if isinstance(left, str):
            return str(right or '') in left
        if isinstance(left, list):
            return right in left
        return False
    return False


def _match_level_address(record_value: Any, evidence_value: Any) -> str:
    return _address_match_level(str(record_value or ''), str(evidence_value or ''))


def _evaluate_match_level(
    params: Dict[str, Any],
    payload: Dict[str, Any],
    evidence: Dict[str, Any],
    metrics: Dict[str, Any],
    dimension_results: Dict[str, Any],
    derived: Dict[str, Any],
) -> Optional[str]:
    fn_name = str(params.get('match_function') or '').strip()
    if fn_name != 'address_match_level':
        return None

    record_selector = params.get('record_selector')
    evidence_selector = params.get('evidence_selector')
    if not isinstance(record_selector, str) or not isinstance(evidence_selector, str):
        return None

    record_value = _resolve_ref(record_selector, payload, evidence, metrics, dimension_results, derived)
    evidence_ref = evidence_selector
    if not evidence_ref.startswith('evidence.'):
        evidence_ref = f'evidence.{evidence_ref}'
    evidence_value = _resolve_ref(evidence_ref, payload, evidence, metrics, dimension_results, derived)
    level = _match_level_address(record_value, evidence_value)
    matching = _copy_dict(evidence.get('matching'))
    matching['address_match_level'] = level
    evidence['matching'] = matching
    return level


def _compute_metric(
    metric_cfg: Dict[str, Any],
    payload: Dict[str, Any],
    dimension_results: Dict[str, Any],
    derived: Dict[str, Any],
    metrics: Dict[str, Any],
) -> Any:
    fn_name = metric_cfg.get('function')
    selector = str(metric_cfg.get('selector') or '')
    items = _select_items(selector, payload)
    where = metric_cfg.get('where')

    if fn_name == 'count':
        return sum(
            1
            for evidence in items
            if _evaluate_condition(where, payload, evidence, metrics, dimension_results, derived)
        )

    if fn_name == 'avg':
        field = str(metric_cfg.get('field') or '')
        values: List[float] = []
        for evidence in items:
            if not _evaluate_condition(where, payload, evidence, metrics, dimension_results, derived):
                continue
            value = _resolve_ref(field, payload, evidence, metrics, dimension_results, derived)
            value_float = _safe_float(value)
            if value_float is None:
                continue
            values.append(value_float)
        if not values:
            return 0.0
        return round(sum(values) / len(values), 6)

    if fn_name == 'max':
        field = str(metric_cfg.get('field') or '')
        values: List[float] = []
        for evidence in items:
            if not _evaluate_condition(where, payload, evidence, metrics, dimension_results, derived):
                continue
            value = _resolve_ref(field, payload, evidence, metrics, dimension_results, derived)
            value_float = _safe_float(value)
            if value_float is None:
                continue
            values.append(value_float)
        if not values:
            return 0.0
        return max(values)

    if fn_name == 'count_match_level':
        params = _copy_dict(metric_cfg.get('params'))
        levels = params.get('levels')
        if not isinstance(levels, list):
            levels = []
        expected_levels = {str(level).strip() for level in levels if str(level).strip()}
        count = 0
        for evidence in items:
            if not _evaluate_condition(where, payload, evidence, metrics, dimension_results, derived):
                continue
            level = _evaluate_match_level(params, payload, evidence, metrics, dimension_results, derived)
            if level in expected_levels:
                count += 1
        return count

    return 0


def _evaluate_outcome(
    dimension_cfg: Dict[str, Any],
    payload: Dict[str, Any],
    metrics: Dict[str, Any],
    dimension_results: Dict[str, Any],
    derived: Dict[str, Any],
) -> Dict[str, Any]:
    evaluation = _copy_dict(dimension_cfg.get('evaluation'))
    order = evaluation.get('order')
    outcomes = dimension_cfg.get('outcomes')
    if not isinstance(order, list):
        order = ['fail', 'risk', 'pass']
    if not isinstance(outcomes, list):
        outcomes = []

    for status in order:
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            if outcome.get('status') != status:
                continue
            when = outcome.get('when')
            if _evaluate_condition(when, payload, None, metrics, dimension_results, derived):
                return outcome

    for outcome in outcomes:
        if isinstance(outcome, dict) and outcome.get('status') == 'pass':
            return outcome
    return {
        'id': 'default_fallback',
        'status': 'risk',
        'risk_level': 'medium',
        'issue_code': 'no_outcome_matched',
        'trigger_rule': dimension_cfg.get('rule_id'),
        'explanation_template': '未命中明确分支，按风险处理。',
        'evidence_policy': {'mode': 'filter', 'selector': 'evidence_record[]', 'max_items': 5},
    }


def _select_evidence_by_policy(
    policy: Any,
    payload: Dict[str, Any],
    metrics: Dict[str, Any],
    dimension_results: Dict[str, Any],
    derived: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(policy, dict):
        return []
    if policy.get('mode') != 'filter':
        return []

    selector = str(policy.get('selector') or '')
    where = policy.get('where')
    max_items = policy.get('max_items')
    max_items_value = int(max_items) if isinstance(max_items, int) and max_items >= 0 else 5
    selected: List[Dict[str, Any]] = []
    for evidence in _select_items(selector, payload):
        if _evaluate_condition(where, payload, evidence, metrics, dimension_results, derived):
            selected.append(copy.deepcopy(evidence))

    # location 场景优先保留近距离证据，避免证据截断导致“离群点主导”。
    def _location_sort_key(item: Dict[str, Any]) -> Tuple[float, float]:
        matching = _copy_dict(item.get('matching'))
        distance = _safe_float(matching.get('location_distance'))
        similarity = _safe_float(matching.get('name_similarity'))
        if distance is None:
            distance = float('inf')
        if similarity is None:
            similarity = 0.0
        return (distance, -similarity)

    if any(
        _safe_float(_copy_dict(item.get('matching')).get('location_distance')) is not None
        for item in selected
    ):
        selected.sort(key=_location_sort_key)

    return selected[:max_items_value]


def _derive_result_confidence(evidence: List[Dict[str, Any]], fallback: float = 0.0) -> float:
    values: List[float] = []
    for item in evidence:
        verification = _copy_dict(item.get('verification'))
        confidence = _safe_float(verification.get('confidence'))
        if confidence is None:
            continue
        values.append(max(0.0, min(1.0, confidence)))
    if not values:
        return round(max(0.0, min(1.0, fallback)), 4)
    return round(sum(values) / len(values), 4)


def _build_dimension_result(
    dimension_name: str,
    dimension_cfg: Dict[str, Any],
    outcome: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    result = {
        'status': str(outcome.get('status') or 'risk'),
        'risk_level': str(outcome.get('risk_level') or 'medium'),
        'explanation': str(outcome.get('explanation_template') or f'{dimension_name} 判定完成。'),
        'related_rules': [str(dimension_cfg.get('rule_id') or outcome.get('trigger_rule') or '')],
        'evidence': evidence,
    }
    issue_code = outcome.get('issue_code')
    if isinstance(issue_code, str) and issue_code.strip():
        result['issue_code'] = issue_code.strip()
        if 'conflict' in result['issue_code']:
            result['hard_conflict'] = True

    default_conf = _safe_float(metrics.get('average_confidence'))
    if default_conf is None:
        default_conf = 0.0
    result['confidence'] = _derive_result_confidence(evidence, fallback=default_conf)
    return result


def _prepare_payload(raw_input: Dict[str, Any], preprocess: bool) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload = copy.deepcopy(raw_input or {})
    preprocess_summary: Dict[str, Any] = {
        'input_evidence_count': 0,
        'retained_evidence_count': 0,
        'filtered_evidence_count': 0,
        'filtered_evidence': [],
    }
    if preprocess:
        payload, preprocess_summary = preprocess_flat_input(payload)

    try:
        mapping = load_mapping(str(DEFAULT_MAPPING_PATH))
        payload = inject_category_fallback(payload, mapping)
    except Exception:
        pass
    _enrich_evidence_for_metrics(payload)
    return payload, preprocess_summary


def execute_core_dimensions(
    raw_input: Dict[str, Any],
    dsl_path: Optional[str] = None,
    preprocess: bool = True,
) -> Dict[str, Any]:
    dsl_file = Path(dsl_path) if dsl_path else DEFAULT_DSL_PATH
    dsl = _load_json(dsl_file)
    dimensions_cfg = _copy_dict(dsl.get('dimensions'))
    payload, preprocess_summary = _prepare_payload(raw_input, preprocess=preprocess)

    dimension_results: Dict[str, Any] = {}
    metrics_by_dimension: Dict[str, Dict[str, Any]] = {}
    derived: Dict[str, Any] = {}

    for dimension_name in CORE_DIMENSIONS:
        dimension_cfg = _copy_dict(dimensions_cfg.get(dimension_name))
        if not dimension_cfg:
            continue
        metrics_cfg = dimension_cfg.get('metrics')
        if not isinstance(metrics_cfg, list):
            metrics_cfg = []
        metrics: Dict[str, Any] = {}
        for metric_cfg in metrics_cfg:
            if not isinstance(metric_cfg, dict):
                continue
            metric_name = str(metric_cfg.get('name') or '').strip()
            if not metric_name:
                continue
            metrics[metric_name] = _compute_metric(
                metric_cfg,
                payload,
                dimension_results=dimension_results,
                derived=derived,
                metrics=metrics,
            )
        metrics_by_dimension[dimension_name] = metrics

        outcome = _evaluate_outcome(
            dimension_cfg,
            payload,
            metrics=metrics,
            dimension_results=dimension_results,
            derived=derived,
        )
        evidence = _select_evidence_by_policy(
            outcome.get('evidence_policy'),
            payload,
            metrics=metrics,
            dimension_results=dimension_results,
            derived=derived,
        )
        dimension_results[dimension_name] = _build_dimension_result(
            dimension_name,
            dimension_cfg,
            outcome=outcome,
            evidence=evidence,
            metrics=metrics,
        )

    return {
        'dimension_results': dimension_results,
        'metrics': metrics_by_dimension,
        'preprocess_summary': preprocess_summary,
        'payload': payload,
    }


def _read_payload(path: Optional[str]) -> Dict[str, Any]:
    if path:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    return json.load(sys.stdin)


def _write_payload(payload: Dict[str, Any], path: Optional[str]) -> None:
    if path:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description='执行 BigPOI 核心维度 DSL 判定（R1-R6）')
    parser.add_argument('--input', help='输入 JSON 文件路径；不传则从 stdin 读取')
    parser.add_argument('--output', help='输出 JSON 文件路径；不传则输出到 stdout')
    parser.add_argument(
        '--dsl',
        default=str(DEFAULT_DSL_PATH),
        help='decision_tables.json 路径',
    )
    parser.add_argument(
        '--no-preprocess',
        action='store_true',
        help='跳过 evidence 预处理（默认会执行预处理）',
    )
    args = parser.parse_args()

    payload = _read_payload(args.input)
    result = execute_core_dimensions(
        payload,
        dsl_path=args.dsl,
        preprocess=not args.no_preprocess,
    )
    _write_payload(result, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
