# CHANGELOG

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
