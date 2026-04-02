# CHANGELOG

## [2.4.12-stable] - 2026-04-02

### 修复
- `scripts/evidence_preprocessor.py` 新增地址文本归一：支持结构化地址对象（如 `{\"full\":...}`）、对象字符串回填，避免 `str(dict)` 直接参与地址匹配导致误判。
- `scripts/dsl_executor.py` 收敛地址锚点提取与城市比较：
  - 增加城市名归一（如 `汕尾市` 与 `广东省汕尾市` 视为同城）；
  - 增强道路锚点清洗（处理“交叉口连接词”“街道/村委等后缀噪声”），降低同址表达差异误判。
- `scripts/result_contract.py` 增强地址语义复核鲁棒性：
  - 地址语义一致性由“首条基准”改为“多数一致簇”判定，避免单条离群证据一票否决；
  - 语义复核过滤 `subject_consistent=false` 证据；
  - 新增“高置信权威硬冲突保护”，对权威来源门牌/行政区硬冲突保持 `risk/fail`，防止过度放宽。

## [2.4.11-stable] - 2026-04-02

### 调整
- `scripts/evidence_preprocessor.py` 新增“主体一致性前置过滤”：在维度判定前先做主体识别与名称锚点比对；主体类型冲突（如居委会 vs 派出所）或明显主体名称不一致的证据直接过滤，不再进入地址/坐标/类型/行政区划等维度计算。
- `scripts/evidence_preprocessor.py` 为保留证据打标 `matching.subject_consistent=true`，并在被过滤证据摘要中输出 `subject_type_mismatch` / `subject_name_mismatch` 原因，便于复盘。
- `scripts/dsl_executor.py` 收敛证据选择：当证据显式标记 `matching.subject_consistent=false` 时，维度 DSL 不再消费该证据，避免主体不一致证据绕过前置过滤。

## [2.4.10-stable] - 2026-04-01

### 修复
- `scripts/result_validator.py` 恢复核心维度证据“信息量”校验：`pass/risk` 维度的 `evidence[]` 不能只含 `evidence_id`，必须包含 `source/data/verification/matching` 中至少一项结构化内容。
- `SKILL.py` 强化证据契约收敛：当维度证据仅为编号引用或无信息量时，自动替换为输入 `evidence_record` 快照，避免结果通过校验但证据不可审计。
- `scripts/dsl_executor.py` 与 `scripts/result_contract.py` 统一地址道路锚点规则：对“街道/社区/镇等前缀差异”“`大道` vs `大道中` 路段差异”“路名包含关系（如 `大兴大道` vs `大布沙大兴大道`）”在门牌一致时按同址软支持处理，不再误判为道路冲突。
- `scripts/result_contract.py` 修复 `location` 语义降级后的证据契约：`no_valid_coordinate_evidence` 从 `fail` 调整为 `risk` 时，若坐标证据为空会自动补入名称/地址维度的有效证据快照，避免 `risk + evidence=[]` 被校验拒绝。
- `scripts/result_contract.py` 调整 `statistics_flags` 人工标记口径：`is_manual_required` / `qc_manual_review_required` 改为按最终 `qc_status` 计算（`risky`、`unqualified` 均为 `true`），以匹配“风险与不通过都需人工查看”的运营策略。
- `scripts/result_contract.py` 收敛 `risky` 触发口径：将 `address/location/category` 的部分 advisory risk（如软地址匹配、可容忍坐标偏移、仅文本类型支撑）自动提升为 `pass`，减少“可自动通过但被标记为 risky”的情况。
- `scripts/result_contract.py` 调整 `qc_status` 聚合：`downgrade_consistency.issue_type=unnecessary_downgrade` 不再单独拉低整体状态；仅阻塞性降级冲突（如 `missed_downgrade`）参与 `risky` 判定。
- `scripts/result_contract.py` 调整 `risk_dims/has_risk` 聚合：`downgrade_consistency.issue_type=unnecessary_downgrade` 不再计入风险维度，避免出现 `qc_status=qualified` 但 `risk_dims` 非空的语义冲突。
- `scripts/result_contract.py` 在语义调整后重算 `evidence_sufficiency`，避免前置计算与最终维度状态不一致。

## [2.4.9-stable] - 2026-04-01

