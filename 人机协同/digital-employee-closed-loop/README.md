# digital-employee-closed-loop

围绕 `POI 核实数字员工 + 质检数字员工 + 人工作业员` 的协同闭环仓库。

## 1. 设计目标

1. 人工只填写“表征现象 + 结构化判断 + 必要补充证据”。
2. 人工不填写整改方案。
3. 闭环 skill 自动执行：
   - 一次分流（first routing）
   - 二次分流（second routing）
   - 核实数字员工自我迭代输入生成
   - 质检数字员工自我迭代输入生成
   - 核实数字员工自动迭代执行
   - 质检数字员工自动迭代执行
   - 发布前回归验证

## 2. 仓库结构

```text
digital-employee-closed-loop/
├── README.md
├── pyproject.toml
├── requirements.txt
├── shared/
├── human-result-first-routing/
├── human-result-second-routing/
├── verify-agent-self-improve/
├── qc-agent-self-improve/
├── integrations/
├── scripts/
└── pre-release-regression-validation/
```

## 3. 输入字段约束

人工输入字段严格沿用业务定义（包括 `verify_action_is_correct` 等关键字段），统一由 `shared/schemas/manual_result.py` 校验。

## 4. 快速开始

### 4.1 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.2 运行一次分流

```bash
cd human-result-first-routing
python src/cli.py --input examples/sample_qc.json --output /tmp/first_routing_result.json
```

### 4.3 运行二次分流

```bash
cd ../human-result-second-routing
python src/cli.py \
  --manual-input examples/manual_sample.json \
  --first-routing-input examples/first_routing_sample.json \
  --output /tmp/second_routing_result.json
```

### 4.4 运行 verify 自我迭代输入生成

```bash
cd ../verify-agent-self-improve
python src/cli.py \
  --manual-input examples/manual_sample.json \
  --first-routing-input examples/first_routing_sample.json \
  --second-routing-input examples/second_routing_sample.json \
  --output /tmp/verify_improvement.json
```

### 4.5 运行 qc 自我迭代输入生成

```bash
cd ../qc-agent-self-improve
python src/cli.py \
  --manual-input examples/manual_sample.json \
  --first-routing-input examples/first_routing_sample.json \
  --second-routing-input examples/second_routing_sample.json \
  --output /tmp/qc_improvement.json
```

### 4.6 运行发布前回归验证

```bash
cd ../pre-release-regression-validation
python src/cli.py \
  --input examples/regression_input.json \
  --output-json /tmp/regression_report.json \
  --output-md /tmp/regression_report.md
```

### 4.7 运行 verify 自动迭代执行

```bash
cd ../verify-agent-self-improve
python src/iterate_cli.py \
  --improvement-input examples/improvement_record.json \
  --second-routing-input examples/second_routing_result_for_iter.json \
  --target-skill-path /path/to/verify-skill \
  --output /tmp/verify_auto_iteration_result.json
```

### 4.8 运行 qc 自动迭代执行

```bash
cd ../qc-agent-self-improve
python src/iterate_cli.py \
  --improvement-input examples/improvement_record.json \
  --second-routing-input examples/second_routing_result_for_iter.json \
  --target-skill-path /path/to/qc-skill \
  --output /tmp/qc_auto_iteration_result.json
```

### 4.9 接入真实技能目录（一键）

当前已提供真实目录映射配置：

- `integrations/targets.yaml`

执行：

```bash
python scripts/run_real_integration.py \
  --manual-input shared/examples/sample_03_both_issue.json
```

执行结果会输出到：

- `integration-output/last_integration_result.json`

### 4.10 一键闭环流水线（推荐）

如果希望明确看到“人工输入 -> 一次分流 -> 二次分流 -> self-improve -> 自动落地”的完整链路，执行：

```bash
python scripts/run_closed_loop_pipeline.py \
  --manual-input shared/examples/sample_03_both_issue.json \
  --output integration-output/closed_loop_last_run.json
```

`both` 场景会自动拆成 verify/qc 两条子链路，分别生成二次分流与改进记录，避免模块写入串线。

### 4.11 批量执行 + 回归报告自动汇总

```bash
python scripts/run_batch_closed_loop_with_regression.py \
  --manual-jsonl integrations/examples/manual_batch_samples.jsonl \
  --historical-input integrations/examples/historical_samples.json \
  --boundary-input integrations/examples/boundary_samples.json \
  --run-id demo_batch_001 \
  --dry-run
```

输出目录示例：

- `integration-output/batch/demo_batch_001/batch_run_summary.json`
- `integration-output/batch/demo_batch_001/regression_input.json`
- `integration-output/batch/demo_batch_001/regression_report.json`
- `integration-output/batch/demo_batch_001/regression_report.md`
- `integration-output/batch/demo_batch_001/samples/*.json`

### 4.12 定时执行（cron 示例）

可按小时定时触发批处理脚本（示例每 2 小时执行一次）：

```bash
0 */2 * * * cd /Users/summer/Documents/bigpoi-qc/人机协同/digital-employee-closed-loop && /usr/bin/python3 scripts/run_batch_closed_loop_with_regression.py --manual-jsonl integrations/examples/manual_batch_samples.jsonl --historical-input integrations/examples/historical_samples.json --boundary-input integrations/examples/boundary_samples.json --run-id cron_$(date +\\%Y\\%m\\%d_\\%H\\%M) >> integration-output/batch/cron.log 2>&1
```

## 5. 测试

在仓库根目录执行：

```bash
pytest
```

覆盖：

1. schema 校验通过/失败
2. 一次分流规则命中
3. 二次分流规则命中
4. verify/qc 自我迭代样本过滤
5. 回归报告 JSON/Markdown 生成
