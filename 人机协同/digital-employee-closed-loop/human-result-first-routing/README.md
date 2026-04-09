# human-result-first-routing

## 功能

一次分流 skill：读取人工结果，输出 first_routing_result，判断样本优先反哺目标。

当前有效目标仅保留：

- `verify_agent`
- `qc_agent`
- `both`

## 输入

- 人工结果（严格使用 shared 的 ManualResultInput 字段）

## 输出

- `first_routing_result`，字段包含：
  - `sample_id`
  - `first_routing_target`
  - `first_routing_reason`
  - `matched_rules`
  - `confidence`
  - `structured_signals`

## 规则特性

- 规则外置在 `config/first_routing_rules.yaml`
- 支持条件组合：`all` / `any` / `not`
- 支持文本关键词、字段等值、标签命中
- 输出包含命中规则链路，支持回放

## 运行

```bash
python src/cli.py --input examples/sample_qc.json --output /tmp/first_routing_result.json
```

## 测试

```bash
pytest tests/test_first_routing.py
```