### 调整
- `scripts/result_contract.py` 为 `location` 新增“离群点名称相关性”判断：
- 仅当离群点名称与目标 POI 构成同目标高置信相关时，才保留离群风险
- 若近距离同目标证据占优且离群点名称不相关，可由 `risk/fail` 提升为 `pass`
- 将 `scripts/dsl_executor.py`、`scripts/evidence_preprocessor.py` 正式同步到 `BigPoi-verification-qc-stable/scripts/`，避免依赖分支目录执行
- `SKILL.py` 默认启用 stable 目录内 DSL 核心维度重算（可通过 `prefer_dsl_core_dimensions=false` 显式关闭）
- `scripts/dsl_executor.py` 调整证据截断策略：命中 `location_distance` 时按距离升序优先保留近距离证据，避免离群证据被优先截入

## [2.4.8-stable] - 2026-04-01

### 调整
- `scripts/result_contract.py` 调整人工核实触发逻辑：由“任一 core 维度 risk/fail 即触发”改为“仅 fail / high risk /硬冲突 issue_code 触发”，降低降级一致性误伤
- `scripts/result_contract.py` 增强 `location` 语义收敛：
- 对 `no_valid_coordinate_evidence` 场景，若名称与地址已通过，则由 `fail` 降为 `risk`
- 对坐标离群判定引入“名称相关性过滤 + 多数簇一致”规则，降低低相关离群点影响
- `scripts/result_contract.py` 放宽 `existence` 语义兜底：当 `name=pass` 且其他事实维度存在稳定通过时，可提升存在性判定
- `scripts/result_contract.py` 增强 `address` 语义复核：`fail/risk` 都可进入同址语义校验，支持按名称相似度过滤低相关地址证据

## [2.4.7-stable] - 2026-04-01

### 调整
- `scripts/result_contract.py` 新增地址语义同址评估：对 `address` 的软匹配/单条精确低置信场景，执行结构化语义补判（同址关系、冲突点、置信度）后再决策
- `scripts/result_contract.py` 增强坐标抗离群：支持“单个中距离离群”与“单个 >500m 离群但多数近距离聚合”场景的稳健放宽，避免单点离群一票否决
- `scripts/result_contract.py` 新增 `administrative/category` 语义放宽：对边界 `risk/fail` 场景按多信号一致性降级为 `risk` 或提升为 `pass`
- `scripts/result_contract.py` 调整 `evidence_sufficiency`：核心事实维度全 `pass` 且单条证据置信度足够时，不再重复降级
- `rules/decision_tables.json` 调整 `location` 与 `category` 分级：
- `location` 中 `>500m` 但存在近距离支持时由直接 `fail` 调整为 `risk`
- `category` 中“仅语义回退冲突”从 `fail` 下调为 `risk`，`fail` 保留给 typecode 直接硬冲突

## [2.4.6-stable] - 2026-04-01

### 调整
- 新增存在性语义兜底：当 `name=pass` 且（`address=pass` 或 `location=pass`）并且不存在高置信存在性反证时，`existence` 可从 `risk` 提升为 `pass`
- `existence` 不再仅由平均置信度单点驱动，降低“事实维度已通过但存在性仍 risk”的不合理情况

## [2.4.5-stable] - 2026-04-01

### 调整
- 收敛地址维度 `address_fail_hard_conflict` 触发条件，避免“单条冲突证据”直接将地址判定为 `fail`
- 地址 `fail` 现在要求“冲突证据占主导，且无精确/主地址语义支撑”才触发，降低噪声证据误伤

## [2.4.4-stable] - 2026-04-01

### 修复
- 修复“全量重判”场景下部分维度 `status=risk/pass` 但 `evidence=[]` 导致 `ResultValidator` 拒绝的问题
- 在 `SKILL.py` 增加维度证据契约兜底：
- 当维度为 `pass/risk` 且无证据时，优先从输入 `evidence_record` 自动补齐证据快照
- 若确实无可用证据，则将该维度自动降级为 `fail`，避免非法结果继续流转

## [2.4.3-stable] - 2026-04-01

### 新增
- 创建稳定分支目录 `BigPoi-verification-qc-stable`，完整继承当前规则、阈值、schema、评分策略与持久化逻辑
- 保留争议维度大模型裁决（hybrid）能力：`config/hybrid_policy.json`、`schema/qc_model_judgement.schema.json`、`scripts/hybrid_adjudicator.py`

### 调整
- 技能元数据名称调整为 `bigpoi-verification-qc-stable`
- 版本标识调整为 `v2.4.3-stable`
- 统一继续使用单入口 `SKILL.py`（程序收敛 + 校验 + 持久化），避免临时脚本旁路执行

## [2.4.3] - 2026-04-01

