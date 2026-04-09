# qc-agent-self-improve

## 功能

将人工结果与分流结果转成质检数字员工可消费的结构化改进输入，并支持自动迭代执行。

## 约束

1. 仅处理 `first_routing_target` 为 `qc_agent` 或 `both`
2. 输出问题归类、风险和训练优先级
3. 不输出技术整改方案

## 输入

- ManualResultInput
- FirstRoutingResult
- SecondRoutingResult

## 输出

- `qc_agent_improvement_record`
- `iteration_execution_result`（自动执行阶段）

## 运行

```bash
python src/cli.py \
  --manual-input examples/manual_sample.json \
  --first-routing-input examples/first_routing_sample.json \
  --second-routing-input examples/second_routing_sample.json \
  --output /tmp/qc_improvement.json
```

自动迭代执行：

```bash
python src/iterate_cli.py \
  --improvement-input examples/improvement_record.json \
  --second-routing-input examples/second_routing_result_for_iter.json \
  --target-skill-path /path/to/qc-skill \
  --output /tmp/qc_iteration_result.json
```

## 测试

```bash
pytest tests/test_qc_self_improve.py
```
