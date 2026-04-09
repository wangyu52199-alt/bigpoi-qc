---
name: human-result-second-routing
description: 在一次分流结果基础上进行模块级二次分流，输出 primary_module 与 module_candidates，并记录规则命中链路。Use when 需要将人工观察结果映射到 verify_agent 或 qc_agent 的具体能力模块。
---

# Human Result Second Routing

## Overview

根据一次分流目标、标签与文本信号，输出二级模块分流结果。

## Workflow

1. 校验人工输入与一次分流输入。
2. 读取二次分流规则配置。
3. 计算模块分数并生成主模块/候选模块。
4. 输出链路可回放结果。

## Output Contract

输出见 `schema/second_routing_result.schema.json`。
