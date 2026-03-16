---
name: bigpoi-qc-audit
description: 质检上游大POI核实结果与证据是否匹配，判断核实结论是否被证据充分支撑。用于审核政府、机场、火车站、5A景区等重点标志性POI的核实输出，输入包含原始POI信息、上游核实结论与其证据材料。
---

# Big POI QC Audit

## Overview

对上游大POI核实数字员工的输出做质检，逐条核对证据与结论的匹配度，给出“核实正确 / 核实不正确 / 需人工复核”的质检结论和理由。重点不是重新做核实，而是判断“现有证据是否足以支撑上游结论”。

## Schema Contract

- 输入必须符合 `references/input-schema.json`。
- 输出必须严格符合 `references/output-schema.json`。
- 如果用户给的是自然语言、表格或非结构化 JSON，先在内部归一化到 input schema，再开始质检。
- 输出时只返回 schema 允许的 JSON 字段，不要额外加 Markdown、解释前缀或围栏代码块。

## Inputs

输入顶层固定为以下四段：

- `schema_version`
- `input_poi`
- `upstream_result`
- `evidence_bundle`

其中：

- `input_poi` 表示原始待核实 POI 信息。
- `upstream_result` 表示上游核实数字员工的最终结论与字段级断言。
- `evidence_bundle` 表示上游收集到的证据列表。
- 所有证据必须有稳定 `evidence_id`，供输出回溯引用。

## Working Mode

- 仅基于输入证据做质检，不自行补搜。
- 将每条证据绑定证据ID，所有判断必须可回溯到证据ID。
- 先审字段，再审总结论；不要先接受上游结论再反向找支持。
- 默认中文输出。

## Workflow

1. 识别 POI 类别：
   - 政府机构
   - 机场
   - 火车站/高铁站/铁路客运站
   - 5A 景区
   - 其他重点标志性 POI
2. 结构化读取输入，拆出待质检字段：
   - 名称
   - 存在性
   - 类型
   - 地址
   - 坐标
   - 其它关键属性
3. 建立“字段 -> 证据”映射，逐条标记：
   - `support`
   - `conflict`
   - `insufficient`
4. 按字段级最低证据要求评估是否达标，详见 `references/poi-qc-rubric.md`。
5. 结合 POI 类别应用特定规则，处理别名、曾用名、管理机构地址、主入口坐标、景区范围坐标等复杂情况。
6. 识别是否命中上游常见误判模式，详见 `references/upstream-failure-patterns.md`。
7. 最后再判断上游最终结论是否成立：
   - 若关键字段均被充分支撑，且不存在重大冲突，判 `pass`
   - 若关键字段被证据明确推翻，或上游越过证据做了不应有的断言，判 `fail`
   - 若证据不足、冲突未消解、字段覆盖不完整，判 `manual`

## Mandatory Checks

每次都必须输出以下五类 `claim_checks`，即使输入字段缺失，也要用 `insufficient` 标记：

- 名称：是否为官方名称、规范简称、曾用名或别名；是否发生更名。
- 存在性：证据是否证明该 POI 当前真实存在，而不是历史存在、规划中或已停用。
- 类型：是否是上游声称的 POI 类别，避免把管理单位、片区、园区、航站楼、游客中心误当成目标 POI。
- 地址：是否是 POI 本体地址，而非上级单位、管理委员会、售票处、办公区地址。
- 坐标：是否对应 POI 主体、主入口或约定俗成的定位点；是否存在明显漂移。

## Type-Specific Rules

### 政府机构

- 优先使用政府官网、编制/机构名录、官方公告。
- 名称需区分机关本体与下属事业单位、服务大厅、行政中心楼宇。
- 地址需优先认定对外办公地址；仅有邮寄地址或历史办公地址时，通常判 `manual`。
- 坐标允许落在办公楼或政务服务中心主入口附近，但不能落到街道、园区或关联单位。

### 机场

- 优先使用民航局、机场官网、航旅官方资料、政府交通公告。
- 区分机场整体、航站楼、机场集团、机场公司、货运区。
- 名称若含旧机场名、新机场名、三字码相关别称，要确认是否为同一机场实体。
- 坐标优先接受航站楼主入口或机场主体中心点；若上游把停车场、地铁站、机场集团办公楼当作机场坐标，通常判 `fail`。

