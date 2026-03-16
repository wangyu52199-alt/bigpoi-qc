#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QC Result Writer - 将质检完成的 POI 数据写入 PostgreSQL 数据库
功能：
1. 接收质检完成的 POI 数据
2. 使用 task_id 作为主键进行更新（poi_qc_zk 表）
3. 更新质检状态为'已质检'
4. 更新质检结论、评分、详细结果及统计字段
5. 原子性提交，确保数据一致性
"""

import json
import psycopg2
import psycopg2.extras
import yaml
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any


class QCResultWriter:
    """PostgreSQL BigPOI 质检结果写入器"""

    def __init__(self, config_path: str = None, logger: logging.Logger = None):
        """
        初始化数据库连接器

        Args:
            config_path: 数据库配置文件路径，默认为同目录下的 config/db_config.yaml
            logger: 日志记录器，如果不提供则创建新的
        """
        if config_path is None:
            # 获取脚本所在目录
            script_dir = Path(__file__).parent
            config_path = script_dir.parent / "config" / "db_config.yaml"

        self.config_path = Path(config_path)

        # 设置日志
        if logger is None:
            self.logger = logging.getLogger('QCResultWriter')
            if not self.logger.handlers:
                handler = logging.StreamHandler(sys.stdout)
                formatter = logging.Formatter(
                    '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.DEBUG)
        else:
            self.logger = logger

        self.db_config = self._load_config()
        self.conn = None

    def _load_config(self) -> Dict:
        """从 YAML 文件加载数据库配置"""
        try:
            self.logger.debug(f"加载数据库配置文件: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.logger.info(f"数据库配置加载成功，主机: {config.get('host')}, 端口: {config.get('port')}, 数据库: {config.get('database')}")
            return config
        except FileNotFoundError:
            self.logger.error(f"配置文件未找到：{self.config_path}")
            raise FileNotFoundError(f"配置文件未找到：{self.config_path}")
        except yaml.YAMLError as e:
            self.logger.error(f"配置文件格式错误：{e}")
            raise ValueError(f"配置文件格式错误：{e}")

    def connect(self):
        """建立数据库连接"""
        try:
            self.logger.debug(f"尝试连接数据库 {self.db_config['host']}:{self.db_config['port']}/{self.db_config['database']}")
            self.conn = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                connect_timeout=10,
                client_encoding='utf8'
            )
            self.logger.info(f"数据库连接成功：{self.db_config['host']}:{self.db_config['port']}")
        except psycopg2.Error as e:
            self.logger.error(f"数据库连接失败：{e}")
            raise Exception(f"数据库连接失败：{e}")

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.logger.debug("数据库连接已关闭")

    def _validate_input(self, data: Dict) -> bool:
        """
        验证输入数据的必要字段

        Args:
            data: 输入的 POI 质检数据

        Returns:
            验证通过返回 True，否则抛出异常
        """
        required_fields = ['task_id', 'quality_status', 'qc_status', 'qc_score', 'qc_result']

        self.logger.debug(f"开始验证输入数据，Task ID: {data.get('task_id', 'unknown')}")

        for field in required_fields:
            if field not in data:
                self.logger.error(f"缺少必要字段：{field}")
                raise ValueError(f"缺少必要字段：{field}")

        # 检查 quality_status
        if data['quality_status'] != '已质检':
            self.logger.error(f"quality_status 必须为'已质检'，当前值：{data['quality_status']}")
            raise ValueError(f"quality_status 必须为'已质检'，当前值：{data['quality_status']}")

        # 检查 qc_status
        valid_statuses = ['qualified', 'risky', 'unqualified']
        if data['qc_status'] not in valid_statuses:
            self.logger.error(f"qc_status 必须为 {valid_statuses}，当前值：{data['qc_status']}")
            raise ValueError(f"qc_status 必须为 {valid_statuses}，当前值：{data['qc_status']}")

        # 检查 qc_score
        if not isinstance(data['qc_score'], (int, float)) or not (0 <= data['qc_score'] <= 100):
            self.logger.error(f"qc_score 必须为 0-100 的数值，当前值：{data['qc_score']}")
            raise ValueError(f"qc_score 必须为 0-100 的数值，当前值：{data['qc_score']}")

        # 检查 qc_result 是否为有效的 JSON
        if isinstance(data['qc_result'], str):
            try:
                json.loads(data['qc_result'])
            except json.JSONDecodeError:
                self.logger.error("qc_result 不是有效的 JSON 格式")
                raise ValueError("qc_result 不是有效的 JSON 格式")
        elif not isinstance(data['qc_result'], dict):
            self.logger.error("qc_result 必须为 JSON 对象或字符串")
            raise ValueError("qc_result 必须为 JSON 对象或字符串")

        self.logger.debug(f"输入数据验证成功，Task ID: {data.get('task_id')}")
        return True

    def _convert_to_json_str(self, data: Any) -> Any:
        """
        将数据转换为 PostgreSQL JSONB 兼容格式

        Args:
            data: 可以是字典或已经是 JSON 字符串

        Returns:
            psycopg2.extras.Json 对象（用于 JSONB 插入）或字典
        """
        if isinstance(data, str):
            # 如果是字符串，先解析为字典再用 Json() 包装
            try:
                parsed_dict = json.loads(data)
                return psycopg2.extras.Json(parsed_dict)
            except json.JSONDecodeError:
                raise ValueError("JSON 字符串格式错误")
        elif isinstance(data, dict):
            # 直接用 Json() 包装字典
            return psycopg2.extras.Json(data)
        else:
            raise ValueError(f"无法转换为 JSON：{type(data)}")

    def _extract_statistics_flags(self, qc_result: Dict) -> Dict:
        """
        从 qc_result 中提取统计字段，返回 1/0 的枚举值

        Args:
            qc_result: 质检结果对象

        Returns:
            包含统计字段的字典（返回 1=是，0=否）
        """
        # 确保 qc_result 是字典
        if isinstance(qc_result, str):
            qc_result = json.loads(qc_result)

        # 提取统计字段，使用默认值避免 KeyError
        # 转换 True/False 为 1/0（所有INT4字段都不接受NULL）
        statistics = {
            'has_risk': 1 if qc_result.get('has_risk', False) else 0,
            'is_qualified': 1 if qc_result.get('statistics_flags', {}).get('is_qualified', False) else 0,
            'is_auto_approvable': 1 if qc_result.get('statistics_flags', {}).get('is_auto_approvable', False) else 0,
            'is_manual_required': 1 if qc_result.get('statistics_flags', {}).get('is_manual_required', False) else 0,
            'downgrade_issue_type': qc_result.get('statistics_flags', {}).get('downgrade_issue_type', None),
            'downgrade_status': qc_result.get('dimension_results', {}).get('downgrade', {}).get('status', None),
            'is_downgrade_consistent': 1 if qc_result.get('dimension_results', {}).get('downgrade_consistency', {}).get('is_consistent', False) else 0
        }

        return statistics

    def write(self, data: Dict) -> Dict:
        """
        将质检完成的 POI 数据写入数据库

        Args:
            data: 包含以下字段的字典：
                - task_id: 质检任务唯一标识（主键）
                - quality_status: 质检状态（必须为'已质检'）
                - qc_status: 质检结论（'qualified' / 'risky' / 'unqualified'）
                - qc_score: 质检评分（0-100）
                - qc_result: 质检结果对象（JSON）
                - (可选) qc_by: 质检执行者
                - (可选) qc_version: 质检技能版本号

        Returns:
            包含更新状态的字典
        """
        try:
            # 验证输入
            self._validate_input(data)

            task_id = data['task_id']
            self.logger.info(f"开始更新 POI 质检结果：Task ID = {task_id}")

            # 转换 JSON 数据
            qc_result_json = self._convert_to_json_str(data['qc_result'])

            # 提取统计字段
            statistics = self._extract_statistics_flags(data['qc_result'])
            self.logger.debug(f"提取的统计字段: {json.dumps(statistics, ensure_ascii=False, default=str)}")

            # 执行更新
            cursor = self.conn.cursor()

            update_sql = """
                UPDATE public.poi_qc_zk
                SET
                    quality_status = %s,
                    qc_status = %s,
                    qc_score = %s,
                    qc_result = %s,
                    has_risk = %s,
                    is_qualified = %s,
                    is_auto_approvable = %s,
                    is_manual_required = %s,
                    downgrade_issue_type = %s,
                    downgrade_status = %s,
                    is_downgrade_consistent = %s,
                    qc_by = %s,
                    qc_version = %s,
                    updatetime = %s
                WHERE task_id = %s
            """

            current_time = datetime.now()

            self.logger.debug(f"执行 UPDATE 操作，更新时间: {current_time.isoformat()}")

            cursor.execute(update_sql, (
                '已质检',
                data['qc_status'],
                int(data['qc_score']),
                qc_result_json,
                statistics['has_risk'],
                statistics['is_qualified'],
                statistics['is_auto_approvable'],
                statistics['is_manual_required'],
                statistics['downgrade_issue_type'],
                statistics['downgrade_status'],
                statistics['is_downgrade_consistent'],
                data.get('qc_by'),
                data.get('qc_version'),
                current_time,
                task_id
            ))

            # 检查是否有行被更新
            if cursor.rowcount == 0:
                cursor.close()
                self.logger.error(f"未找到要更新的 POI_QC：Task ID = {task_id}")
                raise ValueError(f"未找到要更新的 POI_QC：Task ID = {task_id}")

            # 提交事务
            self.conn.commit()
            cursor.close()

            self.logger.info(f"POI 质检结果更新成功：Task ID = {task_id}，受影响行数: {cursor.rowcount}")

            updated_fields = [
                'quality_status', 'qc_status', 'qc_score', 'qc_result',
                'has_risk', 'is_qualified', 'is_auto_approvable', 'is_manual_required',
                'downgrade_issue_type', 'downgrade_status', 'is_downgrade_consistent',
                'qc_by', 'qc_version', 'updatetime'
            ]

            return {
                'success': True,
                'task_id': task_id,
                'message': 'POI 质检结果已成功更新',
                'updated_fields': updated_fields,
                'updatetime': current_time.isoformat()
            }

        except psycopg2.Error as e:
            self.conn.rollback()
            self.logger.error(f"数据库操作失败：{e}", exc_info=True)
            raise Exception(f"数据库操作失败：{e}")

    def write_batch(self, data_list: list) -> Dict:
        """
        批量写入质检完成的 POI 数据

        Args:
            data_list: POI 质检数据列表

        Returns:
            包含批量更新状态的字典
        """
        success_count = 0
        failure_count = 0
        errors = []

        self.logger.info(f"开始批量写入，共 {len(data_list)} 条数据")

        for idx, data in enumerate(data_list):
            try:
                self.logger.debug(f"处理第 {idx + 1}/{len(data_list)} 条数据，Task ID: {data.get('task_id', 'unknown')}")
                result = self.write(data)
                success_count += 1
            except Exception as e:
                failure_count += 1
                task_id = data.get('task_id', 'unknown')
                self.logger.warning(f"第 {idx + 1} 条数据处理失败，Task ID: {task_id}, 错误: {str(e)}")
                errors.append({
                    'index': idx,
                    'task_id': task_id,
                    'error': str(e)
                })

                # 如果连接出现异常，尝试恢复连接以继续处理后续数据
                try:
                    self.conn.rollback()
                except:
                    pass

                # 重新连接
                try:
                    self.close()
                    self.connect()
                    self.logger.info(f"连接已恢复，继续处理下一条数据")
                except Exception as reconnect_error:
                    self.logger.error(f"无法恢复连接：{reconnect_error}", exc_info=True)
                    # 如果无法恢复，后续数据都会失败
                    break

        self.logger.info(f"批量写入完成 - 总数: {len(data_list)}, 成功: {success_count}, 失败: {failure_count}")

        return {
            'success': failure_count == 0,
            'total': len(data_list),
            'success_count': success_count,
            'failure_count': failure_count,
            'errors': errors if errors else None
        }


def main():
    """
    主函数

    注意：此脚本设计为被 AI Skill Framework 调用，不应直接运行
    直接运行此脚本可能导致误操作数据库
    """
    logger = logging.getLogger('QCResultWriter')
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    logger.warning("="*60)
    logger.warning("警告：此脚本应通过 AI Skill Framework 调用，不应直接运行")
    logger.warning("="*60)
    logger.info("请使用 Framework 通过 SKILL.py 中的 execute() 函数进行调用")
    print("\n[提示] 此脚本是 AI Skill Framework 的组件，应通过框架调用")
    print("[提示] 请勿直接执行此脚本，以免误操作数据库\n")

    return {
        'success': False,
        'message': '此脚本应通过 AI Skill Framework 调用'
    }


if __name__ == '__main__':
    main()