### 新增
- 新增 `SKILL.py` 作为主质检技能唯一对外执行入口，固定执行链路：
- 模型维度草稿收敛（`finalize_qc_result.py`）
- 结果校验（`result_validator.py`）
- 结果持久化（`result_persister.py`）

### 调整
- `SKILL.py` 对模型输入做字段白名单收敛：只采纳维度级草稿，忽略手工拼接的最终聚合字段
- `SKILL.py` 在 finalize 前强制补齐 `downgrade_consistency` 种子字段，并从平铺输入 `verify_result` 推导 `upstream_manual_review_required`
- 仅当 finalize 后校验通过时才允许落盘；失败时返回结构化错误并终止后续流程

### 文档
- `SKILL.md` 升级至 `v2.4.3`，新增“单入口执行（强制）”章节，明确禁止临时脚本执行和手工拼接最终结果

## [2.4.2] - 2026-03-31

### 调整
- `scripts/result_persister.py` 新增运行时配置读取：优先读取 `qc_runtime.json` 的 `result_dir` 作为持久化路径
- 当 `strict_result_dir=true` 时，持久化忽略外部传入 `output_dir`，强制写入配置路径

### 文档
- `SKILL.md` 更新到 `v2.4.2`，补充持久化路径优先级与 `strict_result_dir` 语义

## [2.4.1] - 2026-03-30

### 调整
- Hybrid 硬冲突判定从“关键词优先”升级为“结构化优先”：
- `scripts/result_contract.py` 在 `apply_model_adjudication()` 中，优先使用维度结果的 `issue_code` 与 `hard_conflict` 判定是否可覆盖
- 仅当结构化字段缺失时，才回退到 explanation 关键词识别，兼容历史结果

### 兼容性
- `config/hybrid_policy.json` 新增 `hard_conflict_issue_codes` 配置，按维度声明硬冲突 issue_code 白名单
- `schema/qc_result.schema.json` 的核心维度结果新增可选字段：`issue_code`、`hard_conflict`
- `scripts/result_validator.py` 新增 `issue_code/hard_conflict` 类型校验与约束校验（`hard_conflict=true` 时不得为 `pass`）

## [2.4.0] - 2026-03-30

### 新增
- 新增 `config/hybrid_policy.json`，定义“规则兜底 + 模型裁决”覆盖策略（可覆盖维度、状态迁移、置信度阈值、硬冲突保护、原因码白名单）
- 新增 `schema/qc_model_judgement.schema.json`，约束模型裁决 DSL 结构（`overrides[]`）
- 新增 `scripts/hybrid_adjudicator.py`，用于执行“规则初判 + 模型裁决 + finalize 收敛”流程

### 代码
- `scripts/result_contract.py` 新增 hybrid 能力：
- 新增 `load_hybrid_policy()` 和策略深合并逻辑
- 新增 `derive_uncertain_dims()` 与 `apply_model_adjudication()`，仅对争议维度执行可控覆盖
- 新增硬冲突保护、证据ID归属校验、reason_code 白名单校验、覆盖置信度阈值校验
- `finalize_qc_result()` 新增参数：`model_judgement`、`hybrid_policy`、`hybrid_policy_path`
- 当启用模型裁决时，覆盖后自动重算 `evidence_sufficiency` 和 `downgrade_consistency`

### 兼容性
- `schema/qc_result.schema.json` 新增可选字段 `adjudication`，记录本次 hybrid 覆盖的应用与拒绝明细
- `scripts/result_validator.py` 新增 `adjudication` 结构校验（可选字段）
- `scripts/finalize_qc_result.py` 新增 CLI 参数：`--model-judgement`、`--hybrid-policy`

### 文档
- `SKILL.md` 升级至 `v2.4.0`，补充 hybrid 执行流程和覆盖约束

## [2.3.15] - 2026-03-30

### 调整
- 调整 `rules/decision_tables.json` 的 `R4(address)`：
- 新增 `branch_suffix_only_support_count`、`non_main_branch_soft_support_count`、`high_confidence_main_or_branch_support_count`
- 新增 `address_pass_semantic_soft_support` 分支，支持“主地址/附属后缀语义一致 + 高置信支持”的场景直接 `pass`
- 收紧 `address_risk_soft_match` 触发条件，避免把“仅主地址与附属后缀表达差异”的样本误判为 `risk`

### 代码
- 调整 `scripts/result_contract.py` 地址语义后处理：
- 地址一致性判定仅使用“信息充分地址”（过滤仅省市级低信息地址）
- 新增道路编号等价归一（例如 `325国道` 与 `G325`）
- 当地址仍判定为 `risk` 时，解释优先输出真实冲突点（门牌冲突 / 道路主干冲突 / 主锚点冲突）

