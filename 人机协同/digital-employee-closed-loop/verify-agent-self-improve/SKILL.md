---
name: verify-agent-self-improve
description: 仅消费 verify_agent/both 样本，生成核实数字员工的结构化改进输入并可执行自动迭代落地（规则、回归样本、迭代日志）。Use when 需要把人工观察结果沉淀并执行到核实数字员工技能中，且避免输出整改技术方案。
---

# Verify Agent Self Improve

## Overview

将人工观察结果转为核实数字员工迭代输入，并支持自动写入目标技能目录，强调结构化事实与风险信号。

## Workflow

1. 校验输入。
2. 过滤非 verify 目标样本。
3. 组装 issue_summary、模块信号、优先级。
4. 输出标准化记录。
5. 需要时执行自动迭代写入（`src/iterate_cli.py`）。
