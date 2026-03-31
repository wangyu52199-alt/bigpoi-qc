---
name: bigpoi-verification-qc
version: 2.4.4
description:
  对上游平铺输入做大POI质检。核心维度由 DSL 先判，模型仅处理争议维度，最终结果统一由 finalize 收敛。
metadata:
  rules_path: ./rules/decision_tables.json
  schema_path: ./schema
  config_path: ./config
  runtime_config_path: ../config/qc_runtime.json
  contracts_path: ./scripts/result_contract.py
  finalizers_path: ./scripts/finalize_qc_result.py
  persisters_path: ./scripts/result_persister.py
  validators_path: ./scripts/result_validator.py
  dsl_validators_path: ./scripts/dsl_validator.py
  evidence_preprocessor_path: ./scripts/evidence_preprocessor.py
  dsl_executor_path: ./scripts/dsl_executor.py
  category_fallback_injector_path: ./scripts/inject_category_fallback.py
  poi_type_mapping_script: ./scripts/poi_type_mapping.py
  hybrid_adjudicator_path: ./scripts/hybrid_adjudicator.py
-------------

# QC Skill · Big POI Verification v2.4.4 (Compact)

## 1) 目标与范围

只评估以下 8 个维度，不增不减：

1. `existence`
2. `name`
3. `location`（仅坐标）
4. `address`
5. `administrative`（当前主判 `city`）
6. `category`
7. `evidence_sufficiency`
8. `downgrade_consistency`

不做外部检索，不做开放式自由推断。

## 2) 权威规则来源

规则唯一来源：`./rules/decision_tables.json`（需通过 `./schema/decision_tables.schema.json` 校验）。

关键输入/输出契约：

- `./schema/qc_input.schema.json`
- `./schema/qc_result.schema.json`
- `./config/scoring_policy.json`

说明性文档（非权威）：

- `./rules/README.md`
- `./rules/DETAILED_JUDGMENT_LOGIC.md`
- `./rules/JUDGMENT_PSEUDOCODE.md`
- `./rules/JUDGMENT_CHECKLISTS.md`

## 3) 输入契约（固定平铺）

仅接受平铺输入（不要再做结构归一化）：

- 必要业务字段：`task_id,name,address,x_coord,y_coord,poi_type,city,poi_status,evidence_record`
- 上游人工信号只看：`verify_result`
- `verify_info` 只保留追溯，不参与判定

`verify_result` -> `upstream_manual_review_required`：

- `核实通过` -> `false`
- `需人工核实` / `需要人工核实` -> `true`
- 其他值 -> `false`

## 4) 固定执行流程

必须按顺序执行：

1. 读取平铺输入
2. `evidence_preprocessor.py` 过滤无效证据并规范化 `source_type`
3. `inject_category_fallback.py` 补齐 `matching.category_fallback_support`（缺失 `typecode` 时）
4. `dsl_executor.py` 按 DSL 先判 6 个核心维度（R1-R6）
5. 仅对 `risk/fail` 争议维度允许模型给 `qc_model_judgement` 覆盖建议（可选）
6. `finalize_qc_result.py` 统一收敛（默认重算核心维度）
7. `result_validator.py` 校验最终结果
8. `result_persister.py` 落盘

## 5) 硬约束

禁止事项：

- 手工拼装 `qc_status/qc_score/has_risk/risk_dims/triggered_rules/statistics_flags`
- 跳过 `finalize_qc_result.py` 或 `result_validator.py`
- 使用 `verify_info.*` 参与维度判定
- 创建临时业务脚本绕过现有脚本链路

输出约束：

- 8 个维度都必须存在
- 每个维度必须有 `evidence` 数组
- 分数范围固定 `0-100`，以 `scoring_policy.json` 为准

## 6) 判定口径（精简）

- 先 `fail`，再 `risk`，最后 `pass`
- 高置信默认阈值：`verification.confidence >= 0.85`
- `location` 只比较坐标（地址放在 `address` 判定）
- `administrative` 主判 `city`，可用地址/名称/raw cityname 补充推断
- `category` 优先 `typecode`，缺失时使用 fallback 语义信号
- `evidence_sufficiency` 只评估“自动通过支撑是否足够”，不回写事实维度
- `downgrade_consistency` 只比较 QC 与上游人工核实结论是否一致

具体阈值、分支和证据策略以 DSL 为准，不在本文件重复展开。

## 7) 持久化口径

输出目录由 `result_persister.py` 统一管理：

- 优先 `config/qc_runtime.json` 的 `result_dir`
- 其次 `QC_OUTPUT_DIR`
- 目录结构：`output/results/{task_id}/`

必须生成：

- `{timestamp}_{task_id}.complete.json`
- `{timestamp}_{task_id}.summary.json`
- `{timestamp}_{task_id}.results_index.json`

## 8) 常用命令

```bash
# 1. DSL 先判核心维度
python ./scripts/dsl_executor.py --input input.json --output core_result.json

# 2. finalize 收敛（默认重算核心维度）
python ./scripts/finalize_qc_result.py --input draft_qc_result.json --raw-input input.json --output final_qc_result.json

# 3. 结果校验
python ./scripts/result_validator.py final_qc_result.json

# 4. 落盘
python ./scripts/result_persister.py final_qc_result.json
```

## 9) 追溯文档

完整版说明保留在：

- `./SKILL_FULL.md`
- `./CHANGELOG.md`
- `./CLAUDE.md`

