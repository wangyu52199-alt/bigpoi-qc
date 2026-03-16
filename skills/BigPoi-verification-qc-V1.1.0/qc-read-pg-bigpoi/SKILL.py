#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bigpoi-verification-qc-read Skill Entry Point
AI Skill Framework 标准入口
"""

import json
import sys
from pathlib import Path
import io

# 强制设置stdout和stderr为UTF-8编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加脚本目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))

from qc_scanner import QCScanner


def execute(context=None, **kwargs):
    """
    Skill 执行函数（符合 AI Skill Framework 规范）

    Args:
        context: 上游传入的上下文信息（可选）
        **kwargs: 其他参数

    Returns:
        dict: 返回扫描结果
    """
    scanner = None
    try:
        # 初始化扫描器
        scanner = QCScanner()

        # 建立数据库连接
        scanner.connect()

        # 执行扫描
        result = scanner.scan()

        return result

    except Exception as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__
        }

    finally:
        if scanner:
            scanner.close()


if __name__ == '__main__':
    # 当直接运行此脚本时
    result = execute()
    print(json.dumps(result, ensure_ascii=False, indent=2))
