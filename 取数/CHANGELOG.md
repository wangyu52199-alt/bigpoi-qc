# Changelog

## 2026-04-02

- 新增 `db_query.py`：
  - 支持参数：`--connection-mode`、`--connection`、`--schema`、`--table`、`--sql`、`--limit`
  - 支持 `sqlite` 与 `sqlalchemy` 两种连接方式
  - `--sql` 支持 `{schema}`、`{table}` 模板变量
  - 输出统一 JSON 结构，便于后续自动化处理
- 新增 `README.md`，补充脚本用法、参数说明和示例
