---
name: pre-release-regression-validation
description: 对历史高频样本、当前修复样本、边界样本进行发布前回归验证，输出 JSON/Markdown 报告与发布建议。Use when 需要发布前给出结构化验证结论、失败样本列表和风险摘要，而不是整改方案。
---

# Pre Release Regression Validation

## Overview

执行三桶回归验证并输出发布建议，不输出整改技术方案。

## Workflow

1. 读取回归输入样本。
2. 按桶统计通过率与失败数。
3. 应用阈值规则生成总体判定。
4. 输出 JSON 与 Markdown 报告。
