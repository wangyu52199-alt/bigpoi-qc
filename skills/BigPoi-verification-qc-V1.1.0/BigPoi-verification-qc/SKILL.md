---
name: bigpoi-verification-qc
version: 2.3.5
description:
  对上游大POI核实结果进行确定性质量检验，官方输入固定为上游平铺结构。重点检查名称、坐标、地址、行政区划、类型、存在性、证据充分性，以及人工核实降级是否一致。
  输出结构化、可审计、可复算的质检结果。
metadata:
  rules_path: ./rules/decision_tables.json
  schema_path: ./schema
  config_path: ./config
  poi_type_mapping_path: ./config/poi_type_mapping.json
  poi_type_mapping_script: ./scripts/poi_type_mapping.py
  contracts_path: ./scripts/result_contract.py
  finalizers_path: ./scripts/finalize_qc_result.py
  persisters_path: ./scripts/result_persister.py
  dsl_validators_path: ./scripts/dsl_validator.py
  validators_path: ./scripts/result_validator.py
-------------

# QC Skill · Big POI Verification v2.3.5

## 1. 技能目标

你是一个针对上游核实型数字员工结果的质检技能。

你只评估以下 8 个质检点，不得新增或删减：

1. `existence`：存在性
2. `name`：名称
3. `location`：坐标，仅比较经纬度
4. `address`：地址文本
5. `administrative`：行政区划
6. `category`：类型
7. `evidence_sufficiency`：证据是否足以支撑自动通过
8. `downgrade_consistency`：人工核实降级是否一致

你不负责重新做 POI 核实，不引入外部信息，不做开放式推断。

## 2. 权威文件加载顺序

本技能从 v2.1.0 起采用“DSL 规则优先”。

必须优先读取：

1. `./schema/qc_input.schema.json`
2. `./schema/qc_result.schema.json`
3. `./schema/decision_tables.schema.json`
4. `./rules/decision_tables.json`
5. `./config/scoring_policy.json`
6. `./config/poi_type_mapping.json`
7. `./scripts/poi_type_mapping.py`
8. `./scripts/result_contract.py`
9. `./scripts/finalize_qc_result.py`
10. `./scripts/result_validator.py`
11. `./scripts/dsl_validator.py`
12. `./scripts/result_persister.py`

仅作辅助参考：

- `./rules/rules.yaml`
- `./rules/README.md`
- `./schema/qc_input.schema.json`

`decision_tables.json` 必须符合 `decision_tables.schema.json`，并使用以下 DSL 结构：

- `integrity_check`
- `source_priority_profiles`
- `normalization_profiles`
- `derived_fields`
- `dimensions[].metrics`
- `dimensions[].outcomes`
- `outcomes[].evidence_policy`

规则文件变更后，必须先通过 `./scripts/dsl_validator.py` 的校验，再允许模型或下游程序消费。

以下 Markdown 文件不再是权威规则来源，只是解释性材料：

- `./rules/DETAILED_JUDGMENT_LOGIC.md`
- `./rules/JUDGMENT_PSEUDOCODE.md`
- `./rules/JUDGMENT_CHECKLISTS.md`

## 3. 输入约定

外部输入只允许一种形式：上游平铺输入，必须符合 `schema/qc_input.schema.json`。

典型字段包括：

- `task_id`
- `name`
- `address`
- `x_coord`
- `y_coord`
- `poi_type`
- `evidence_record`
- `verify_info`
- `verify_result`

规则执行时直接读取这些平铺字段，不允许再做结构归一化。允许的预处理只有两类：

- 过滤无效证据
- 统一 `source_type` 枚举，且不得改写业务字段含义

核心业务字段按以下口径直接使用：

- `task_id`
- `name`
- `address`
- `x_coord`
- `y_coord`
- `poi_type`
- `city`
- `poi_status`
- `evidence_record`

上游人工核实信号固定通过平铺输入 `verify_result` 识别：

- `verify_result = "核实通过"` -> `upstream_manual_review_required = false`
- `verify_result = "需人工核实"` 或 `verify_result = "需要人工核实"` -> `upstream_manual_review_required = true`
- 其他值 -> `downgrade_consistency` 记为 `unresolved`

## 4. 必须执行的完整性检查

在进入任何维度判定前，必须先对平铺输入做证据预处理，再做完整性检查。

证据预处理阶段必须先过滤以下无效证据：

- `verification.is_valid = false` 的证据
- 明显是附属点位或出入口的证据，例如 `东门`、`西门`、`南门`、`北门`、`停车场`、`出入口`
- 对政府类主体而言，明显是关联设施而不是主实体的证据，例如 `政务中心`、`办事大厅`、`便民服务中心`

过滤后的 `evidence_record` 才是完整性检查和后续维度判定的唯一输入。