### 文档
- 更新 `SKILL.md` 至 `v2.3.15`，补充地址维度中“道路编号等价”与“低信息地址不可单独支撑通过”的规则口径

## [2.3.14] - 2026-03-30

### 修复
- 统一 `downgrade_consistency` 的输出语义，移除 `unresolved` 输出通道：
- `SKILL.md` 与 `rules/decision_tables.json` 同步为布尔口径：`verify_result` 非标准值默认按 `upstream_manual_review_required=false` 处理
- 删除 `R7` 中 `downgrade_risk_unresolved_signal` 分支，避免产出与 `schema/qc_result.schema.json` 不兼容的降级状态
- `scripts/result_contract.py` 在收敛阶段强制修正 `downgrade_consistency`：当 `upstream_manual_review_required` 非布尔时兜底为 `false`，并重算 `status/risk_level/is_consistent/issue_type/explanation`

### 新增
- 新增 `scripts/inject_category_fallback.py`：
- 面向平铺输入自动补齐 `evidence_record[].matching.category_fallback_support`
- 仅在证据缺失 `typecode` 时触发，使用 `poi_type + category + name` 经 `poi_type_mapping.py` 计算 `strong/medium/weak/none`

### 调整
- `scripts/result_contract.py` 在 `category` 维度证据投影前增加自动补齐逻辑：
- 当缺失 `matching.category_fallback_support` 且提供了 `poi_type` 上下文时，自动注入回退强度
- `scripts/finalize_qc_result.py` 新增 `--poi-type` 参数，用于在 finalize 阶段显式传入类型上下文
- `SKILL.md` 升级至 `v2.3.14`，执行流程新增 `inject_category_fallback.py`，并明确禁止输出 `unresolved`

## [2.3.13] - 2026-03-30

### 调整
- 调整 `rules/decision_tables.json`：
- `R2(name)` 高置信强支持阈值由 `name_similarity >= 0.95` 下调为 `>= 0.85`（仍要求 `confidence >= 0.85`）
- `R5(administrative)` 新增“补充推断 city”指标（地址/名称/raw cityname），支持在结构化 `city` 缺失时判定 `pass`
- `R6(category)` 新增语义回退指标（`category_fallback_support` 的 `strong/medium/weak/conflict`），缺失 `typecode` 时不再直接失败，允许按回退强度判定 `pass/risk/fail`
- `R4(address)` 新增 `main_address_only_support_count`，将“仅行政区/镇街道前缀差异、主道路和门牌一致”的场景从 `risk` 提升为 `pass`

### 代码
- 更新 `scripts/result_contract.py` 的证据投影：
- `administrative` 维度输出中增加 `name`，用于展示行政区划补充推断依据
- `category` 维度输出中增加 `matching.category_fallback_support`，用于展示类型语义回退依据
- 调整 `scripts/result_contract.py` 地址语义修正阈值：命中“主地址/前缀差异”场景时放宽置信度门槛，避免将纯前缀差异误判为 `risk`

### 文档
- 更新 `SKILL.md` 至 `v2.3.13`，同步以上规则口径（行政区划补充推断、类型语义回退、名称高置信阈值）

## [2.3.12] - 2026-03-30

### 调整
- 调整 `scripts/normalize_legacy_input.py`，移除 `verify_info` 对标准输入构造的影响：
- `record.existence` 不再读取 `verify_info.existence`，仅基于 `poi_status` 与 `verify_result` 信号推导
- `upstream_decision.dimensions` 不再由 `verify_info` 填充，统一输出 `uncertain` 占位，避免下游误用

### 修复
- 修复 `scripts/result_contract.py` 中 `downgrade_consistency` 计算时机问题：先完成语义修正，再重算降级一致性，避免出现“核心维度已修正为 `pass` 但降级一致性仍为旧值 `fail`”的状态错位
- 明确 `qc_status` 聚合继续纳入 `downgrade_consistency` 风险：当降级一致性为 `risk/fail` 时，整体 `qc_status` 为 `risky`

### 文档
- 更新 `SKILL.md` 与输入 schema，明确 `verify_info` 仅用于追溯，禁止参与 QC 判定、解释和证据选择

## [2.3.11] - 2026-03-30

