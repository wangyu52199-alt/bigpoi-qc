#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""执行数据库 SQL 的通用脚本。

参数要求：
- 连接方式（connection_mode）
- schema
- 表名（table）
- SQL（支持 {schema}/{table} 模板变量）
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="执行数据库 SQL，输入参数包括连接方式、schema、表名、sql。"
    )
    parser.add_argument(
        "--connection-mode",
        required=True,
        choices=["sqlite", "sqlalchemy"],
        help="数据库连接方式：sqlite 或 sqlalchemy。",
    )
    parser.add_argument(
        "--connection",
        required=True,
        help="连接信息。sqlite 模式传数据库文件路径；sqlalchemy 模式传数据库 URL。",
    )
    parser.add_argument("--schema", required=True, help="schema 名称。")
    parser.add_argument("--table", required=True, help="表名。")
    parser.add_argument(
        "--sql",
        required=True,
        help="待执行 SQL。支持使用 {schema} 和 {table} 模板变量。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="最多输出记录条数，默认 100。",
    )
    return parser


def safe_to_text(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value


def run_with_sqlite(db_path: str, sql: str, limit: int) -> list[dict[str, Any]]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite 文件不存在: {path}")

    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(sql)
        rows = cursor.fetchmany(limit)
        return [{k: safe_to_text(v) for k, v in dict(row).items()} for row in rows]
    finally:
        connection.close()


def run_with_sqlalchemy(
    connection_url: str, sql: str, limit: int
) -> list[dict[str, Any]]:
    try:
        from sqlalchemy import create_engine, text
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "未安装 SQLAlchemy。请先执行: pip install sqlalchemy"
        ) from exc

    engine = create_engine(connection_url)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchmany(limit)
        keys = list(result.keys())
        return [
            {key: safe_to_text(value) for key, value in zip(keys, row)} for row in rows
        ]


def main() -> int:
    args = build_parser().parse_args()

    sql = args.sql.format(schema=args.schema, table=args.table)

    try:
        if args.connection_mode == "sqlite":
            data = run_with_sqlite(args.connection, sql, args.limit)
        else:
            data = run_with_sqlalchemy(args.connection, sql, args.limit)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] SQL 执行失败: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "connection_mode": args.connection_mode,
                "schema": args.schema,
                "table": args.table,
                "row_count": len(data),
                "rows": data,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
