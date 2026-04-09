# verify-agent-self-improve

## 功能

将人工结果 + 分流结果转成核实数字员工可消费的结构化改进输入，并支持自动迭代执行。

## 约束

1. 仅处理 `first_routing_target` 为 `verify_agent` 或 `both`
2. 不输出技术整改方案
3. 输出结构化改进输入与优先级

## 输入

- ManualResultInput
- FirstRoutingResult
- SecondRoutingResult

## 输出

- `verify_agent_improvement_record`
- `iteration_execution_result`（自动执行阶段）

## 运行

```bash
python src/cli.py \
  --manual-input examples/manual_sample.json \
  --first-routing-input examples/first_routing_sample.json \
  --second-routing-input examples/second_routing_sample.json \
  --output /tmp/verify_improvement.json
```

自动迭代执行：

```bash
python src/iterate_cli.py \
  --improvement-input examples/improvement_record.json \
  --second-routing-input examples/second_routing_result_for_iter.json \
  --target-skill-path /path/to/verify-skill \
  --output /tmp/verify_iteration_result.json
```

## 测试

```bash
pytest tests/test_verify_self_improve.py
```
