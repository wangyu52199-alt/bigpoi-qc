---
name: quality-check
description: 面向大 POI 核实结果包的后置质检技能。用于读取 `skills-bigpoi-verification` 产出的正式 `index` 文件，交叉校验 `decision / evidence / record` 的结构完整性、跨文件一致性与证据支撑度，并且必须通过脚本生成稳定的 `qc_report`。适用于核实链路完成后需要输出结构化质检结论、退回建议和问题列表时；本技能不得重写原有核实结果文件。
---

# Quality Check

## Core rule

本技能的唯一正式产物是 `qc_report_*.json` 文件路径。

不要输出：

- 自由格式问题摘要代替正式 `qc_report`
- 修改原有 `decision_*.json`
- 修改原有 `evidence_*.json`
- 修改原有 `record_*.json`
- 修改原有 `index_*.json`

## Use bundled scripts

必须使用：

- `quality-check/scripts/write_qc_report.py`
- `quality-check/scripts/validate_qc_report.py`

禁止行为：

- 手写最终 `qc_report_*.json`
- 只根据对话里的摘要做质检，不读取正式结果包
- 读取 `output/runs/{run_id}` 下过程文件替代正式 `index / decision / evidence / record`

## Inputs

正式必填输入：

- `skills-bigpoi-verification` 产出的正式 `index_*.json` 路径

可选增强输入：

- 原始输入 POI 文件：遵循 `skills-bigpoi-verification/schema/input.schema.json`

固定约束：

- `index.files` 应指向正式 `decision / evidence / record` 文件
- 质检只对正式结果包做判断，不回溯过程目录中的中间 JSON 作为正式结论依据
- 若提供原始输入文件，其 `id` 与 `task_id` 必须与结果包一致

## Workflow

1. 读取 `index_*.json`，定位对应 `decision / evidence / record`。
2. 先执行父技能的正式结果校验，把返回结果作为 `bundle_integrity` 检查基础。
3. 再补充以下质检检查：
   - `cross_file_consistency`
   - `evidence_support`
   - `correction_consistency`
   - `input_traceability`（仅在提供原始输入时启用）
4. 运行脚本生成正式质检报告：

```bash
python quality-check/scripts/write_qc_report.py -IndexPath <output/results/{task_id}/index_*.json> -WorkspaceRoot <repo-root> [-PoiPath <input.json>]
```

5. 只把脚本返回的 `qc_report_path` 作为唯一正式输出。

## QC report contract

默认输出目录：

- `output/qc_results/{task_id}/`

正式输出文件：

- `qc_report_<timestamp>.json`

正式报告至少包含：

- `overall.status`
- `overall.recommended_action`
- `checks.bundle_integrity`
- `checks.cross_file_consistency`
- `checks.evidence_support`
- `checks.correction_consistency`
- `metrics`
- `source_bundle`

状态约束：

- `overall.status` 只能是 `pass | manual_review | fail`
- `overall.recommended_action` 只能是 `release | manual_review | return_to_verification`

## Failure handling

如果 `write_qc_report.py` 失败，通常意味着：

- 输入的 `index` 文件无效
- 结果包缺失正式文件
- 质检报告结构未通过 `validate_qc_report.py`

此时必须：

1. 先修正输入 `index` 或上游结果包问题
2. 重新运行 `write_qc_report.py`
3. 只返回新的 `qc_report_path`

不要：

- 直接手改失败后的 `qc_report`
- 在校验器失败时继续把报告当作正式产物交付
- 用自然语言结论跳过脚本化报告

## References to load only when needed

仅在需要时读取：

- `quality-check/schema/qc_report.schema.json`
- `skills-bigpoi-verification/schema/input.schema.json`
- `skills-bigpoi-verification/schema/decision.schema.json`
- `skills-bigpoi-verification/schema/record.schema.json`
- `skills-bigpoi-verification/schema/evidence.schema.json`
- `skills-bigpoi-verification/scripts/validate_result_bundle.py`
