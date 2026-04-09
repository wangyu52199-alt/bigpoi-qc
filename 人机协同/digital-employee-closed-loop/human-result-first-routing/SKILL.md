---
name: human-result-first-routing
description: 对人工结果执行一次分流，判断优先反哺目标（verify_agent、qc_agent、both）。Use when 需要将人工结构化观察结果自动路由到闭环模块，并输出可追踪的命中规则链路。
---

# Human Result First Routing

## Overview

根据人工结果字段与规则配置，输出一级分流目标与理由，不输出整改建议。

## Workflow

1. 校验输入 schema。
2. 读取规则配置。
3. 执行规则匹配并记录命中链路。
4. 生成 first_routing_result。

## Output Contract

输出见 `schema/first_routing_result.schema.json`。
