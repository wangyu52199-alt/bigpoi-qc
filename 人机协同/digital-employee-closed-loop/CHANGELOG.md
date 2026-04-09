# Changelog

## 2026-04-09

### Added

- 初始化仓库 `digital-employee-closed-loop`。
- 新增 shared 层 schema/taxonomy/utils/examples/tests。
- 新增 5 个 skill 子模块：
  - human-result-first-routing
  - human-result-second-routing
  - verify-agent-self-improve
  - qc-agent-self-improve
  - pre-release-regression-validation
- 新增配置化规则与阈值配置（YAML）。
- 新增可执行 CLI 与最小可运行测试。
- 新增顶层 `README.md`、`requirements.txt`、`pyproject.toml`。

### Changed

- 一级分流目标收敛为 `verify_agent`、`qc_agent`、`both`。
- 移除一级分流中的 `upstream_data_issue`、`policy_or_taxonomy_issue`、`hold_for_manual_review` 输出分支。
- 一级分流默认回退策略调整为 `both`（双路由）。
- 补充一级分流回归测试，覆盖上游/口径样本默认双路由行为。

### Added

- 新增 `verify-agent-auto-iteration` 执行型 skill（自动写入核实技能规则、回归样本、迭代日志）。
- 新增 `qc-agent-auto-iteration` 执行型 skill（自动写入质检技能规则、回归样本、迭代日志）。
- shared 层新增自动迭代执行结果 schema 与文件写入工具函数。
- 新增自动迭代执行模块测试（dry-run + apply 两种模式）。
- 新增真实技能目录接入配置 `integrations/targets.yaml`。
- 新增一键接入脚本 `scripts/run_real_integration.py`。
- 已完成对以下目录的自动接入写入：
  - `/Users/summer/Documents/bigpoi-qc/人机协同/Product/skills-bigpoi-verification/auto-iteration/`
  - `/Users/summer/Documents/bigpoi-qc/人机协同/BigPoi-verification-qc-stable/auto-iteration/`

### Changed

- 将自动迭代执行能力并入 `verify-agent-self-improve` 和 `qc-agent-self-improve`（每个 skill 同时支持“改进输入生成 + 自动落地执行”）。
- 根目录流程收敛为 5 个核心技能，不再独立维护 auto-iteration skill。

### Added

- 新增一键闭环脚本 `scripts/run_closed_loop_pipeline.py`：
  - 输入人工结果后自动串联一次分流、二次分流、verify/qc self-improve、自动迭代落地。
- 新增端到端测试 `tests/test_closed_loop_pipeline.py`，覆盖 `both` 场景双子链路落地。

### Changed

- `scripts/run_real_integration.py` 从“示例 improvement 直写”升级为调用闭环流水线，默认从人工输入驱动。
- `integrations/targets.yaml` 收敛为真实接入必需字段（`skill_path`、`config_path`）。
- 修正 `both` 场景模块选择：verify/qc 迭代引擎会优先选择各自模块集合内的主模块，避免跨域写入。

### Added

- 新增批处理脚本 `scripts/run_batch_closed_loop_with_regression.py`：
  - 支持读取人工结果 JSONL 批量执行闭环；
  - 自动汇总 `current_fix_target` 回归样本；
  - 自动生成 `regression_input.json`、`regression_report.json`、`regression_report.md`。
- 新增批处理示例输入：
  - `integrations/examples/manual_batch_samples.jsonl`
  - `integrations/examples/historical_samples.json`
  - `integrations/examples/boundary_samples.json`
- 新增批处理回归测试 `tests/test_batch_closed_loop_with_regression.py`。

### Changed

- `README.md` 补充批量执行与定时执行（cron）示例命令。