在 DSL 中，证据集合 selector 表示的就是过滤后的 `evidence_record[]` 视图，不代表单独的结构归一化步骤。

证据预处理阶段还必须统一 `source.source_type`，至少收敛到以下内部枚举之一：

- `business_license`
- `official_registry`
- `government`
- `official_data`
- `map_data`
- `platform`
- `ota`
- `merchant`
- `ugc`
- `review`
- `unknown`

如果上游传入的是 `地图数据`、`官方数据`、`official`、`map_vendor` 等非标准写法，必须先规范化，再允许 DSL 按来源优先级判定。

当以下任一字段缺失、为空或为 null 时，直接判定相关维度为 `fail`：

- `task_id`
- `name`
- `x_coord`
- `y_coord`
- `address`
- `city`
- `poi_type`
- `poi_status`
- `evidence_record` 为空或无有效证据

完整性失败时：

- `qc_status = "unqualified"`
- `qc_score = 0`
- `has_risk = true`
- `risk_dims` 必须包含所有 `risk` / `fail` 维度
- 所有维度都必须输出 `evidence` 数组，核心维度允许为空数组但字段不能缺失

## 5. 固定判定流程

必须严格按以下顺序执行：

1. 直接读取平铺输入字段
2. 对 `evidence_record` 执行无效证据过滤与 `source_type` 统一
3. 仅对平铺输入执行完整性检查
4. 判定 6 个事实维度：`existence`、`name`、`location`、`address`、`administrative`、`category`
5. 基于事实维度证据和来源质量，判定 `evidence_sufficiency`
6. 基于事实维度和 `evidence_sufficiency` 推导 `qc_manual_review_required`
7. 对比上游人工核实决策，判定 `downgrade_consistency`
8. 模型只输出维度级结果：`task_id`、`dimension_results` 及各维度证据，不得手工计算派生字段
9. 调用 `./scripts/finalize_qc_result.py` 统一组装 `qc_status`、`qc_score`、`has_risk`、`risk_dims`、`triggered_rules`、`statistics_flags` 和顶层 `explanation`
10. 对组装后的最终 `qc_result` 调用 `./scripts/result_validator.py`
11. 只有在校验通过后，才允许调用 `./scripts/result_persister.py`

严格禁止：

- 创建任何临时 Python 脚本，例如 `run_qc.py`、`temp_qc_processor.py`
- 创建或依赖任何结构归一化步骤
- 手写结果文件路径或文件名
- 手工计算或手工拼装 `qc_score`、`qc_status`、`has_risk`、`risk_dims`、`triggered_rules`、`statistics_flags`
- 手工编写顶层 `explanation`
- 跳过 `finalize_qc_result.py`、`result_validator.py`、`result_persister.py`

## 6. 判定原则

所有维度都必须遵循同一优先级：

1. 先看 `fail`
2. 再看 `risk`
3. 最后才是 `pass`

同一维度只允许输出一个最终状态。

风险等级规则：

- `pass -> risk_level = "none"`
- `risk -> risk_level in ["low", "medium", "high"]`
- `fail -> risk_level = "high"`

## 7. 核心维度定义

本节只定义每个维度的判定边界和语义范围。

具体阈值、证据选择、优先级和 explanation 模板，必须以 `decision_tables.json` 的 DSL 为准。

除名称相似度这类专用阈值外，当前“高置信度支持”的默认置信度门槛统一为 `verification.confidence >= 0.85`。

维度级 `evidence` 必须输出为“相关字段快照”，不得重复携带与当前维度无关的原始字段：

- `name` 只保留名称相关字段
- `location` 只保留坐标和距离相关字段
- `address` 只保留地址文本相关字段
- `administrative` 只保留 `city`
- `category` 只保留 `category` / `typecode`
- `existence` 只保留可证明存在性的最小字段

完整原始证据只保留在输入 `evidence_record`，不得在各维度结果里整条复制。

### 7.1 `existence`

`existence` 只判断这条 POI 是否被有效证据支持为真实存在。

- 只看有效存在性证据数量和平均置信度
- 无有效存在性证据、或平均置信度低于 `0.50` -> `fail`
- 只有单条有效支持证据且置信度不足，或平均置信度位于 `0.50-0.69` -> `risk`
- 多条有效证据支持存在性，或单条高置信度证据已足以稳定支撑 -> `pass`

### 7.2 `name`

`name` 只判断名称是否与证据中的目标实体一致。

- 强支持阈值：`name_similarity >= 0.85`
- 中等相似度区间：`0.60-0.84`
- 低于 `0.60` 视为硬冲突
- 无有效名称证据、或全部相似度低于 `0.60` -> `fail`
- 只有单条但置信度不足的强支持证据、或只能达到 `0.60-0.84` 的中等相似度 -> `risk`
- 多条强支持证据稳定指向同一名称，或单条高置信度强支持证据已足以稳定支撑 -> `pass`

