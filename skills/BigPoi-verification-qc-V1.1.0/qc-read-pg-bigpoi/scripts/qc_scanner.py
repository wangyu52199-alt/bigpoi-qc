#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QC Scanner - 从 PostgreSQL 数据库中读取待质检的 POI 核实结果数据
功能：
1. 检查数据库中是否存在'质检中'的数据
2. 若存在，则跳过本次，只返回统计信息
3. 若不存在，则获取一条待质检的数据，更新其质检状态为'质检中'
4. 同时读取该 POI 的所有关联数据（poi_verify 的证据和决策信息）
5. 返回统计信息与待质检的完整数据
"""

import json
import psycopg2
import psycopg2.extras
import yaml
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class QCScanner:
    """PostgreSQL BigPOI 质检数据库扫描器"""

    def __init__(self, config_path: str = None):
        """
        初始化数据库连接器

        Args:
            config_path: 数据库配置文件路径，默认为同目录下的 config/db_config.yaml
        """
        if config_path is None:
            # 获取脚本所在目录
            script_dir = Path(__file__).parent
            config_path = script_dir.parent / "config" / "db_config.yaml"

        self.config_path = Path(config_path)
        self.db_config = self._load_config()
        self.conn = None
        self.poi_type_mapping = self._load_poi_type_mapping()

    def _load_config(self) -> Dict:
        """从 YAML 文件加载数据库配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件未找到：{self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误：{e}")

    def _load_poi_type_mapping(self) -> Dict[str, str]:
        """
        加载 POI 类型映射配置

        Returns:
            POI 类型代码到中文名称的映射字典
        """
        try:
            script_dir = Path(__file__).parent
            mapping_path = script_dir.parent / "config" / "poi_type_mapping.yaml"

            if not mapping_path.exists():
                print(f"[WARN] POI 类型映射配置未找到：{mapping_path}")
                return {}

            with open(mapping_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 构建映射字典：type_code -> 中文类型名
            mapping = {}
            if config and 'mappings' in config:
                for type_name, type_info in config['mappings'].items():
                    # 获取中文描述（去掉后面的详细说明，只取主要类型）
                    description = type_info.get('description', type_name)
                    # 提取主要类型名（第一句话）
                    chinese_name = description.split('，')[0] if description else type_name

                    if 'type_codes' in type_info:
                        for code in type_info['type_codes']:
                            mapping[code] = chinese_name

            return mapping
        except Exception as e:
            print(f"[WARN] 加载 POI 类型映射失败：{e}")
            return {}

    def _get_poi_type_name(self, poi_type: str) -> str:
        """
        根据 POI 类型代码获取映射后的中文名称

        Args:
            poi_type: POI 类型代码

        Returns:
            映射后的 POI 中文类型名称，如无匹配则返回原值
        """
        if not poi_type:
            return poi_type

        # 精确匹配
        if poi_type in self.poi_type_mapping:
            return self.poi_type_mapping[poi_type]

        # 前缀匹配（用于大类匹配）
        for code, type_name in self.poi_type_mapping.items():
            if poi_type.startswith(code):
                return type_name

        # 无匹配则返回原值
        return poi_type

    def _validate_record_data(self, record_data: Dict) -> None:
        """
        验证读库的记录数据完整性和一致性

        验证以下必填字段不能为空：
        - id: POI ID
        - name: POI名称
        - poi_type: POI类型
        - city: 城市
        - x_coord: 经度坐标
        - y_coord: 纬度坐标
        - verify_status: 核实状态（必须为'已核实'）

        Args:
            record_data: 从poi_qc表读取的记录数据

        Raises:
            ValueError: 当数据不完整或不一致时抛出异常
        """
        if not record_data:
            raise ValueError("记录数据为空")

        # 检查必填字段
        required_fields = {
            'id': 'POI ID',
            'name': 'POI名称',
            'poi_type': 'POI类型',
            'city': '城市'
        }

        for field, field_name in required_fields.items():
            if field not in record_data:
                raise ValueError(f"缺少必填字段：{field_name} ({field})")

            value = record_data[field]
            if value is None or (isinstance(value, str) and value.strip() == ''):
                raise ValueError(f"必填字段不能为空：{field_name} ({field})")

        # 检查坐标有效性
        if 'x_coord' in record_data and record_data['x_coord'] is not None:
            try:
                x = float(record_data['x_coord'])
                if x < -180 or x > 180:
                    raise ValueError(f"经度坐标越界：{x}（有效范围：-180 ~ 180）")
            except (TypeError, ValueError) as e:
                raise ValueError(f"经度坐标格式错误：{record_data['x_coord']}")

        if 'y_coord' in record_data and record_data['y_coord'] is not None:
            try:
                y = float(record_data['y_coord'])
                if y < -90 or y > 90:
                    raise ValueError(f"纬度坐标越界：{y}（有效范围：-90 ~ 90）")
            except (TypeError, ValueError) as e:
                raise ValueError(f"纬度坐标格式错误：{record_data['y_coord']}")

        # 检查核实状态
        if 'verify_status' in record_data:
            if record_data['verify_status'] != '已核实':
                raise ValueError(f"核实状态不符：期望'已核实'，实际'{record_data['verify_status']}'")

        # 检查质检状态
        if 'quality_status' in record_data:
            valid_statuses = ['待质检', '质检中', '已质检']
            if record_data['quality_status'] not in valid_statuses:
                raise ValueError(f"质检状态无效：'{record_data['quality_status']}'，允许值：{valid_statuses}")

        # 检查POI类型是否已映射为中文
        if 'poi_type' in record_data:
            poi_type = record_data['poi_type']
            # 如果poi_type还是数字代码（未映射），说明映射失败
            if poi_type and poi_type.isdigit():
                raise ValueError(f"POI类型未正确映射：{poi_type}（应该是中文类型名）")

        print(f"[INFO] 记录数据验证通过：ID={record_data.get('id')}, 名称={record_data.get('name')}")

    def connect(self):
        """建立数据库连接"""
        try:
            self.conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                connect_timeout=10,
                client_encoding='utf8'
            )
            print(f"[INFO] 数据库连接成功：{self.db_config['host']}:{self.db_config['port']}")
        except psycopg2.Error as e:
            raise Exception(f"数据库连接失败：{e}")

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            print("[INFO] 数据库连接已关闭")

    def _count_by_qc_status(self) -> Dict[str, int]:
        """
        统计各质检状态下的 POI 数量

        Returns:
            包含各状态数量的字典
        """
        try:
            cursor = self.conn.cursor()

            # 统计质检中的数量
            cursor.execute("""
                SELECT COUNT(*) FROM public.poi_qc
                WHERE quality_status = '质检中'
            """)
            qc_checking_count = cursor.fetchone()[0]

            # 统计质检完成的数量
            cursor.execute("""
                SELECT COUNT(*) FROM public.poi_qc
                WHERE quality_status = '已质检'
            """)
            qc_completed_count = cursor.fetchone()[0]

            # 统计待质检的数量
            cursor.execute("""
                SELECT COUNT(*) FROM public.poi_qc
                WHERE quality_status NOT IN ('质检中', '已质检')
            """)
            pending_qc_count = cursor.fetchone()[0]

            cursor.close()

            return {
                'qc_checking_count': qc_checking_count,
                'qc_completed_count': qc_completed_count,
                'pending_qc_count': pending_qc_count
            }
        except psycopg2.Error as e:
            raise Exception(f"统计质检状态失败：{e}")

    def _check_qc_checking_exists(self) -> bool:
        """
        检查是否存在'质检中'的 POI 数据

        Returns:
            存在返回 True，否则返回 False
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT 1 FROM public.poi_qc
                WHERE quality_status = '质检中'
                LIMIT 1
            """)
            result = cursor.fetchone() is not None
            cursor.close()
            return result
        except psycopg2.Error as e:
            raise Exception(f"检查质检中数据失败：{e}")

    def _get_record_data(self, qc_id: str, poi_id: str) -> Dict:
        """
        获取 POI 的核实结论数据（从poi_qc表获取）

        Args:
            qc_id: poi_qc 表的 id
            poi_id: POI ID（用于关联查询）

        Returns:
            record 数据字典
        """
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # 从 poi_qc 表获取质检记录的核实数据
            cursor.execute("""
                SELECT
                    task_id, id, name, address, x_coord, y_coord,
                    poi_type, city, city_adcode, poi_status, verify_result,
                    batch_id, quality_status
                FROM public.poi_qc
                WHERE id = %s
            """, (qc_id,))

            row = cursor.fetchone()
            cursor.close()

            if row is None:
                return {}

            result = dict(row)
            # 映射 poi_type 代码为中文名称
            if 'poi_type' in result and result['poi_type']:
                result['poi_type'] = self._get_poi_type_name(result['poi_type'])
            # 添加 verify_status 标记为已核实
            result['verify_status'] = '已核实'
            return result
        except psycopg2.Error as e:
            raise Exception(f"获取 POI 结论数据失败：{e}")

    def _detect_evidence_format(self, evidence_record_json) -> tuple:
        """
        自动检测证据数据的格式

        Returns:
            (format_type, evidence_items, metadata)
            - format_type: 'array' | 'sources_array' | 'details_sources' | 'collection_summary' | 'unknown'
            - evidence_items: 提取的证据数组
            - metadata: 公共元数据（如collection_time等）
        """
        if isinstance(evidence_record_json, list):
            # 格式C：直接是标准数组格式
            return 'array', evidence_record_json, {}

        if not isinstance(evidence_record_json, dict):
            return 'unknown', [], {}

        metadata = {}

        # 检查是否有 collection_time（多种格式都可能有）
        if 'collection_time' in evidence_record_json:
            metadata['collection_time'] = evidence_record_json['collection_time']

        # 格式C 的另一种包装：顶层有 evidence_list
        if 'evidence_list' in evidence_record_json:
            evidence_items = evidence_record_json.get('evidence_list', [])
            if isinstance(evidence_items, list) and evidence_items:
                return 'evidence_list', evidence_items, metadata

        # 格式A/B：sources 数组（可能与 details 组合）
        sources = evidence_record_json.get('sources', [])
        details = evidence_record_json.get('details', [])

        # 格式B：details 和 sources 并存
        if details and isinstance(details, list):
            return 'details_sources', details, metadata

        # 格式A：只有 sources 数组
        if sources and isinstance(sources, list):
            return 'sources_array', sources, metadata

        # evidence_collection_summary.evidence_list 结构
        evidence_collection_summary = evidence_record_json.get('evidence_collection_summary', {})
        if evidence_collection_summary:
            evidence_list = evidence_collection_summary.get('evidence_list', [])
            if isinstance(evidence_list, list) and evidence_list:
                return 'collection_summary', evidence_list, metadata

        return 'unknown', [], metadata

    def _normalize_evidence_item(self, item: Dict, format_type: str, idx: int, metadata: Dict) -> Dict:
        """
        将不同格式的证据项转换为标准格式

        标准输出格式：
        {
            'evidence_id': str,
            'source': {'source_id': str, 'source_name': str, 'source_type': str},
            'data': dict,
            'verification': {'is_valid': bool, 'confidence': float, 'verification_time': str},
            'matching': {'name_similarity': float, 'location_distance': float, 'category_match': float, 'is_match': bool},
            'poi_id': str (optional)
        }
        """
        standard_item = {
            'evidence_id': '',
            'source': {
                'source_id': '',
                'source_name': '',
                'source_type': ''
            },
            'data': {},
            'verification': {
                'is_valid': True,
                'confidence': 0,
                'verification_time': ''
            },
            'matching': {
                'name_similarity': 0,
                'location_distance': 0,
                'category_match': 0,
                'is_match': False
            }
        }

        # poi_id 如果存在则保留
        if 'poi_id' in item:
            standard_item['poi_id'] = item['poi_id']

        if format_type == 'array' or format_type == 'evidence_list':
            # 标准格式C：直接映射
            standard_item['evidence_id'] = item.get('evidence_id', f'EV_{idx+1}')
            standard_item['data'] = item.get('data', {})

            if 'source' in item:
                source = item['source']
                if isinstance(source, dict):
                    standard_item['source']['source_id'] = source.get('source_id', '')
                    standard_item['source']['source_name'] = source.get('source_name', '')
                    standard_item['source']['source_type'] = source.get('source_type', '')

            if 'verification' in item:
                verification = item['verification']
                if isinstance(verification, dict):
                    standard_item['verification']['is_valid'] = verification.get('is_valid', True)
                    standard_item['verification']['confidence'] = verification.get('confidence', 0)
                    standard_item['verification']['verification_time'] = item.get('collected_at', '')

            if 'matching' in item:
                matching = item['matching']
                if isinstance(matching, dict):
                    standard_item['matching'] = {
                        'name_similarity': matching.get('name_similarity', 0),
                        'location_distance': matching.get('location_distance', 0),
                        'category_match': matching.get('category_match', 0),
                        'is_match': matching.get('is_match', False)
                    }

        elif format_type == 'sources_array':
            # 格式A：sources 数组，每个源有 name, type, weight, data
            standard_item['evidence_id'] = f'EV_{idx+1}'
            standard_item['source']['source_name'] = item.get('name', '')
            standard_item['source']['source_type'] = item.get('type', '')
            standard_item['data'] = item.get('data', {})
            standard_item['verification']['confidence'] = item.get('weight', 0)
            standard_item['verification']['verification_time'] = metadata.get('collection_time', '')

        elif format_type == 'details_sources':
            # 格式B：details 数组，每个detail有 source, weight, source_type
            standard_item['evidence_id'] = f'EV_{idx+1}'
            standard_item['source']['source_name'] = item.get('source', '')
            standard_item['source']['source_type'] = item.get('source_type', '')
            standard_item['verification']['confidence'] = item.get('weight', 0)
            standard_item['verification']['verification_time'] = metadata.get('collection_time', '')

        elif format_type == 'collection_summary':
            # evidence_collection_summary.evidence_list 格式
            standard_item['evidence_id'] = item.get('evidence_id', f'EV_{idx+1}')

            if 'source' in item:
                source = item['source']
                if isinstance(source, dict):
                    standard_item['source']['source_id'] = source.get('source_id', '')
                    standard_item['source']['source_name'] = source.get('source_name', '')
                    standard_item['source']['source_type'] = source.get('source_type', '')

            standard_item['data'] = item.get('data', {})

            if 'verification' in item:
                verification = item['verification']
                if isinstance(verification, dict):
                    standard_item['verification']['is_valid'] = verification.get('is_valid', True)
                    standard_item['verification']['confidence'] = verification.get('confidence', 0)

            standard_item['verification']['verification_time'] = item.get('collected_at', '')

            if 'matching' in item:
                matching = item['matching']
                if isinstance(matching, dict):
                    standard_item['matching'] = {
                        'name_similarity': matching.get('name_similarity', 0),
                        'location_distance': matching.get('location_distance', 0),
                        'category_match': matching.get('category_match', 0),
                        'is_match': matching.get('is_match', False)
                    }

        return standard_item

    def _parse_evidence_record(self, evidence_record_json) -> List[Dict]:
        """
        从 poi_verified 表的 evidence_record JSON 字段解析证据数据

        自动识别以下数据结构：
        1. 标准数组格式：[{evidence_id, source, data, verification, ...}]
        2. sources 数组：{sources: [{name, type, weight, data}], collection_time}
        3. details+sources：{details: [{source, weight, source_type}], sources: [...], collection_time}
        4. evidence_collection_summary：{evidence_collection_summary: {evidence_list: [...]}}
        5. evidence_list：{evidence_list: [...]}

        Args:
            evidence_record_json: JSON 格式的证据记录（可能是dict或list）

        Returns:
            证据数据列表（统一的标准格式）
        """
        if not evidence_record_json:
            return []

        try:
            # 自动检测格式
            format_type, evidence_items, metadata = self._detect_evidence_format(evidence_record_json)

            if format_type == 'unknown' or not evidence_items:
                print(f"[WARN] 无法识别证据数据格式", file=sys.stderr)
                return []

            # 转换为标准格式
            result = []
            for idx, item in enumerate(evidence_items):
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_evidence_item(item, format_type, idx, metadata)
                result.append(normalized)

            return result

        except Exception as e:
            print(f"[WARN] 解析证据数据异常：{e}", file=sys.stderr)
            return []

    def _get_evidence_data(self, poi_id: str) -> List[Dict]:
        """
        获取 POI 的所有证据数据（从poi_verified表的evidence_record字段读取）

        Args:
            poi_id: POI ID

        Returns:
            证据数据列表
        """
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT evidence_record
                FROM public.poi_verified
                WHERE id = %s
            """, (poi_id,))

            row = cursor.fetchone()
            cursor.close()

            if row is None or not row['evidence_record']:
                return []

            evidence_record_json = row['evidence_record']
            if isinstance(evidence_record_json, str):
                evidence_record_json = json.loads(evidence_record_json)

            return self._parse_evidence_record(evidence_record_json)
        except psycopg2.Error as e:
            raise Exception(f"获取证据数据失败：{e}")
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            print(f"[WARN] 解析证据数据失败：{e}", file=sys.stderr)
            return []

    def _normalize_upstream_decision(self, verify_info_json: Dict) -> Dict:
        """
        智能识别并规范化上游决策信息

        支持以下格式的自动识别：
        1. 维度维的核实结果直接在顶层：{name: {...}, category: {...}, location: {...}}
        2. 嵌套在 verify_dimensions 中：{verify_dimensions: {name: {...}, ...}}
        3. 嵌套在 verification 中：{verification: {dimensions: {...}}}
        4. 包含 overall 和 dimensions：{overall: {...}, dimensions: {...}}

        标准输出格式：
        {
            'overall': {'status': str, 'confidence': float, 'action': str, 'summary': str},
            'dimensions': {各维度核实结果},
            'downgrade_info': {降级信息}
        }

        Args:
            verify_info_json: 从 poi_verified.verify_info 读取的 JSON

        Returns:
            规范化后的上游决策数据
        """
        if not verify_info_json:
            return {}

        standard_decision = {
            'overall': {
                'status': '未知',
                'confidence': 0,
                'action': 'unknown',
                'summary': ''
            },
            'dimensions': {},
            'downgrade_info': {
                'is_downgraded': False,
                'reason_code': None,
                'reason_description': None,
                'trigger_conditions': None,
                'recommendation': None
            }
        }

        # 检查是否有 overall 字段
        if 'overall' in verify_info_json:
            overall = verify_info_json['overall']
            if isinstance(overall, dict):
                standard_decision['overall'] = {
                    'status': overall.get('status', '未知'),
                    'confidence': overall.get('confidence', 0),
                    'action': overall.get('action', 'unknown'),
                    'summary': overall.get('summary', '')
                }

        # 检查是否有 downgrade_info
        if 'downgrade_info' in verify_info_json:
            downgrade_info = verify_info_json['downgrade_info']
            if isinstance(downgrade_info, dict):
                standard_decision['downgrade_info'] = {
                    'is_downgraded': downgrade_info.get('is_downgraded', False),
                    'reason_code': downgrade_info.get('reason_code'),
                    'reason_description': downgrade_info.get('reason_description'),
                    'trigger_conditions': downgrade_info.get('trigger_conditions'),
                    'recommendation': downgrade_info.get('recommendation')
                }

        # 检测维度数据的位置
        dimensions_data = None

        # 方案1：顶层直接有 dimensions
        if 'dimensions' in verify_info_json:
            dimensions_data = verify_info_json['dimensions']

        # 方案2：verify_dimensions 字段
        elif 'verify_dimensions' in verify_info_json:
            dimensions_data = verify_info_json['verify_dimensions']

        # 方案3：verification.dimensions
        elif 'verification' in verify_info_json:
            verification = verify_info_json['verification']
            if isinstance(verification, dict) and 'dimensions' in verification:
                dimensions_data = verification['dimensions']

        # 方案4：维度数据直接在顶层（如 name, category, location 等）
        if not dimensions_data:
            # 提取所有可能的维度字段
            known_dimensions = ['name', 'category', 'location', 'address', 'phone', 'existence',
                              'administrative', 'coordinate', 'contact', 'business_hours']
            dimensions_data = {}
            for key in known_dimensions:
                if key in verify_info_json and isinstance(verify_info_json[key], dict):
                    dimensions_data[key] = verify_info_json[key]

        # 设置维度数据
        if dimensions_data and isinstance(dimensions_data, dict):
            standard_decision['dimensions'] = dimensions_data

        return standard_decision

    def _get_upstream_decision(self, poi_id: str) -> Dict:
        """
        获取 POI 的上游核实决策信息（从poi_verified表的verify_info字段读取）

        自动识别多种可能的 JSON 结构格式

        Args:
            poi_id: POI ID

        Returns:
            upstream_decision 数据字典（包含各维度的核实结果）
        """
        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""
                SELECT verify_info
                FROM public.poi_verified
                WHERE id = %s
            """, (poi_id,))

            row = cursor.fetchone()
            cursor.close()

            if row is None or not row['verify_info']:
                return {}

            verify_info_json = row['verify_info']
            if isinstance(verify_info_json, str):
                verify_info_json = json.loads(verify_info_json)

            # 智能规范化
            return self._normalize_upstream_decision(verify_info_json)

        except psycopg2.Error as e:
            raise Exception(f"获取上游决策数据失败：{e}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] 解析决策数据失败：{e}", file=sys.stderr)
            return {}

    def _get_one_pending_qc_poi(self) -> Optional[Dict]:
        """
        获取一条待质检的 POI 数据，并原子性地更新其质检状态为'质检中'

        Returns:
            获取到的完整 POI 数据字典，若无则返回 None
        """
        try:
            cursor = self.conn.cursor()

            # 使用事务保证原子性
            self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)

            # 获取一条待质检数据（quality_status 不是'质检中'和'已质检'）
            cursor.execute("""
                SELECT id
                FROM public.poi_qc
                WHERE quality_status NOT IN ('质检中', '已质检')
                ORDER BY id ASC
                LIMIT 1
                FOR UPDATE
            """)

            row = cursor.fetchone()

            if row is None:
                cursor.close()
                return None

            qc_id = row[0]
            # poi_id 就是 id（因为迁移时用 id 作为主键）
            poi_id = qc_id
            previous_quality_status = None

            # 获取之前的 quality_status 值
            cursor.execute("""
                SELECT quality_status FROM public.poi_qc WHERE id = %s
            """, (qc_id,))
            prev_row = cursor.fetchone()
            if prev_row:
                previous_quality_status = prev_row[0]

            # 更新质检状态为'质检中'
            update_time = datetime.now()
            cursor.execute("""
                UPDATE public.poi_qc
                SET quality_status = %s, updatetime = %s
                WHERE id = %s
            """, ('质检中', update_time, qc_id))

            self.conn.commit()
            cursor.close()

            # 读取完整数据
            record_data = self._get_record_data(qc_id, poi_id)

            # 验证记录数据的完整性和一致性
            try:
                self._validate_record_data(record_data)
            except ValueError as e:
                # 验证失败，回滚状态更新（将质检状态改回原状态）
                print(f"[ERROR] 数据验证失败：{e}", file=sys.stderr)
                try:
                    cursor = self.conn.cursor()
                    cursor.execute("""
                        UPDATE public.poi_qc
                        SET quality_status = %s, updatetime = %s
                        WHERE id = %s
                    """, (previous_quality_status, datetime.now(), qc_id))
                    self.conn.commit()
                    cursor.close()
                    print(f"[INFO] 已回滚质检状态：{qc_id} → {previous_quality_status}")
                except Exception as rollback_error:
                    print(f"[ERROR] 回滚失败：{rollback_error}", file=sys.stderr)
                raise Exception(f"质检数据验证失败，请检查数据库数据完整性：{e}")

            evidence_data = self._get_evidence_data(poi_id)
            upstream_decision = self._get_upstream_decision(poi_id)

            # 构建返回数据
            qc_data = {
                'read_metadata': {
                    'timestamp': datetime.now().isoformat() + 'Z',
                    'data_source': 'PostgreSQL',
                    'record_id': qc_id,
                    'read_status': 'success',
                    'status_update': {
                        'updated': True,
                        'previous_quality_status': previous_quality_status,
                        'current_quality_status': '质检中',
                        'update_timestamp': update_time.isoformat() + 'Z'
                    }
                },
                'record': record_data,
                'evidence_data': evidence_data,
                'upstream_decision': upstream_decision
            }

            print(f"[INFO] 获取待质检数据成功：POI QC ID = {qc_id}, POI ID = {poi_id}")
            return qc_data

        except psycopg2.Error as e:
            self.conn.rollback()
            raise Exception(f"获取待质检数据失败：{e}")

    def scan(self) -> Dict:
        """
        执行 QC 扫描和状态管理的主流程

        返回格式：
        {
            "qc_checking_count": 0,
            "qc_completed_count": 5,
            "pending_qc_count": 100,
            "need_qc": {...}  # 可选，仅当存在待质检数据时返回
        }
        """
        try:
            # 步骤1：统计各质检状态数量
            print("[INFO] 正在统计质检状态分布...")
            counts = self._count_by_qc_status()

            # 步骤2：检查是否存在'质检中'的数据
            print("[INFO] 检查是否存在'质检中'的数据...")
            if self._check_qc_checking_exists():
                print("[INFO] 检测到'质检中'的数据存在，本次跳过处理")
                return counts

            # 步骤3：获取待质检数据并更新状态
            print("[INFO] 开始获取待质检数据...")
            need_qc = self._get_one_pending_qc_poi()

            if need_qc:
                counts['need_qc'] = need_qc
                print(f"[INFO] 成功获取待质检数据：{need_qc['record'].get('id')} - {need_qc['record'].get('name')}")
            else:
                print("[INFO] 未找到待质检数据，本次跳过")

            return counts

        except Exception as e:
            print(f"[ERROR] 扫描失败：{e}", file=sys.stderr)
            raise


def main():
    """主函数"""
    scanner = None
    try:
        # 初始化扫描器
        scanner = QCScanner()

        # 建立连接
        scanner.connect()

        # 执行扫描
        result = scanner.scan()

        # 输出结果为 JSON
        print("\n=== 质检扫描结果 ===")
        json_str = json.dumps(result, ensure_ascii=False, indent=2)
        print(json_str)

        # 同时保存到文件（UTF-8编码，避免终端编码问题）
        output_file = Path(__file__).parent.parent / "qc_input.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(json_str)
        print(f"\n[INFO] 结果已保存到：{output_file}")

        return result

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        if scanner:
            scanner.close()


if __name__ == '__main__':
    main()
