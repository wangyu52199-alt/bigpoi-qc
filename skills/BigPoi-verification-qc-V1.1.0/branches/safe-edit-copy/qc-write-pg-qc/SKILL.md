---
name: qc-write-pg-qc
description: 从本地质检结果文件读取 qc_result，并更新 PostgreSQL 质检表（紧凑版说明）。
metadata:
  version: "1.3.1"
  category: "quality-control"
  tags: ["qc", "database", "persistence"]
---

# 大POI质检结果回库技能 v1.3.1 (Compact)

## 1) 目标

从本地 `complete.json` 读取质检结果，更新目标表（默认 `poi_qc_zk`）对应 `task_id` 的记录，并将状态更新为 `已质检`。

## 2) 输入参数

- `task_id`（必填）
- `result_file`（可选，与 `result_dir` 二选一）
- `result_dir`（可选，推荐）
- `table_name`（可选，默认 `poi_qc_zk`）

## 3) 路径与查找策略

运行时路径配置：

- 优先读取 `config/qc_runtime.json`
- 若配置 `result_dir`，作为默认回库目录
- 若 `strict_result_dir=true`，忽略外部传入 `result_dir`，并禁用跨目录恢复搜索

当给 `result_dir` 时，查找顺序：

1. `output/results/{task_id}/results_index.json`
2. 同目录最新合法 `*.complete.json`
3. 受约束恢复搜索（仅 `task_id` 目录）

候选必须通过：

- `task_id` 一致
- 主质检 `result_contract/finalize` 收敛
- 主质检 `result_validator` 校验

若多个合法候选同时存在：

- 先按时间戳选最新
- 时间戳相同再按修改时间
- 仍无法区分才报歧义错误

## 4) 写库前固定流程

1. 加载 `qc_result`
2. 调用主质检技能 `finalize_qc_result` 收敛派生字段
3. 调用主质检技能 `result_validator` 校验
4. 数据映射后执行 SQL `UPDATE`

## 5) 核心映射字段

- `qc_status` <- `qc_result.qc_status`
- `qc_score` <- `qc_result.qc_score`
- `has_risk` <- `qc_result.has_risk`（bool -> int）
- `is_qualified` <- `statistics_flags.is_qualified`
- `is_auto_approvable` <- `statistics_flags.is_auto_approvable`
- `is_manual_required` <- `statistics_flags.is_manual_required`
- `downgrade_issue_type` <- `statistics_flags.downgrade_issue_type`
- `downgrade_status` <- `dimension_results.downgrade_consistency.status`
- `is_downgrade_consistent` <- `dimension_results.downgrade_consistency.is_consistent`
- `qc_result` <- 完整 JSONB
- `quality_status` <- 固定 `'已质检'`

## 6) 安全约束

- 表名必须通过正则校验：`[a-zA-Z_][a-zA-Z0-9_]*`
- 禁止拼接未校验表名到 SQL
- 写库失败必须事务回滚
- 不允许绕过校验直接写库

## 7) 常用调用

```python
from SKILL import execute

result = execute({
    "task_id": "xxx",
    "result_dir": "output/results",
    "table_name": "poi_qc_zk"
})
```

```bash
python SKILL.py <task_id> <result_dir> [table_name]
```

## 8) 返回格式

成功：

```json
{
  "success": true,
  "task_id": "xxx",
  "table_updated": "poi_qc_zk",
  "updated_records": 1
}
```

失败：

```json
{
  "success": false,
  "task_id": "xxx",
  "error": "...",
  "error_type": "ValueError"
}
```

## 9) 追溯文档

完整版说明保留在：

- `./SKILL_FULL.md`
- `./README.md`

