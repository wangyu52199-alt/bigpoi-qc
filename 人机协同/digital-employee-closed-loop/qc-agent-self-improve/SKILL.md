---
name: qc-agent-self-improve
description: 仅消费 qc_agent/both 样本，围绕误拦截、漏拦截、规则不稳、证据不足、解释不足输出结构化改进输入并可自动迭代落地（规则、回归样本、迭代日志）。Use when 需要将人工质检观察结果沉淀并执行到 qc 数字员工技能中。
---

# QC Agent Self Improve

## Overview

将人工观察结果整理为质检数字员工迭代记录，并支持自动写入目标技能目录，强调拦截正确性与证据风险。

## Workflow

1. 校验输入。
2. 过滤非 qc 目标样本。
3. 归类拦截问题类型。
4. 输出结构化改进输入。
5. 需要时执行自动迭代写入（`src/iterate_cli.py`）。