### 调整
- 在 `scripts/result_contract.py` 新增软风险语义修正器：
- `location` 维度：当存在单个 201-500m 离群点且多数证据在 200m 内时，按稳健规则由 `risk` 修正为 `pass`
- `address` 维度：当命中软匹配风险、存在高置信证据且证据地址语义一致时，由 `risk` 修正为 `pass`
- 调整 `qc_status` 聚合规则：整体状态仅由核心事实维度和 `evidence_sufficiency` 决定，不再由 `downgrade_consistency` 直接拉低
- 调整 `statistics_flags.is_auto_approvable`：仍要求 `qc_status=qualified` 且 `downgrade_consistency` 无风险，避免降级冲突直接自动放行

### 影响
- 仅修正 `risk -> pass` 的边界场景，不会将 `fail` 直接改为 `pass`
- 修正后仍通过统一 `finalize_qc_result` 重算 `qc_score`、`qc_status`、`risk_dims`

## [2.3.10] - 2026-03-18

### 调整
- 调整 `qc-write-pg-qc/scripts/file_loader.py` 和 `qc-write-pg-qc/SKILL.py`，主质检技能目录定位改为按目录结构探测，不再依赖 `BigPoi-verification-qc` 固定目录名
- 调整 `scripts/result_persister.py` 的工作区根目录识别逻辑，兼容 `bigpoi-verification-qc` 等不同目录名安装形态

### 修复
- 修复 Linux 服务器或容器中主质检技能目录为小写 `bigpoi-verification-qc` 时，回库候选校验失败并报“未找到 BigPoi-verification-qc 目录”的问题

## [2.3.9] - 2026-03-18

### 调整
- 调整 `poi_type_mapping.py` 的回退强度：当中文 `category` 至少确认大类、且名称层级规则确认到正确层级时，`fallback_support` 提升为 `strong`
- 这使得类似 `130104 + 福海县人民政府 + 政府机关` 的场景可直接作为 `pass` 级类型回退支撑

### 文档
- 更新 `SKILL.md` 和 `rules/rules.yaml`，明确“大类匹配 + 名称层级匹配”可作为类型通过依据

## [2.3.8] - 2026-03-18

### 调整
- 在 `scripts/poi_type_mapping.py` 中新增 `fallback_support` 汇总结果，统一收敛中文 `category` 和名称层级两类回退信号
- 缺失 `typecode` 时，类型回退现在按 `strong / medium / weak / none` 四档支持强度输出

### 文档
- 更新 `SKILL.md` 和 `rules/rules.yaml`，明确缺失 `typecode` 时必须通过 `poi_type_mapping.py` 决定类型回退强度

## [2.3.7] - 2026-03-18

### 调整
- 在 `scripts/poi_type_mapping.py` 中新增名称层级提取规则，支持从政府类名称中确定 `province / city / county / town`
- 当前名称规则至少覆盖：`省人民政府`、`自治区人民政府`、`市人民政府`、`州人民政府`、`地区行政公署`、`县人民政府`、`区人民政府`、`乡人民政府`、`镇人民政府`

### 文档
- 更新 `SKILL.md` 和 `rules/rules.yaml`，明确缺失 `typecode` 时可使用中文 `category` 和名称层级规则做确定性回退

## [2.3.6] - 2026-03-18

### 调整
- 将 `poi_type` 映射结构升级为“标准大类 + 层级/子类语义”，支持区分政府类 `province / city / county / town` 等层级
- 调整 `scripts/poi_type_mapping.py`，在缺失 `typecode` 时可分别判断中文 `category` 是否命中大类别名、层级别名

### 文档
- 更新 `SKILL.md` 和 `rules/rules.yaml`，明确 `category` 维度必须拆成“大类一致”和“层级/子类一致”两层判断

## [2.3.5] - 2026-03-17

### 新增
- 新增 `config/poi_type_mapping.json`，用于将内部 `poi_type` 映射到白名单类型
- 新增 `scripts/poi_type_mapping.py`，用于在缺失 `typecode` 时按映射表匹配中文 `category`

### 文档
- 更新 `SKILL.md` 和 `rules/rules.yaml`，明确 `category` 维度的判定顺序为：`typecode` 优先，缺失时再回退到映射后的中文类目别名

## [2.3.4] - 2026-03-17

### 调整
- 为 `administrative` 增加“官方或权威来源地址包含输入 city”这一补充弱支持
- 弱支持只能帮助边界通过判定，不参与行政区划冲突，不会把地址重新变成主判定字段
- 当存在单条结构化 `city` 一致证据且同时有官方/权威地址弱支持时，允许 `administrative` 直接通过

### 输出
- 调整 `administrative` 维度证据快照，允许在需要时展示相关地址文本作为弱支持依据

## [2.3.3] - 2026-03-17

