#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bigpoi-verification-qc-write Skill Entry Point
AI Skill Framework 标准入口
"""

import json
import sys
import logging
from pathlib import Path
from typing import Dict, Any
import io

# 强制设置stdout和stderr为UTF-8编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 配置日志
logger = logging.getLogger('QCWriteSkill')
logger.setLevel(logging.DEBUG)

# 如果没有 handler，则添加一个
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# 添加脚本目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from qc_result_writer import QCResultWriter


def execute(data: Dict[str, Any] = None, **kwargs) -> Dict:
    """
    Skill 执行函数（符合 AI Skill Framework 规范）

    Args:
        data: 包含质检完成 POI 数据的字典，应包含：
            - task_id: 质检任务唯一ID（主键）
            - quality_status: 质检状态（'已质检'）
            - qc_status: 质检结论（'qualified' / 'risky' / 'unqualified'）
            - qc_score: 质检评分（0-100）
            - qc_result: 质检结果对象（JSON）
            - (可选) qc_by: 质检执行者
            - (可选) qc_version: 质检技能版本号
        **kwargs: 其他参数（向后兼容）

    Returns:
        dict: 返回更新结果
    """
    logger.info("===== 开始执行质检写库 skill =====")

    if data is None:
        logger.error("输入数据为空，缺少必要的参数")
        return {
            'success': False,
            'error': '缺少必要的输入数据',
            'error_type': 'ValueError'
        }

    task_id = data.get('task_id', 'unknown')
    logger.debug(f"输入参数 - Task ID: {task_id}, 数据: {json.dumps(data, ensure_ascii=False, default=str)}")

    writer = None
    try:
        # 初始化写入器
        logger.debug("初始化 QCResultWriter...")
        writer = QCResultWriter(logger=logger)

        # 建立数据库连接
        logger.debug("建立数据库连接...")
        writer.connect()

        # 执行写入
        logger.info(f"执行质检结果写入操作，Task ID: {task_id}")
        result = writer.write(data)

        logger.info(f"质检结果写入成功，Task ID: {task_id}")
        return result

    except ValueError as e:
        logger.error(f"输入数据验证错误：{e}")
        return {
            'success': False,
            'error': str(e),
            'error_type': 'ValueError'
        }

    except Exception as e:
        logger.error(f"执行过程中发生异常：{type(e).__name__} - {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }

    finally:
        if writer:
            logger.debug("关闭数据库连接...")
            writer.close()
        logger.info("===== 质检写库 skill 执行完成 =====")


def execute_batch(data_list: list = None, **kwargs) -> Dict:
    """
    批量执行函数

    Args:
        data_list: POI 质检数据列表
        **kwargs: 其他参数

    Returns:
        dict: 返回批量更新结果
    """
    logger.info("===== 开始执行批量质检写库 skill =====")

    if data_list is None or not isinstance(data_list, list):
        logger.error("输入必须是 POI 质检数据列表，当前输入类型非法")
        return {
            'success': False,
            'error': '输入必须是 POI 质检数据列表',
            'error_type': 'ValueError'
        }

    logger.debug(f"批量写入任务列表大小: {len(data_list)}")

    writer = None
    try:
        # 初始化写入器
        logger.debug("初始化 QCResultWriter...")
        writer = QCResultWriter(logger=logger)

        # 建立数据库连接
        logger.debug("建立数据库连接...")
        writer.connect()

        # 执行批量写入
        logger.info(f"执行批量质检结果写入操作，共 {len(data_list)} 条数据")
        result = writer.write_batch(data_list)

        if result['success']:
            logger.info(f"批量写入成功 - 总数: {result['total']}, 成功: {result['success_count']}, 失败: {result['failure_count']}")
        else:
            logger.warning(f"批量写入存在失败 - 总数: {result['total']}, 成功: {result['success_count']}, 失败: {result['failure_count']}")

        return result

    except Exception as e:
        logger.error(f"批量执行过程中发生异常：{type(e).__name__} - {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }

    finally:
        if writer:
            logger.debug("关闭数据库连接...")
            writer.close()
        logger.info("===== 批量质检写库 skill 执行完成 =====")


if __name__ == '__main__':
    # 当直接运行此脚本时，使用示例数据
    from datetime import datetime

    logger.info("运行 SKILL.py 测试模式")

    sample_data = {
        'task_id': 'TASK_20240115_QC_001',
        'quality_status': '已质检',
        'qc_status': 'qualified',
        'qc_score': 95,
        'qc_by': 'system',
        'qc_version': '1.1.0',
        'qc_result': {
            'qc_status': 'qualified',
            'qc_score': 95,
            'has_risk': False,
            'risk_dims': [],
            'triggered_rules': [],
            'dimension_results': {
                'existence': {
                    'status': 'pass',
                    'risk_level': 'none',
                    'explanation': 'POI 存在性通过质检'
                },
                'downgrade': {
                    'status': 'pass'
                },
                'downgrade_consistency': {
                    'is_consistent': True
                }
            },
            'explanation': '所有维度质检通过，无质量风险',
            'statistics_flags': {
                'is_qualified': True,
                'is_auto_approvable': True,
                'is_manual_required': False,
                'downgrade_issue_type': 'consistent'
            }
        }
    }

    result = execute(sample_data)
    logger.info(f"测试结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