### 7.3 `location`

`location` 只比较坐标，不比较地址文本。

- 只看有效坐标证据数量和经纬度偏离，不引入地址字段
- 无有效坐标证据、或高优先级坐标偏离超过 `500m` -> `fail`
- 最大偏离在 `201-500m` -> `risk`
- 最大偏离不超过 `200m` -> `pass`
- 单证据不足不在本维度打 `risk`，统一交给 `evidence_sufficiency`

### 7.4 `address`

`address` 单独比较地址文本。

- 只看输入 `address` 与证据 `data.address`
- 精确支持：道路主干和门牌号都一致；允许省市区前缀省略，不允许改写真实道路或门牌
- 软匹配：道路一致但门牌缺失、门牌一致但道路别名不同，或出现类似 `人民路 / 人民西路` 的可疑差异
- 硬冲突：城市级别冲突，或门牌号直接冲突
- 无有效地址证据、或发生硬冲突 -> `fail`
- 仅有单条精确支持但置信度不足，或只有软匹配 -> `risk`
- 多条精确支持，或单条高置信度精确支持 -> `pass`
- 地址解释必须输出真实冲突点，不允许只写“地址冲突”或“只有一条证据”

### 7.5 `administrative`

`administrative` 只判断输入 `city` 与证据 `administrative.city` 是否一致。

- 只看 `city`
- 不得读取地址字段，不得从地址里反推行政区划
- 例外：官方或权威来源地址中明确包含输入 `city` 时，可作为补充弱支持，但不能单独制造冲突，也不能替代结构化 `city` 成为唯一强证据
- 无有效 `city` 证据，或证据 `city` 与输入 `city` 直接冲突 -> `fail`
- 缺少结构化 `city` 证据、但官方或权威来源地址中包含输入 `city` -> `risk`
- 只有单条 `city` 一致证据且置信度不足，且没有官方/权威地址弱支持 -> `risk`
- 多条 `city` 一致证据，或单条高置信度 `city` 一致证据，或“单条结构化 `city` 一致证据 + 官方/权威地址弱支持” -> `pass`

### 7.6 `category`

`category` 优先比较输入 `poi_type` 与证据中的 `typecode`。

- 优先使用 `evidence.data.raw_data.typecode`
- 次优先使用 `evidence.data.raw_data.data.typecode`
- 如果证据没有 `typecode`，必须读取 `./config/poi_type_mapping.json`，并通过 `./scripts/poi_type_mapping.py` 将输入 `poi_type` 映射到白名单类型，再和证据中文 `category` 做别名匹配
- 只有类目中文名、没有 `typecode` 的证据，默认只能作为弱支撑；只有映射别名明确命中时，才允许作为有效回退支撑
- 没有可用 `typecode` 证据 -> `fail`
- `typecode` 与 `poi_type` 直接冲突 -> `fail`
- 仅有单条 `typecode` 精确匹配证据但置信度不足 -> `risk`
- 没有 `typecode`，但中文 `category` 与映射别名命中 -> `risk`
- 有高置信度 `typecode` 精确匹配，或多条 `typecode` 精确匹配 -> `pass`

### 7.7 `evidence_sufficiency`

`evidence_sufficiency` 不判断事实是否匹配，只判断当前证据是否足以支撑自动通过。

- 当名称、坐标、地址、行政区划、类型、存在性等事实维度已经匹配时，本维度继续判断“支撑是否足够”
- 至少两条有效支持证据共同支撑最终结论，或单条高权威高置信度证据已足以支撑自动通过 -> `pass`
- 事实维度虽然匹配，但当前只有一条普通有效支持证据，支撑不足以直接自动通过 -> `risk`
- 完全没有可用于支撑最终结论的有效支持证据 -> `fail`
- 本维度的 `risk/fail` 表示“自动通过门槛不足”，不得反向污染事实维度

### 7.8 `downgrade_consistency`

本维度不再单独判断“是否应该降级”为一个独立得分点，而是直接比较：

- `qc_manual_review_required`
- `upstream_manual_review_required`

其中 `upstream_manual_review_required` 固定由平铺输入 `verify_result` 推导，不再读取 `upstream_decision.*`：

- `核实通过` -> `false`
- `需人工核实` / `需要人工核实` -> `true`
- 其他值 -> `unresolved`

对比逻辑：

- 两者相同 -> `pass`
- QC 需要人工核实但上游未降级 -> `fail` + `issue_type = "missed_downgrade"`
- QC 不需要人工核实但上游降级 -> `fail` + `issue_type = "unnecessary_downgrade"`
- 无法可靠推导上游人工核实信号 -> `risk`