### 调整
- 将各维度 `evidence` 输出收敛为按维度裁剪的证据快照，不再重复输出与当前维度无关的字段
- 将顶层 `explanation` 改为由 `result_contract.py` 程序统一生成，自动汇总最终状态、得分、通过维度和风险原因

### 文档
- 更新 `SKILL.md`，明确模型不得手工编写顶层 `explanation`，维度 `evidence` 只允许输出相关字段快照

## [2.3.2] - 2026-03-17

### 调整
- 将上游人工核实信号识别逻辑改为直接读取平铺输入 `verify_result`
- 固定映射规则：`核实通过 -> false`，`需人工核实/需要人工核实 -> true`
- 不再以 `upstream_decision.*` 作为 `downgrade_consistency` 的主判定来源

### 文档
- 更新 `SKILL.md`，明确 `verify_result` 是上游人工核实信号的唯一官方输入字段

## [2.3.1] - 2026-03-17

### 调整
- 将 DSL 和结果收敛逻辑中仍为 `0.90` 的“高置信度支持”门槛统一下调为 `0.85`
- 统一 `name` 高置信强支持、`address` 高置信精确支持、`evidence_sufficiency` 高权威高置信支持的置信度口径

### 文档
- 更新 `SKILL.md`，明确当前默认高置信度门槛为 `verification.confidence >= 0.85`

## [2.3.0] - 2026-03-17

### 改进
- 将 `schema/qc_input.schema.json` 收敛为上游平铺输入的唯一官方契约，不再以 canonical 输入作为主口径
- 调整 `rules/decision_tables.json`，将 `location` 的通过阈值放宽到 `200m`，并将 `201-500m` 定义为风险区间、`>500m` 定义为失败区间
- 调整 `rules/decision_tables.json`，将 `administrative` 维度收敛为只比较输入 `city` 与证据 `administrative.city`，禁止引入地址字段
- 调整 `rules/decision_tables.json`，将 `category` 维度改为优先比较输入 `poi_type` 与证据 `typecode`
- 调整 `rules/decision_tables.json` 和 `SKILL.md`，明确 `address` 的精确支持、软匹配、硬冲突定义，并要求地址解释输出真实冲突点

### 文档
- 更新 `SKILL.md` 执行流程，明确直接消费平铺输入，不再执行结构归一化
- 更新 `rules/rules.yaml`、`examples/sample_input.json` 与相关 schema 描述，使其与平铺输入主口径保持一致

## [2.2.8] - 2026-03-17

### 修复
- 调整 `scripts/result_persister.py`，在真正写入 `complete/summary/index` 文件前先执行 `finalize_qc_result.py` 和 `result_validator.py`，无效结果禁止落盘

### 文档
- 更新 `SKILL.md` 的持久化约束，明确落盘前必须先通过结果校验

## [2.2.7] - 2026-03-17

### 修复
- 统一 `statistics_flags.is_manual_required` 与 `statistics_flags.qc_manual_review_required` 的语义，两者现在都只表示“QC 是否认为需要人工复核”
- 修正 `downgrade_consistency` 导致整体 `qc_status = risky` 时 `is_manual_required` 被误置为 `true` 的问题

### 文档
- 更新 `SKILL.md` 统计标记说明，明确 `is_manual_required = qc_manual_review_required`

## [2.2.6] - 2026-03-17

### 新增
- 新增 `evidence_sufficiency` 维度，用于在 6 个事实维度全部匹配后继续判断“当前证据是否足以支撑自动通过”

### 修复
- 调整 `scripts/result_contract.py` 的最终聚合逻辑：允许 6 个事实维度全部 `pass`，但因 `evidence_sufficiency = risk/fail` 将整体 `qc_status` 判为 `risky`
- 调整 `config/scoring_policy.json`，为 `evidence_sufficiency` 和 `downgrade_consistency` 重新分配权重，保持总分固定 100 分
- 调整 `rules/decision_tables.json`、相关 schema 和规则注册表，补齐 `R8` 与 `evidence_sufficiency` 的 DSL 定义
- 更新回归样例和示例输出，覆盖“事实维度通过但证据不足导致整体 risky”的场景

### 文档
- 更新 `SKILL.md`，将质检点扩展为 8 个，并明确 `evidence_sufficiency` 只表达自动通过门槛风险，不反向污染事实维度

## [2.2.5] - 2026-03-17

### 新增
- 新增 `scripts/result_contract.py`，集中实现 `qc_status`、`qc_score`、`has_risk`、`risk_dims`、`triggered_rules`、`statistics_flags` 的确定性派生逻辑
- 新增 `scripts/finalize_qc_result.py`，用于在维度级结果基础上组装完整 `qc_result`

