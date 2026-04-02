# 取数脚本

## 任务说明

提供一个通用 Python 脚本，用于按参数执行数据库 SQL。输入参数包含：

- 库表连接方式
- schema
- 表名
- sql

## 文件说明

- `db_query.py`: 主脚本

## 运行环境

- Python 3.9+
- 可选依赖：`sqlalchemy`（当 `--connection-mode sqlalchemy` 时需要）

安装可选依赖：

```bash
pip install sqlalchemy
```

## 参数说明

```bash
python db_query.py \
  --connection-mode <sqlite|sqlalchemy> \
  --connection <连接信息> \
  --schema <schema> \
  --table <表名> \
  --sql "<SQL>" \
  [--limit 100]
```

- `--connection-mode`：连接方式，支持 `sqlite` 或 `sqlalchemy`
- `--connection`：
  - `sqlite` 模式：SQLite 文件路径
  - `sqlalchemy` 模式：SQLAlchemy URL（如 `postgresql+psycopg2://user:pwd@host:5432/db`）
- `--schema`：schema 名称
- `--table`：表名
- `--sql`：SQL 文本，支持 `{schema}` 和 `{table}` 模板变量
- `--limit`：最多返回记录数，默认 `100`

## 使用示例

SQLite 示例：

```bash
python db_query.py \
  --connection-mode sqlite \
  --connection ./demo.db \
  --schema main \
  --table users \
  --sql "select * from {schema}.{table} limit 10"
```

SQLAlchemy 示例：

```bash
python db_query.py \
  --connection-mode sqlalchemy \
  --connection "postgresql+psycopg2://user:pwd@127.0.0.1:5432/demo" \
  --schema public \
  --table users \
  --sql "select id, name from {schema}.{table} where id < 100"
```

## 输出

脚本输出 JSON，包含执行元信息与结果行：

- `connection_mode`
- `schema`
- `table`
- `row_count`
- `rows`
