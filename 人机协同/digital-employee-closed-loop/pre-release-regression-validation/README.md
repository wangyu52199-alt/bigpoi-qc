# pre-release-regression-validation

## 功能

发布前回归验证 skill：对三类样本分桶验证，输出机器可读 JSON 与人类可读 Markdown。

## 输入

- `historical_high_frequency`
- `current_fix_target`
- `boundary_cases`

## 输出

- `regression_report.json`
- `regression_report.md`

报告字段包含：

- `overall_pass`
- `bucket_results`
- `failed_samples`
- `risk_summary`
- `release_recommendation`
- `metrics_summary`

## 运行

```bash
python src/cli.py \
  --input examples/regression_input.json \
  --output-json /tmp/regression_report.json \
  --output-md /tmp/regression_report.md
```

## 测试

```bash
pytest tests/test_regression_validation.py
```