### 修复
- 调整 `scripts/result_validator.py`，复用统一的结果契约计算逻辑，避免“结果组装一套、结果校验一套”导致的漂移
- 调整 `scripts/result_persister.py`，在落盘前先统一收敛派生字段，减少持久化后回库校验失败

### 文档
- 更新 `SKILL.md` 执行流程，明确模型只输出维度级结果，派生字段必须由 `finalize_qc_result.py` 生成
- 更新 `SKILL.md` 权威文件列表和禁止项，禁止模型手工拼装 `qc_score`、`qc_status`、`risk_dims`、`triggered_rules`、`statistics_flags`

## [2.2.4] - 2026-03-17

### 修复
- 在 `scripts/normalize_legacy_input.py` 中加入 `source.source_type` 规范化逻辑，统一将 `地图数据`、`官方数据`、`official`、`map_vendor` 等上游写法映射到 QC DSL 识别的内部枚举
- 保留 `source.original_source_type` 以便审计上游原始来源类型，避免规范化后丢失原始输入

### 文档
- 更新 `SKILL.md` 预处理流程，明确在无效证据过滤前需要先完成 `source_type` 规范化

## [2.2.3] - 2026-03-17

### 新增
- 在 `scripts/normalize_legacy_input.py` 中加入统一证据预处理逻辑；无论输入是 canonical 还是 legacy flat，都会在质检前先过滤无效证据

### 修复
- 过滤 `verification.is_valid = false` 的证据，避免其进入完整性检查和维度判定
- 增加同主实体去噪规则，过滤明显属于附属点位或关联设施的证据，例如 `东门`、`西门`、`停车场`、`政务中心`、`办事大厅`
- 允许预处理后 `evidence_data` 为空，由完整性检查统一判定失败，而不是被输入 schema 提前拦截

### 文档
- 更新 `SKILL.md` 执行流程，明确“归一化 -> 无效证据过滤 -> 完整性检查 -> 维度判定”的固定顺序
- 更新 `schema/qc_input.schema.json` 描述，使其与预处理后可能出现的空 `evidence_data` 保持一致

## [2.2.2] - 2026-03-17

### 修复
- 重新检查并收紧 6 个业务维度的 DSL 判定条件，修复“单条支持证据一律不能通过”的过严规则
- 为 `existence`、`name`、`location`、`address`、`administrative`、`category` 增加“单条高置信度证据可直接通过”的 pass 分支
- 收紧 `name/category` 的中等匹配风险分支，以及 `address/administrative` 的弱支持风险分支，避免本应 pass 的强支持结果被提前判为 risk

### 文档
- 更新 `SKILL.md` 中 6 个业务维度的判定语义，明确“高置信度单证据可 pass，低置信度单证据才 risk”

## [2.2.1] - 2026-03-17

### 修复
- 为 `scripts/result_persister.py` 增加技能安装目录保护；当输出目录解析到 `.claude/skills/<skill>/output/results` 或 `.openclaw/skills/<skill>/output/results` 时，自动改写到工作区根目录的 `output/results`

### 文档
- 更新 `SKILL.md` 的持久化约束，明确禁止将结果保存到技能安装目录下的 `output/results`

## [2.2.0] - 2026-03-17

### 新增
- 新增 `schema/qc_legacy_flat_input.schema.json`，用于描述旧版平铺输入
- 新增 `scripts/normalize_legacy_input.py`，用于将 legacy 平铺输入稳定归一化为 canonical 输入

### 改进
- 将 `schema/qc_input.schema.json` 扩展为同时接受 canonical 输入和 legacy 平铺输入
- 重写 `SKILL.md` 执行流程，明确 legacy 输入必须先归一化，再执行完整性检查、结果校验和本地持久化

### 约束
- 明确禁止在执行过程中创建 `run_qc.py`、`temp_qc_processor.py` 等临时 Python 脚本
- 明确禁止手写持久化路径，要求结果路径只能来自 `result_persister.py` 的真实返回值

## [2.1.5] - 2026-03-16

### 修复
- 为 `scripts/result_persister.py` 增加 `output_dir` 归一化逻辑；当调用方传入的输出目录已经是 `{task_id}` 目录时，直接复用该目录，避免生成双层 `{task_id}/{task_id}` 路径

### 文档
- 更新 `SKILL.md` 中的持久化约束，明确 `output_dir` 已指向任务目录时的处理规则