### 火车站 / 高铁站

- 优先使用铁路 12306、国铁/地方铁路官方页面、交通主管部门公告。
- 区分车站本体、站房、站区、铁路局、地铁换乘站。
- 名称需处理“东站/西站/南站/北站”以及老站新站并存问题。
- 地址可接受站房官方地址；若证据只指向站前广场或综合交通枢纽，且无法确认主站房，通常判 `manual`。

### 5A 景区

- 优先使用文旅部、文旅厅局、景区官网、5A 名录。
- 名称需与官方景区名一致，避免用景区内单个景点、游客中心、售票点代替景区本体。
- 地址允许为景区管理地址或主入口地址，但必须说明是哪一种。
- 坐标通常允许主入口、游客中心或景区公认定位点；若上游声称“景区中心坐标”但证据只证明游客中心位置，判 `manual`。

### 其他重点标志性 POI

- 先判断其最接近哪一类规则，再套用相近类型的证据优先级。
- 若无法明确类别，降低自动通过阈值，倾向 `manual`。

## Decision Rules

- `pass`：
  - 关键字段都有足够证据支撑。
  - 证据之间无未解释的实质冲突。
  - 上游结论没有超出证据覆盖范围。
- `fail`：
  - 任一关键字段被高等级证据明确推翻。
  - 上游把关联实体误判为目标 POI。
  - 上游把“部分可证”扩展成“全部通过”。
- `manual`：
  - 关键字段缺证。
  - 冲突存在但无法消解。
  - 证据只支持低精度结论，不足以支持上游的高精度断言。

## Confidence Rules

- `0.85-1.00`：核心字段均有高质量独立证据支持。
- `0.60-0.84`：主要字段可支撑，但存在轻微歧义或少量补充证据不足。
- `0.40-0.59`：部分字段可判断，但关键字段仍缺证或存在未消解冲突。
- `<0.40`：证据严重不足或冲突明显。

## Output Format

默认输出 JSON，且必须满足 `references/output-schema.json`。枚举字段使用 schema 中的英文 code，说明文本使用中文。

```json
{
  "schema_version": "bigpoi_qc_audit_output/v1",
  "qc_decision": "pass | fail | manual",
  "qc_summary": "简要结论",
  "poi_category": "government | airport | railway_station | scenic_5a | other",
  "claim_checks": [
    {
      "claim": "name | existence | type | address | coordinates | other",
      "upstream_value": "上游给出的字段值",
      "evidence_ids": ["E1", "E2"],
      "support_level": "support | conflict | insufficient",
      "notes": "关键说明",
      "confidence": 0.0
    }
  ],
  "issues": [
    {
      "code": "ADDRESS_CONFLICT",
      "severity": "critical | major | minor",
      "message": "问题说明",
      "related_claims": ["address"]
    }
  ],
  "missing_evidence": [
    {
      "claim": "coordinates",
      "required_evidence": "缺失的证据类型",
      "why_missing": "缺口说明",
      "preferred_source_tier": "A1 | A2 | B1 | B2"
    }
  ],
  "matched_failure_patterns": ["FP01", "FP08"],
  "confidence": 0.0,
  "recommended_action": "accept_upstream_result | send_back_for_reverification | request_more_evidence | send_to_human_review",
  "recommended_action_note": "执行建议"
}
```

输出时遵循以下要求：

- `qc_summary` 先说总判断，再说关键原因。
- `claim_checks` 必须至少覆盖 `name`、`existence`、`type`、`address`、`coordinates` 五项。
- `issues` 使用结构化对象，不要输出纯字符串数组。
- `missing_evidence` 要具体到“缺什么来源、缺哪个字段的什么证明”。
- `recommended_action` 必须使用固定枚举；自由说明写在 `recommended_action_note`。
- 输出必须是单个 JSON 对象，不要附加额外文本。

## Reference

需要详细判定标准时，阅读以下文件：

- `references/input-schema.json`
- `references/output-schema.json`
- `references/poi-qc-rubric.md`
- `references/upstream-failure-patterns.md`