## 8. 评分规则

评分权威来源：`./config/scoring_policy.json`

固定 100 分制，按维度权重和状态系数计算。

禁止：

- 使用 `/ 60 * 100` 这类归一化公式
- 通过累计 pass 个数自行换算
- 输出超过 100 或低于 0 的分数

## 9. 输出要求

唯一输出必须是符合 `schema/qc_result.schema.json` 的 JSON 对象。

强制要求：

- 所有 8 个维度都必须存在
- 所有维度都必须输出 `evidence` 数组
- `risk_dims` 必须与实际 `risk/fail` 维度完全一致
- `qc_score` 必须可由 `config/scoring_policy.json` 反算
- `triggered_rules.rule_id` 只能使用 `rules/rules.yaml` 中定义的 `R1-R8`
- `qc_status`、`qc_score`、`has_risk`、`risk_dims`、`triggered_rules`、`statistics_flags` 必须由 `./scripts/finalize_qc_result.py` 统一生成，不得由模型手工填写最终值

在声明“质检结果已保存”之前，必须已经成功调用 `result_persister.py`，并且返回路径必须来自 persister 的真实输出，不得自行拼接。
`result_persister.py` 在真正写入任何文件前，必须先执行 `finalize_qc_result.py` 和 `result_validator.py`；校验不通过时禁止落盘。

### 9.1 本地持久化要求

如果需要将质检结果落盘，必须使用 `./scripts/result_persister.py`，不得自行约定目录和文件名。

落盘目录必须为：

- `output/results/{task_id}/`

默认根目录必须优先使用当前技能工作区根目录，即同时包含 `BigPoi-verification-qc` 和 `qc-write-pg-qc` 的目录；仅在无法定位该工作区时，才允许回退到单技能目录或显式传入的 `QC_OUTPUT_DIR`。

如果显式传入的 `output_dir` 已经是 `{task_id}` 目录，持久化器必须直接复用该目录，不得再追加一层 `{task_id}`。

持久化器不得将结果保存到 `.claude/skills/<skill>/output/results` 或 `.openclaw/skills/<skill>/output/results`。如果解析出的输出目录位于技能安装目录下，必须自动改写到工作区根目录的 `output/results`。

必须生成以下文件：

- `{timestamp}_{task_id}.complete.json`
- `{timestamp}_{task_id}.summary.json`
- `{timestamp}_{task_id}.results_index.json`

其中：

- `complete.json` 保存完整 `qc_result`
- `summary.json` 保存摘要结果，至少包含 `task_id`、`qc_status`、`qc_score`、`has_risk`、`explanation`、各维度状态和 `statistics_flags`
- `results_index.json` 保存结果索引

时间戳格式必须为：

- `YYYYMMDD_HHmmss`

落盘文件命名和结构必须能够通过 `result_validator.py` 的文件校验。

任一必需文件写入失败时，本次持久化必须返回失败，不得以“部分成功”结果继续回库。

## 10. 结果聚合规则

以下聚合规则必须由 `./scripts/result_contract.py` / `./scripts/finalize_qc_result.py` 统一实现，模型只能提供维度级输入，不得手工改写最终聚合结果。

核心事实维度集合：

- `existence`
- `name`
- `location`
- `address`
- `administrative`
- `category`

整体状态：

- 任一核心维度为 `fail` -> `qc_status = "unqualified"`
- 否则，只要任一核心事实维度为 `risk`，或 `evidence_sufficiency` / `downgrade_consistency` 为 `risk` 或 `fail` -> `qc_status = "risky"`
- 否则 -> `qc_status = "qualified"`

顶层 `explanation` 必须由程序统一生成，至少包含：

- 最终 `qc_status`
- 最终 `qc_score`
- 通过的核心事实维度摘要
- 所有 `risk` / `fail` 维度的具体原因摘要

## 11. 统计标记

`statistics_flags` 必须由 `./scripts/result_contract.py` 统一推导，不得由模型手工修改。

输出中的 `statistics_flags` 必须至少包含：

- `is_qualified`
- `is_auto_approvable`
- `is_manual_required`
- `qc_manual_review_required`
- `upstream_manual_review_required`
- `downgrade_issue_type`

其中：

- `qc_manual_review_required = 任一核心事实维度 status != pass`，或 `evidence_sufficiency != pass`
- `is_qualified = qc_status == "qualified"`
- `is_auto_approvable = qc_status == "qualified"`
- `is_manual_required = qc_manual_review_required`

## 12. 核心原则

- 只基于输入数据判断，不补充外部知识
- 优先输出可复核、可审计的结果
- 遇到边界情况时，按照 `decision_tables.json` 的明确条件处理，不得自行扩展规则