## [2.1.4] - 2026-03-16

### 修复
- 调整 `scripts/result_persister.py` 的默认落盘根目录识别逻辑，优先对齐当前技能工作区根目录，避免与 `qc-write-pg-qc` 的默认查找根目录不一致
- 调整持久化返回语义：任一必需文件写入失败时，`status` 可为 `partial`，但 `success` 必须为 `false`，禁止调用方将部分落盘结果继续视为可回库状态

### 文档
- 更新 `SKILL.md` 中的本地持久化要求，明确默认根目录优先级和 `partial` 返回的失败语义

## [2.1.3] - 2026-03-16

### 文档
- 补全 `SKILL.md` 第 7 节，完整覆盖 `existence`、`name`、`location`、`address`、`administrative`、`category`、`downgrade_consistency` 7 个维度
- 将维度定义统一为“语义边界写在 `SKILL.md`，具体阈值与证据规则写在 `decision_tables.json` DSL”

## [2.1.2] - 2026-03-16

### 修复
- 将结果持久化要求恢复到 `SKILL.md` 的权威说明中，避免主技能文档与 `result_persister.py` 实现脱节
- 将 `result_persister.py` 补回权威加载链路
- 修正 `CLAUDE.md` 中指向旧版 `SKILL.md` 章节号的失效引用

## [2.1.1] - 2026-03-16

### 清理
- 删除旧版分散规则文件 `rules/**/R*.yaml`，避免与 `rules/decision_tables.json` 并存造成误导
- 删除废弃配置 `config/score_weights.yaml`、`config/risk_dimension_map.yaml` 和未消费的 `config/downgrade_policy.yaml`

### 记录
- 保留既有版本历史，仅在 `CHANGELOG.md` 中追加本次清理记录
- 当前目录的权威规则链路继续保持为 `SKILL.md -> decision_tables.json -> decision_tables.schema.json -> scoring_policy.json -> dsl_validator.py/result_validator.py`

## [2.1.0] - 2026-03-16

### 新增
- 为 `rules/decision_tables.json` 增加 DSL 结构，补充 `metrics`、`outcomes`、`evidence_policy`
- 新增 `schema/decision_tables.schema.json`，用于约束 DSL 本身
- 新增 `source_priority_profiles`、`normalization_profiles`、`derived_fields`
- 新增 `scripts/dsl_validator.py`，用于校验 DSL 结构和关键执行约束

### 改进
- 将原先的“条件名列表”升级为可校验的条件表达式
- 明确地址、行政区划、坐标边界和人工核实信号的 DSL 表达方式
- 降低模型在证据选择、解释生成和规则解释上的自由度

## [2.0.0] - 2026-03-16

### 重构
- 将质检维度重构为 6 个核心维度加 1 个降级一致性维度
- 新增独立的 `address` 维度，并将 `location` 明确定义为仅校验坐标
- 移除单独的 `downgrade` 维度，改为直接比较 QC 与上游是否都需要人工核实

### 规则
- 引入 `rules/decision_tables.json` 作为唯一权威规则来源
- 将旧版 Markdown 规则文档降级为解释材料，避免模型在多份文档之间自由发挥
- 将规则注册表收敛为 `R1-R7`

### 评分
- 重构为固定 100 分权重制，不再使用比例换算公式
- 新增 `config/scoring_policy.json`，支持按维度权重和状态系数反算得分
- 修复“分数超过 100”这一类规范级问题

### 校验
- 重写 `result_validator.py`，增加 Schema 校验、评分反算、统计标记一致性校验
- 修复结果文件命名校验与文件类型识别中的历史 bug
- 强制所有维度输出 `evidence` 数组

### 示例
- 更新输入输出样例以匹配新维度与新评分体系
- 新增地址冲突和降级一致性相关回归场景

## [1.1.0] - 2024-01-15

### 新增
- 新增规则引擎模块，实现规则的加载、匹配和分数聚合
- 新增降级检查器，实现数据质量降级的自动检测
- 新增配置管理模块，支持评分权重、降级策略和风险维度的配置
- 新增示例文件，提供测试和回归用例

### 改进
- 优化规则结构，将规则按类别分类管理
- 改进评分算法，支持多维度风险评估
- 优化输出结果格式，提供更详细的规则触发信息

### 修复
- 修复规则匹配逻辑中的边界情况
- 修复分数计算中的溢出问题

## [1.0.0] - 2024-01-01

### 初始版本
- 实现基本的 QC 验证功能
- 支持核心规则的配置和执行
- 提供基本的评分和降级功能
