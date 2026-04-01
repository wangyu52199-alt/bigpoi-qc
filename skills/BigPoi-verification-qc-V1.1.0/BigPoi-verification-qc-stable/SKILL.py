#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BigPOI QC Skill v2.4.10-stable - 单入口执行器

固定流程：
1. 优先按 DSL 重算核心维度（R1-R6），仅在显式关闭时接收模型维度草稿
2. 程序收敛最终字段（finalize_qc_result）
3. 程序校验（result_validator）
4. 程序持久化（result_persister）
"""

import argparse
import copy
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from result_contract import (  # noqa: E402
    ALL_DIMENSIONS,
    CORE_DIMENSIONS,
    DEFAULT_RULE_BY_DIMENSION,
    RULE_METADATA,
    finalize_qc_result,
)
from dsl_executor import execute_core_dimensions  # noqa: E402
from result_persister import ResultPersister  # noqa: E402
from result_validator import ResultValidator  # noqa: E402


LOGGER = logging.getLogger(__name__)
VALID_STATUSES = {'pass', 'risk', 'fail'}
VALID_RISK_LEVELS = {'none', 'low', 'medium', 'high'}
VALID_ISSUE_TYPES = {'consistent', 'missed_downgrade', 'unnecessary_downgrade'}

INPUT_KEYS = {
    'task_id',
    'id',
    'poi_id',
    'name',
    'address',
    'x_coord',
    'y_coord',
    'poi_type',
    'city',
    'district',
    'province',
    'city_adcode',
    'poi_status',
    'verify_result',
    'quality_status',
    'batch_id',
    'worker_id',
    'verify_info',
    'evidence_record',
}
DEFAULT_PREFER_DSL_CORE_DIMENSIONS = True


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f'JSON 根节点必须是对象：{path}')
    return payload


def _write_payload(payload: Dict[str, Any], output_path: Optional[str]) -> None:
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _coerce_probability(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def _normalize_status(value: Any, default: str = 'fail') -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in VALID_STATUSES:
            return lowered
    return default


def _normalize_risk_level(status: str, value: Any) -> str:
    if status == 'pass':
        return 'none'
    if status == 'fail':
        return 'high'
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {'low', 'medium', 'high'}:
            return lowered
    return 'medium'


def _sanitize_related_rules(dim_name: str, value: Any) -> list:
    default_rule = DEFAULT_RULE_BY_DIMENSION.get(dim_name)
    if not isinstance(value, list):
        return [default_rule] if default_rule else []

    filtered = []
    for item in value:
        if item in RULE_METADATA and item not in filtered:
            filtered.append(item)
    if filtered:
        return filtered
    return [default_rule] if default_rule else []


def _sanitize_evidence(value: Any) -> list:
    if not isinstance(value, list):
        return []
    return [copy.deepcopy(item) for item in value if isinstance(item, dict)]


def _sanitize_core_dimension(dim_name: str, raw_dim: Any) -> Dict[str, Any]:
    status = 'fail'
    risk_level = 'high'
    explanation = f'{dim_name} 未提供有效判定结果。'
    related_rules = _sanitize_related_rules(dim_name, [])
    evidence = []
    confidence = None
    issue_code = None
    hard_conflict = None

    if isinstance(raw_dim, dict):
        status = _normalize_status(raw_dim.get('status'), default='fail')
        risk_level = _normalize_risk_level(status, raw_dim.get('risk_level'))
        explanation_value = raw_dim.get('explanation')
        if isinstance(explanation_value, str) and explanation_value.strip():
            explanation = explanation_value.strip()
        related_rules = _sanitize_related_rules(dim_name, raw_dim.get('related_rules'))
        evidence = _sanitize_evidence(raw_dim.get('evidence'))
        confidence = _coerce_probability(raw_dim.get('confidence'))

        issue_code_value = raw_dim.get('issue_code')
        if isinstance(issue_code_value, str) and issue_code_value.strip():
            issue_code = issue_code_value.strip()

        hard_conflict_value = raw_dim.get('hard_conflict')
        if isinstance(hard_conflict_value, bool):
            hard_conflict = hard_conflict_value

    result = {
        'status': status,
        'risk_level': risk_level,
        'explanation': explanation,
        'related_rules': related_rules,
        'evidence': evidence,
    }
    if confidence is not None:
        result['confidence'] = confidence
    if issue_code is not None:
        result['issue_code'] = issue_code
    if hard_conflict is not None:
        result['hard_conflict'] = hard_conflict
    return result


def _parse_upstream_manual_review_required(input_data: Dict[str, Any]) -> bool:
    verify_result = input_data.get('verify_result')
    if not isinstance(verify_result, str):
        return False
    normalized = verify_result.strip()
    return normalized in {'需人工核实', '需要人工核实'}


def _sanitize_downgrade_dimension(raw_dim: Any, upstream_manual: bool) -> Dict[str, Any]:
    evidence = []
    confidence = None
    related_rules = ['R7']
    if isinstance(raw_dim, dict):
        evidence = _sanitize_evidence(raw_dim.get('evidence'))
        confidence = _coerce_probability(raw_dim.get('confidence'))
        related_rules = _sanitize_related_rules('downgrade_consistency', raw_dim.get('related_rules'))
        if 'R7' not in related_rules:
            related_rules = ['R7']

    result = {
        'status': 'fail',
        'risk_level': 'high',
        'explanation': '降级一致性由程序重算。',
        'is_consistent': False,
        'issue_type': 'missed_downgrade' if not upstream_manual else 'unnecessary_downgrade',
        'qc_manual_review_required': True,
        'upstream_manual_review_required': upstream_manual,
        'related_rules': related_rules,
        'evidence': evidence,
    }
    if confidence is not None:
        result['confidence'] = confidence
    return result


def _sanitize_dimension_results(raw_dims: Dict[str, Any], upstream_manual: bool) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    raw_dims = raw_dims if isinstance(raw_dims, dict) else {}

    for dim_name in ALL_DIMENSIONS:
        raw_dim = raw_dims.get(dim_name)
        if dim_name == 'downgrade_consistency':
            sanitized[dim_name] = _sanitize_downgrade_dimension(raw_dim, upstream_manual)
        else:
            sanitized[dim_name] = _sanitize_core_dimension(dim_name, raw_dim)

    return sanitized


def _extract_valid_input_evidence(input_data: Dict[str, Any]) -> list:
    evidence_record = input_data.get('evidence_record')
    if not isinstance(evidence_record, list):
        return []

    valid_items = []
    for item in evidence_record:
        if not isinstance(item, dict):
            continue
        verification = item.get('verification')
        if isinstance(verification, dict) and verification.get('is_valid') is False:
            continue
        valid_items.append(copy.deepcopy(item))
    if valid_items:
        return valid_items

    # 兜底：如果没有明确有效证据，则回退到原始证据字典项。
    return [copy.deepcopy(item) for item in evidence_record if isinstance(item, dict)]


def _is_informative_evidence_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    for key in ('source', 'data', 'verification', 'matching'):
        value = item.get(key)
        if isinstance(value, dict) and value:
            return True
    return False


def _ensure_dimension_evidence_contract(
    dimension_results: Dict[str, Any],
    input_data: Dict[str, Any],
) -> None:
    if not isinstance(dimension_results, dict):
        return

    evidence_candidates = _extract_valid_input_evidence(input_data)
    for dim_name in ALL_DIMENSIONS:
        if dim_name == 'downgrade_consistency':
            continue

        dim_result = dimension_results.get(dim_name)
        if not isinstance(dim_result, dict):
            continue

        status = dim_result.get('status')
        if status not in {'pass', 'risk'}:
            continue

        evidence = dim_result.get('evidence')
        if isinstance(evidence, list) and evidence:
            informative_items = [item for item in evidence if _is_informative_evidence_item(item)]
            if informative_items:
                dim_result['evidence'] = informative_items
                continue

        if evidence_candidates:
            dim_result['evidence'] = [copy.deepcopy(evidence_candidates[0])]
            explanation = dim_result.get('explanation')
            if isinstance(explanation, str) and explanation.strip():
                if '自动补齐证据快照' not in explanation:
                    dim_result['explanation'] = f"{explanation.strip()}（自动补齐证据快照）"
            else:
                dim_result['explanation'] = f"{dim_name} 自动补齐证据快照。"
            continue

        # 没有可用证据时，强制降级为 fail，确保结果满足校验契约。
        dim_result['status'] = 'fail'
        dim_result['risk_level'] = 'high'
        dim_result['evidence'] = []
        dim_result['explanation'] = f"{dim_name} 缺少可用证据，已自动降级为 fail。"


def _extract_input_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ('input_data', 'input', 'source_input'):
        value = payload.get(key)
        if isinstance(value, dict):
            return copy.deepcopy(value)

    extracted = {}
    for key in INPUT_KEYS:
        if key in payload:
            extracted[key] = copy.deepcopy(payload[key])
    return extracted


def _extract_dimension_results(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    direct = payload.get('dimension_results')
    if isinstance(direct, dict):
        return direct

    draft = payload.get('draft')
    if isinstance(draft, dict):
        dim_results = draft.get('dimension_results')
        if isinstance(dim_results, dict):
            return dim_results

    qc_result = payload.get('qc_result')
    if isinstance(qc_result, dict):
        dim_results = qc_result.get('dimension_results')
        if isinstance(dim_results, dict):
            return dim_results

    return None


def _extract_model_judgement(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for key in ('model_judgement', 'qc_model_judgement'):
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    draft = payload.get('draft')
    if isinstance(draft, dict):
        value = draft.get('model_judgement')
        if isinstance(value, dict):
            return value
    return None


def _build_core_dimensions_from_dsl(input_data: Dict[str, Any]) -> Dict[str, Any]:
    dsl_result = execute_core_dimensions(
        input_data,
        dsl_path=str(SCRIPT_DIR / 'rules' / 'decision_tables.json'),
        preprocess=True,
    )
    dimension_results = dsl_result.get('dimension_results')
    if not isinstance(dimension_results, dict):
        raise ValueError('DSL 核心维度重算结果缺少 dimension_results')
    return dimension_results


def _build_qc_draft(payload: Dict[str, Any]) -> Dict[str, Any]:
    input_data = _extract_input_data(payload)
    raw_dimension_results = _extract_dimension_results(payload)

    prefer_dsl = payload.get('prefer_dsl_core_dimensions')
    if not isinstance(prefer_dsl, bool):
        prefer_dsl = DEFAULT_PREFER_DSL_CORE_DIMENSIONS

    dimension_results: Optional[Dict[str, Any]] = None
    if prefer_dsl:
        try:
            dimension_results = _build_core_dimensions_from_dsl(input_data)
        except Exception as exc:
            if raw_dimension_results is None:
                raise ValueError(f'DSL 核心维度重算失败，且无 dimension_results 可回退：{exc}')
            LOGGER.warning('DSL 核心维度重算失败，回退到输入 dimension_results：%s', exc)
            dimension_results = raw_dimension_results
    else:
        if raw_dimension_results is None:
            raise ValueError('缺少 dimension_results：当前已关闭 DSL 重算，需提供维度级草稿结果。')
        dimension_results = raw_dimension_results

    task_id = input_data.get('task_id') or payload.get('task_id')
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError('缺少 task_id')
    task_id = task_id.strip()

    poi_type_hint = input_data.get('poi_type')
    if poi_type_hint is None:
        poi_type_hint = payload.get('poi_type')
    if poi_type_hint is not None:
        poi_type_hint = str(poi_type_hint)

    upstream_manual = _parse_upstream_manual_review_required(input_data)
    normalized_dims = _sanitize_dimension_results(dimension_results, upstream_manual)
    _ensure_dimension_evidence_contract(normalized_dims, input_data)

    qc_draft = {
        'task_id': task_id,
        'dimension_results': normalized_dims,
    }
    if poi_type_hint:
        qc_draft['poi_type'] = poi_type_hint
    return qc_draft


def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """技能执行入口：收敛 -> 校验 -> 持久化。"""
    params = params if isinstance(params, dict) else {}
    include_result = bool(params.get('include_result', False))
    persist_enabled = bool(params.get('persist', True))
    output_dir = params.get('output_dir')

    try:
        qc_draft = _build_qc_draft(params)
        task_id = qc_draft['task_id']
        model_judgement = _extract_model_judgement(params)

        finalized = finalize_qc_result(
            qc_draft,
            scoring_policy_path=str(SCRIPT_DIR / 'config' / 'scoring_policy.json'),
            poi_type_hint=qc_draft.get('poi_type'),
            model_judgement=model_judgement,
            hybrid_policy_path=str(SCRIPT_DIR / 'config' / 'hybrid_policy.json'),
        )

        validator = ResultValidator(
            schema_path=str(SCRIPT_DIR / 'schema' / 'qc_result.schema.json'),
            scoring_policy_path=str(SCRIPT_DIR / 'config' / 'scoring_policy.json'),
            logger=LOGGER,
        )
        validation = validator.validate(finalized)
        if not validation.get('is_valid'):
            result = {
                'success': False,
                'task_id': task_id,
                'error': '质检结果未通过 finalize 后校验',
                'error_type': 'ValidationError',
                'validation_status': validation.get('status'),
                'validation_errors': validation.get('errors', []),
                'validation_warnings': validation.get('warnings', []),
            }
            if include_result:
                result['qc_result'] = finalized
            return result

        result = {
            'success': True,
            'task_id': task_id,
            'qc_status': finalized.get('qc_status'),
            'qc_score': finalized.get('qc_score'),
            'has_risk': finalized.get('has_risk'),
            'risk_dims': finalized.get('risk_dims', []),
            'validation_status': validation.get('status'),
            'validation_warnings': validation.get('warnings', []),
        }

        if not persist_enabled:
            result['message'] = '质检结果已收敛并通过校验（未持久化）'
            if include_result:
                result['qc_result'] = finalized
            return result

        persister = ResultPersister(output_dir=output_dir, logger=LOGGER)
        persist_result = persister.persist(finalized, task_id=task_id)
        if not persist_result.get('success'):
            return {
                'success': False,
                'task_id': task_id,
                'error': '质检结果持久化失败',
                'error_type': 'PersistError',
                'persist_status': persist_result.get('status'),
                'persist_errors': persist_result.get('errors', []),
                'persist_files': persist_result.get('files', {}),
                'persist_output_dir': persist_result.get('output_dir'),
            }

        result.update(
            {
                'message': '质检结果已收敛、校验并持久化',
                'persist_status': persist_result.get('status'),
                'result_dir': persist_result.get('output_dir'),
                'result_files': persist_result.get('files', {}),
            }
        )
        if include_result:
            result['qc_result'] = finalized
        return result
    except Exception as exc:
        return {
            'success': False,
            'task_id': params.get('task_id'),
            'error': str(exc),
            'error_type': type(exc).__name__,
        }


def _read_payload_from_cli(payload_path: Optional[str]) -> Dict[str, Any]:
    if payload_path:
        return _read_json(payload_path)
    if sys.stdin.isatty():
        raise ValueError('缺少 payload 输入：请传入 payload JSON 文件，或从 stdin 传入 JSON。')
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError('stdin JSON 根节点必须是对象')
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description='BigPOI 质检技能单入口执行器')
    parser.add_argument('payload_json', nargs='?', help='输入 payload JSON 文件（可选，不传则读取 stdin）')
    parser.add_argument(
        'output_dir_positional',
        nargs='?',
        help='可选输出目录（兼容旧调用方式）；未传时由 runtime config/默认规则决定',
    )
    parser.add_argument('--output-dir', default=None, help='输出目录，优先于位置参数')
    parser.add_argument('--output', default=None, help='执行结果输出 JSON 文件；不传则打印到 stdout')
    parser.add_argument('--model-judgement', default=None, help='可选：模型裁决 DSL JSON 文件')
    parser.add_argument('--no-persist', action='store_true', help='仅执行收敛+校验，不落盘')
    parser.add_argument('--include-result', action='store_true', help='在返回中附带完整 qc_result')
    args = parser.parse_args()

    payload = _read_payload_from_cli(args.payload_json)
    if args.output_dir:
        payload['output_dir'] = args.output_dir
    elif args.output_dir_positional:
        payload['output_dir'] = args.output_dir_positional

    if args.no_persist:
        payload['persist'] = False
    if args.include_result:
        payload['include_result'] = True
    if args.model_judgement:
        payload['model_judgement'] = _read_json(args.model_judgement)

    result = execute(payload)
    _write_payload(result, args.output)
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    raise SystemExit(main())
