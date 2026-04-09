# human-result-second-routing

## 功能

二次分流 skill：在一次分流基础上，判断具体改进模块（主模块 + 候选模块）。

## 输入

1. 人工结果（ManualResultInput）
2. 一次分流结果（FirstRoutingResult）

## 输出

- `second_routing_result`
  - `sample_id`
  - `primary_module`
  - `module_candidates`
  - `second_routing_reason`
  - `matched_rules`
  - `structured_signals`

## 运行

```bash
python src/cli.py \
  --manual-input examples/manual_sample.json \
  --first-routing-input examples/first_routing_sample.json \
  --output /tmp/second_routing_result.json
```

## 测试

```bash
pytest tests/test_second_routing.py
```
